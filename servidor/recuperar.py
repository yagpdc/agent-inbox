"""Recupera tarefas que ficaram sem acompanhamento (servidor reiniciado, PC desligado).

Ao subir, procura tarefas em "planejando" ou "em execução". Pelo arquivo da sessão do agente:
  - sessão terminou com resultado  -> registra como se o servidor tivesse visto;
  - sessão ainda escrevendo         -> acompanha até terminar;
  - sessão parada sem resultado     -> volta a tarefa pra etapa anterior como "interrompida".
"""

import json
import re
import threading
import time
from pathlib import Path

from . import barramento, db, runner

PROJETOS = Path.home() / ".claude" / "projects"
PARADA_APOS = 10 * 60  # sessão sem escrever há mais que isso e sem resultado = morreu
INTERVALO = 20


def _pasta_do_projeto(cwd: Path) -> Path:
    return PROJETOS / re.sub(r"[^A-Za-z0-9]", "-", str(cwd))


def _arquivo_da_sessao(t: dict, etapa: str, cwd: Path) -> Path | None:
    sessao = (t.get("execucao") or {}).get("sessao") if etapa == "execucao" else None
    if sessao:
        achados = list(PROJETOS.glob(f"*/{sessao}.jsonl"))
        if achados:
            return achados[0]
    # Sem id: a sessão mais recente na pasta daquele projeto com o nome "inbox <id> <etapa>".
    nome = f"inbox {t['id']} {'execução' if etapa == 'execucao' else 'resposta' if t.get('tipo') == 'duvida' else 'plano'}"
    candidatos = sorted(_pasta_do_projeto(cwd).glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    alvo = f'"customTitle":"{nome}"'
    for arq in candidatos[:30]:
        with open(arq, encoding="utf-8", errors="replace") as f:
            if any(alvo in linha for linha in f):
                return arq
    return None


def _ler_sessao(arq: Path) -> tuple[dict | None, str | None]:
    """(resultado estruturado, último passo) lidos do arquivo da sessão."""
    saida, passo = None, None
    with open(arq, encoding="utf-8", errors="replace") as f:
        for linha in f:
            try:
                ev = json.loads(linha)
            except json.JSONDecodeError:
                continue
            if ev.get("type") != "assistant":
                continue
            for bloco in ev.get("message", {}).get("content", []):
                if bloco.get("type") != "tool_use":
                    continue
                if bloco.get("name") == "StructuredOutput":
                    saida = bloco.get("input")
                else:
                    passo = runner._descrever_ferramenta(bloco)  # noqa: SLF001
    return saida, passo


def _acompanhar(tid: str, etapa: str) -> None:
    t = db.tarefa(tid)
    if etapa == "execucao" and t["plano"].get("repo") in runner.REPOS:
        cwd = runner.WORKTREES / f"{tid}-{t['plano']['repo']}"
        branch = runner._git(cwd, "branch", "--show-current", checar=False) or None  # noqa: SLF001
    else:
        cwd, branch = runner.DRIVA, None

    arq = None
    inicio = (t.get("execucao") or {}).get("desde") if etapa == "execucao" else t.get("esperando")
    while True:
        atual = db.tarefa(tid)
        if atual["status"] != ("execucao" if etapa == "execucao" else "triagem"):
            return  # você decidiu outra coisa enquanto isso
        agora = (atual.get("execucao") or {}).get("desde") if etapa == "execucao" else atual.get("esperando")
        if agora != inicio:
            return  # a tarefa recomeçou por outro caminho: quem começou acompanha
        arq = arq or _arquivo_da_sessao(atual, etapa, cwd)
        if arq:
            saida, passo = _ler_sessao(arq)
            sessao = arq.stem
            if saida is not None:
                if etapa == "execucao":
                    runner.finalizar_execucao(tid, saida, sessao, cwd if branch else None, branch)
                elif atual.get("tipo") == "duvida":
                    runner.finalizar_resposta(tid, saida, sessao)
                else:
                    runner.finalizar_plano(tid, saida, sessao)
                return
            if etapa == "execucao" and passo:
                e = atual["execucao"] or {}
                if e.get("passo") != passo or e.get("sessao") != sessao:
                    barramento.publicar("tarefa", tarefa=db.atualizar_tarefa(tid, execucao={**e, "passo": passo, "sessao": sessao}))
            parada = time.time() - arq.stat().st_mtime > PARADA_APOS
        else:
            parada = True
        if parada:
            nome = "Execução" if etapa == "execucao" else "Pesquisa" if atual.get("tipo") == "duvida" else "Plano"
            e = atual.get("execucao") or {}
            if runner.autonomo(atual) and not e.get("retomadaSozinha"):
                # Pedido do orquestrador: ninguém está olhando pra dar o clique. Tenta de novo uma vez sozinho.
                db.atualizar_tarefa(tid, execucao={**e, "retomadaSozinha": True})
                runner._evento(f"{nome} interrompida pelo reinício: recomecei sozinho", tid)  # noqa: SLF001
                if etapa == "execucao":
                    db.atualizar_tarefa(tid, status="aprovacao")
                    runner.executar(tid, *runner.modelo_recomendado(atual))
                else:
                    db.atualizar_tarefa(tid, status="identificada")
                    runner.pesquisar(tid) if atual.get("tipo") == "duvida" else runner.planejar(tid)
                return
            runner._falhou(tid, nome, RuntimeError("interrompida (o servidor ou o PC reiniciou no meio)"),  # noqa: SLF001
                           volta_para="aprovacao" if etapa == "execucao" else "identificada")
            return
        time.sleep(INTERVALO)


def iniciar() -> int:
    orfas = [(t["id"], "execucao" if t["status"] == "execucao" else "plano")
             for t in db.tarefas() if t["status"] in ("execucao", "triagem")]
    for tid, etapa in orfas:
        threading.Thread(target=_acompanhar, args=(tid, etapa), daemon=True, name=f"recuperar-{tid}").start()
    return len(orfas)
