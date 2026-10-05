"""Decidir pelo celular, no espaço "Inbox Agent - Mobile" do Google Chat.

  saída  webhook do espaço (credenciais/webhook-chat.json) — uma THREAD por tarefa.
  volta  o vigia já lê esse espaço; o que VOCÊ escrever numa thread vira decisão.

Você responde com o número da opção ("1"), ou escreve livre ("pode fazer, mas só no
layout novo") — texto livre vale como instrução, igual ao chat do painel. Deploy só
com a palavra `deploy`, pra não sair no automático.
"""

import json
import urllib.parse
import urllib.request

from . import db

CONFIG = db.RAIZ / "credenciais" / "webhook-chat.json"

# Opções por etapa. A ordem é a do número que você responde.
OPCOES = {
    "tarefa": [("1", "pode fazer (plano + execução)", "fazer"), ("2", "só o plano", "planejar"),
               ("3", "deixa comigo", "assumir"), ("4", "não é tarefa", "descartar")],
    "duvida": [("1", "pesquisar e responder", "pesquisar"), ("2", "assumir a conversa", "assumir-conversa"),
               ("3", "deixa comigo", "assumir"), ("4", "não é tarefa", "descartar")],
    "plano": [("1", "executar", "aprovar"), ("2", "refazer o plano", "reprovar"), ("3", "deixa comigo", "assumir")],
    "resposta": [("1", "enviar no Chat", "enviar"), ("2", "descartar", "descartar")],
    "deploy": [("deploy", "subir (escreva a palavra deploy)", "deploy"), ("2", "concluir sem deploy", "concluir")],
    "pergunta": [],  # é só responder escrevendo
}

CABECALHO = {
    "tarefa": "Nova tarefa", "duvida": "Nova dúvida", "plano": "Plano pronto",
    "resposta": "Resposta pronta", "deploy": "Pronta pra deploy", "pergunta": "Preciso de você",
    "falhou": "Travou", "complemento": "Quem pediu acrescentou",
}


def _config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}


def ligado() -> bool:
    """Só manda pro celular quando você liga o modo — senão vira ruído no Chat."""
    return bool(_config().get("url")) and bool(db.config().get("movel", {}).get("ativo"))


def disponivel() -> bool:
    return bool(_config().get("url"))


def espaco() -> str | None:
    return _config().get("espaco")


def enviar(texto: str, tarefa: str | None = None) -> dict | None:
    """Posta no espaço. Com tarefa, entra na thread dela (uma conversa por tarefa)."""
    cfg = _config()
    if not cfg.get("url"):
        return None
    url = cfg["url"]
    if tarefa:
        url += "&" + urllib.parse.urlencode({
            "threadKey": tarefa, "messageReplyOption": "REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD"})
    req = urllib.request.Request(url, data=json.dumps({"text": texto}).encode(), method="POST",
                                 headers={"Content-Type": "application/json; charset=UTF-8"})
    with urllib.request.urlopen(req, timeout=20) as r:
        msg = json.loads(r.read() or b"{}")
    thread = (msg.get("thread") or {}).get("name")
    if thread and tarefa:  # guarda pra saber de qual tarefa é a sua resposta
        db.salvar_config("movel", {"threads": {**_threads(), thread: tarefa}})
    return msg


def _threads() -> dict:
    return db.config().get("movel", {}).get("threads", {})


def tarefa_da_thread(thread: str | None) -> str | None:
    return _threads().get(thread or "")


# ---------------- o que sai ----------------

def _linha_opcoes(tipo: str) -> str:
    return "\n".join(f"{n} — {rotulo}" for n, rotulo, _ in OPCOES.get(tipo, [])) or "Responda escrevendo."


def avisar(tipo: str, t: dict) -> None:
    """Mesma decisão que aparece no painel, agora no seu celular."""
    if not ligado() or not t:
        return
    if tipo == "tarefa" and t.get("tipo") == "duvida":
        tipo = "duvida"
    if tipo not in CABECALHO:
        return
    quem = db.pessoas().get(t["pessoa"], {}).get("nome", "alguém").split(" ")[0]
    corpo = {
        "tarefa": lambda: t["pedido"][:600],
        "duvida": lambda: t["pedido"][:600],
        "plano": lambda: f"{(t['plano'] or {}).get('resumo', '')[:600]}\n\nRisco {(t['plano'] or {}).get('risco')} · {(t['plano'] or {}).get('estimativa')}",
        "resposta": lambda: f"Rascunho:\n{(t['resposta'] or {}).get('texto', '')[:600]}",
        "deploy": lambda: f"{(t['resultado'] or {}).get('resumo', '')[:500]}\n\n{(t['resultado'] or {}).get('deploy', {}).get('resumo', '')}",
        "pergunta": lambda: "\n".join(f"- {i['pergunta']}" for i in (t["pergunta"] or {}).get("itens", []))[:900],
        "falhou": lambda: (t.get("esperando") or "Algo deu errado.")[:600],
        "complemento": lambda: "Mandou mais detalhes depois de pronto. Veja a conversa da tarefa.",
    }[tipo]()
    try:
        enviar(f"*{CABECALHO[tipo]} · {t['id']}* ({quem})\n{t['titulo']}\n\n{corpo}\n\n{_linha_opcoes(tipo)}", t["id"])
    except Exception:  # noqa: BLE001
        pass  # o painel continua sendo a fonte; o celular é conveniência


