"""Agentes especialistas: um por tipo de pedido, cada um com o seu contrato.

Cada tipo mora em agentes/<tipo>/:
  agente.json      modelos, repos, campos obrigatórios da ficha, o que é "deploy" pra ele
  CONTEXTO.md      como entregar certo nesse tipo
  APRENDIZADOS.md  lições dos ajustes do Yago (lidas em toda tarefa do tipo)

O orquestrador usa o contrato pra saber o que perguntar; o servidor usa o mesmo
contrato pra conferir a ficha antes de despachar (não confia só no modelo).
"""

import json
import threading

from . import db

PASTA = db.RAIZ / "agentes"
COMUM = PASTA / "_comum"
TIPOS = ("site", "hub", "mapa", "camadas", "reativacao", "duvida")

_trava = threading.Lock()


def definicao(tipo: str) -> dict:
    return json.loads((PASTA / tipo / "agente.json").read_text(encoding="utf-8"))


def todos() -> dict[str, dict]:
    return {t: definicao(t) for t in TIPOS}


def nomes() -> dict[str, dict]:
    """Pro painel: o nome do agente (Sora) e do que ele cuida (Mapa)."""
    return {t: {"apelido": d.get("apelido") or d["nome"], "nome": d["nome"]} for t, d in todos().items()}


def _ler(caminho) -> str:
    return caminho.read_text(encoding="utf-8").strip() if caminho.exists() else ""


def comum(nome: str) -> str:
    return _ler(COMUM / nome)


def contexto(tipo: str) -> str:
    """Tudo que o agente do tipo precisa saber, na ordem em que importa."""
    tipo = tipo if tipo in TIPOS else "hub"
    partes = [
        f"## Contexto do agente {definicao(tipo)['nome']}\n{_ler(PASTA / tipo / 'CONTEXTO.md')}",
        f"## Aprendizados (ajustes que o Yago já pediu; valem mais que o contexto)\n{_ler(PASTA / tipo / 'APRENDIZADOS.md')}",
        f"## Regra de deploy\n{comum('DEPLOY.md')}",
        f"## Onde procurar mais (leia só se precisar)\n{comum('FONTES.md')}",
    ]
    return "\n\n".join(partes) + "\n"


def modelo(tipo: str, etapa: str) -> tuple[str, str | None]:
    """(apelido do modelo, esforço) da etapa: plano, execucao ou pesquisa."""
    conf = definicao(tipo if tipo in TIPOS else "hub").get(etapa) or {}
    padrao = {"plano": ("opus", "high"), "execucao": ("sonnet", "high"), "pesquisa": ("sonnet", "medium")}[etapa]
    return conf.get("modelo", padrao[0]), conf.get("esforco", padrao[1])


# ---------------- ficha ----------------

def obrigatorios(tipo: str, sub: str | None) -> list[dict]:
    """Campos que a ficha precisa ter pra esse tipo (bug pede mais que feature)."""
    return [c for c in definicao(tipo).get("campos", [])
            if c.get("obrigatorio") is True or (c.get("obrigatorio") == "bug" and sub == "bug")]


def precisa_workspace(tipo: str, sub: str | None) -> bool:
    regra = definicao(tipo).get("workspace", "opcional")
    return regra == "obrigatorio" or (regra == "se_bug" and sub == "bug")


def faltando(ficha: dict) -> list[str]:
    """O que ainda falta na ficha pra poder despachar. Lista vazia = pode."""
    tipo = ficha.get("tipo")
    if tipo not in TIPOS:
        return ["tipo"]
    falta = [c for c in ("pedido", "criterio") if not str(ficha.get(c) or "").strip()]
    if tipo == "duvida":
        return [c for c in falta if c == "pedido"]
    sub = ficha.get("sub")
    ws = ficha.get("workspace") or {}
    if precisa_workspace(tipo, sub) and not (ws.get("id") and ws.get("nome")):
        falta.append("workspace")
    campos = ficha.get("campos") or {}
    falta += [c["campo"] for c in obrigatorios(tipo, sub) if not str(campos.get(c["campo"]) or "").strip()]
    return falta