def avisar_texto(tid: str, texto: str) -> None:
    if ligado():
        try:
            enviar(texto, tid)
        except Exception:  # noqa: BLE001
            pass


ESPERA = {"identificada": "ok pro plano", "comigo": "com você", "pergunta": "sua resposta",
          "resposta": "enviar a resposta", "aprovacao": "ok pra executar", "revisao": "testar e subir",
          "execucao": "rodando", "triagem": "planejando"}


def resumo_pendentes() -> str:
    """O que está esperando você, pra pedir do celular a qualquer hora."""
    pessoas = db.pessoas()
    abertas = [t for t in db.tarefas() if t["status"] != "feito"]
    esperando = [t for t in abertas if t["status"] not in ("execucao", "triagem")]
    rodando = [t for t in abertas if t["status"] in ("execucao", "triagem")]
    if not abertas:
        return "Nada pendente. Tudo em dia."
    linhas = [f"*{len(esperando)} esperando você*"]
    for t in esperando:
        quem = pessoas.get(t["pessoa"], {}).get("nome", "alguém").split(" ")[0]
        linhas.append(f"• {t['id']} — {t['titulo']} ({quem} · {ESPERA.get(t['status'], t['status'])})")
    if rodando:
        linhas.append(f"\n*{len(rodando)} rodando agora*")
        linhas += [f"• {t['id']} — {t['titulo']} ({(t['execucao'] or {}).get('passo', 'trabalhando')})" for t in rodando]
    linhas.append("\nResponda dentro da thread da tarefa pra decidir. Aqui fora, escreva `pendentes` pra ver de novo.")
    return "\n".join(linhas)


def comando_geral(texto: str) -> None:
    """Mensagem no espaço fora de uma thread: comandos gerais."""
    t = texto.strip().lower()
    if t in ("pendentes", "pendencias", "pendências", "status", "tarefas", "?"):
        enviar(resumo_pendentes())
    else:
        enviar("Pra decidir, responda dentro da thread da tarefa. Aqui fora eu entendo `pendentes`.")


# ---------------- o que volta ----------------

def _tipo_da_vez(t: dict) -> str:
    if t["status"] in ("identificada", "comigo"):
        return "duvida" if t["tipo"] == "duvida" else "tarefa"
    return {"aprovacao": "plano", "resposta": "resposta", "revisao": "deploy", "pergunta": "pergunta"}.get(t["status"], "")


def processar(tid: str, texto: str) -> None:
    """Sua mensagem numa thread do espaço: número vira ação, texto livre vira instrução."""
    from .api import Conflito, decidir  # evita import circular
    t = db.tarefa(tid)
    if not t:
        return
    escolha = texto.strip().lower()
    acao = next((a for n, _, a in OPCOES.get(_tipo_da_vez(t), []) if escolha == n), None)
    try:
        if acao == "aprovar":
            from .runner import modelo_recomendado
            modelo, esforco = modelo_recomendado(t)
            decidir(tid, "aprovar", {"modelo": modelo, "esforco": esforco})
            enviar(f"Executando com {modelo.replace('claude-', '')}. Te aviso quando der pra testar.", tid)
        elif acao == "enviar":
            decidir(tid, "enviar", {"texto": (t["resposta"] or {}).get("texto", "")})
            enviar("Enviei no Chat.", tid)
        elif acao == "reprovar":
            decidir(tid, "reprovar", {"motivo": "pelo celular"})
            enviar("Refazendo o plano.", tid)
        elif acao in ("deploy", "concluir"):
            decidir(tid, acao, {"avisar": True})  # e conta pra quem pediu quando terminar
            enviar("Deploy começando. Aviso a pessoa quando terminar." if acao == "deploy"
                   else "Concluí sem deploy e contei pra pessoa.", tid)
        elif acao:
            decidir(tid, acao, {})
            enviar({"fazer": "Beleza: vou planejar e executar.", "planejar": "Vou montar só o plano.",
                    "assumir": "Fica com você.", "descartar": "Descartei.",
                    "pesquisar": "Vou pesquisar e responder.", "assumir-conversa": "Assumi a conversa.",
                    "deploy": "Deploy começando.", "concluir": "Concluí sem deploy."}.get(acao, "Feito."), tid)
        else:
            decidir(tid, "falar", {"texto": texto})  # texto livre: mesma coisa do chat do painel
            enviar("Anotado, seguindo com isso.", tid)
    except Conflito as e:
        enviar(f"Não deu: {e}", tid)
    except Exception as e:  # noqa: BLE001
        enviar(f"Deu erro aqui: {str(e)[:200]}", tid)