def ficha_em_texto(ficha: dict) -> str:
    """A ficha como o agente especialista lê (é o pedido dele; a conversa crua não vai)."""
    d = definicao(ficha["tipo"])
    rotulos = {c["campo"]: c["pergunta"] for c in d.get("campos", [])}
    ws = ficha.get("workspace") or {}
    linhas = [
        f"Tipo: {d['nome']}{' (bug)' if ficha.get('sub') == 'bug' else ' (feature)' if ficha.get('sub') == 'feature' else ''}",
        f"Pedido: {ficha.get('pedido', '').strip()}",
        f"Como saber que ficou certo: {ficha.get('criterio', '').strip() or '(não informado)'}",
    ]
    if ws.get("id"):
        linhas.append(f"Workspace: {ws.get('nome')} ({ws['id']})")
    if ficha.get("prioridade") and ficha["prioridade"] != "normal":
        linhas.append(f"Urgência: {ficha['prioridade']}")
    if ficha.get("prazo"):
        linhas.append(f"Quem pediu precisa até: {ficha['prazo']}")
    for campo, valor in (ficha.get("campos") or {}).items():
        if str(valor or "").strip():
            linhas.append(f"{rotulos.get(campo, campo)} {valor}".strip())
    return "\n".join(linhas)


# ---------------- aprendizados ----------------

def registrar_aprendizado(tipo: str, tid: str, licao: str) -> None:
    """Uma lição nova no fim do APRENDIZADOS.md do tipo (a mais nova vale mais)."""
    licao = " ".join((licao or "").split())
    if tipo not in TIPOS or not licao:
        return
    with _trava:
        arq = PASTA / tipo / "APRENDIZADOS.md"
        atual = arq.read_text(encoding="utf-8") if arq.exists() else f"# Aprendizados: {definicao(tipo)['nome']}\n"
        arq.write_text(atual.rstrip() + f"\n- {db.agora()[:10]} {tid}: {licao}\n", encoding="utf-8")


# ---------------- tela Agentes ----------------

MODELOS = ("opus", "sonnet", "haiku")
ESFORCOS = ("low", "medium", "high", "xhigh", "max")
ARQUIVOS = {"contexto": "CONTEXTO.md", "aprendizados": "APRENDIZADOS.md"}


def ler_arquivo(tipo: str, qual: str) -> str:
    if tipo not in TIPOS or qual not in ARQUIVOS:
        raise KeyError(f"{tipo}/{qual}")
    return _ler(PASTA / tipo / ARQUIVOS[qual])


def salvar_arquivo(tipo: str, qual: str, texto: str) -> None:
    if tipo not in TIPOS or qual not in ARQUIVOS:
        raise KeyError(f"{tipo}/{qual}")
    with _trava:
        (PASTA / tipo / ARQUIVOS[qual]).write_text(texto.rstrip() + "\n", encoding="utf-8")


def salvar_definicao(tipo: str, patch: dict) -> dict:
    """O que dá pra mudar pela tela: modelos, regra de workspace e quais campos são obrigatórios."""
    if tipo not in TIPOS:
        raise KeyError(tipo)
    with _trava:
        d = definicao(tipo)
        for etapa in ("plano", "execucao", "pesquisa"):
            if etapa in patch:
                m, e = patch[etapa].get("modelo"), patch[etapa].get("esforco")
                if m not in MODELOS or e not in ESFORCOS:
                    raise ValueError(f"{etapa}: modelo {m!r} ou esforço {e!r} inválido")
                d[etapa] = {"modelo": m, "esforco": e}
        if "workspace" in patch:
            if patch["workspace"] not in ("obrigatorio", "se_bug", "opcional", "nao"):
                raise ValueError("regra de workspace inválida")
            d["workspace"] = patch["workspace"]
        if "campos" in patch:  # só muda a obrigatoriedade e a pergunta dos campos que já existem
            novos = {c.get("campo"): c for c in patch["campos"]}
            for c in d.get("campos", []):
                if c["campo"] in novos:
                    ob = novos[c["campo"]].get("obrigatorio", c.get("obrigatorio"))
                    c["obrigatorio"] = ob if ob in (True, False, "bug") else c.get("obrigatorio")
                    c["pergunta"] = (novos[c["campo"]].get("pergunta") or c["pergunta"]).strip()
        for chave in ("resumo", "deploy", "ondeTestar", "apelido"):
            if isinstance(patch.get(chave), str) and patch[chave].strip():
                d[chave] = patch[chave].strip()
        for chave in ("exemplos", "naoE"):
            if isinstance(patch.get(chave), list):
                d[chave] = [str(x).strip() for x in patch[chave] if str(x).strip()]
        (PASTA / tipo / "agente.json").write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return d


def painel() -> dict:
    """Tudo que a tela Agentes mostra: config, o que cada um está fazendo e o que já fez."""
    from . import runner  # evita import circular
    tarefas = db.tarefas()
    fila = runner.estado_fila()
    rodando = {a["tarefa"] for a in fila["ativos"]}
    saida = {}
    for tipo, d in todos().items():
        minhas = [t for t in tarefas if runner.tipo_da(t) == tipo and not t["descartada"]
                  and (t["tipo"] == "tarefa" or tipo == "duvida")]
        agora = [t for t in minhas if t["status"] in ("triagem", "execucao") or t["id"] in rodando]
        feitas = [t for t in minhas if t["status"] == "feito"]
        ajustadas = [t for t in feitas if any(f["quem"] == "voce" for f in db.falas(t["id"]))]
        saida[tipo] = {
            "definicao": d,
            "contexto": ler_arquivo(tipo, "contexto"),
            "aprendizados": ler_arquivo(tipo, "aprendizados"),
            "agora": [{"id": t["id"], "titulo": t["titulo"], "status": t["status"],
                       "passo": (t.get("execucao") or {}).get("passo") or t.get("esperando"),
                       "progresso": (t.get("execucao") or {}).get("progresso")} for t in agora],
            "fila": [x for x in fila["fila"] if runner.tipo_da(db.tarefa(x["tarefa"]) or {}) == tipo],
            "historico": [{"id": t["id"], "titulo": t["titulo"], "status": t["status"],
                           "concluidaEm": t.get("concluidaEm"), "subiu": "no_ar" in (t.get("marcos") or {})
                           or bool((t.get("resultado") or {}).get("deploy", {}).get("tipo") not in (None, "nenhum"))}
                          for t in minhas[:15]],
            "numeros": {"total": len(minhas), "feitas": len(feitas), "ajustadas": len(ajustadas),
                        "abertas": len([t for t in minhas if t["status"] != "feito"])},
        }
    return saida


# ---------------- pro orquestrador ----------------

def cardapio() -> str:
    """Os agentes, do jeito que o orquestrador precisa pra rotear e montar a ficha."""
    blocos = []
    for tipo, d in todos().items():
        campos = "; ".join(
            f"{c['campo']} ({'obrigatório' if c.get('obrigatorio') is True else 'obrigatório se bug' if c.get('obrigatorio') == 'bug' else 'opcional'}): {c['pergunta']}"
            for c in d.get("campos", [])) or "nenhum"
        regra_ws = {"obrigatorio": "obrigatório", "se_bug": "obrigatório se for bug", "nao": "não se aplica",
                    "opcional": "opcional"}[d.get("workspace", "opcional")]
        blocos.append(
            f"### {tipo}: {d['nome']}\n{d['resumo']}\n"
            f"Exemplos reais: {' | '.join(d.get('exemplos', []))}\n"
            f"NÃO é deste agente: {' | '.join(d.get('naoE', [])) or '-'}\n"
            f"Workspace: {regra_ws}\nCampos: {campos}"
        )
    return "\n\n".join(blocos)
