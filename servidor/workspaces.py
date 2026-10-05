"""Catálogo de workspaces (nome -> id) pro orquestrador confirmar em qual cliente é o pedido.

Vem da tabela workspace_permissions do geodriva (todo workspace que já abriu o Atlas),
lida em prod SÓ LENDO (CLAUDE-CONTEXT §7), uma vez por dia. Fica em
agentes/_comum/workspaces.json; se a leitura falhar, segue com a última cópia.
"""

import json
import re
import threading
import time
import unicodedata

from . import db, local, prod

ARQUIVO = db.RAIZ / "agentes" / "_comum" / "workspaces.json"
VALIDADE = 24 * 3600
# prefixo do id -> nome. Clientes em que um erro custa caro: o agente para e chama você.
PROTEGIDOS: dict[str, str] = local.valor("workspacesProtegidos", {})
# onde camada de cliente sobe primeiro, pra você conferir antes de ir pro cliente
TESTE: dict = local.valor("workspaceTeste", {"id": "", "nome": "workspace de teste"})

_CONSULTA = """
import json
from app.database import pg_query
linhas = pg_query("SELECT workspace_id, workspace_name, tags_enabled, positivation_enabled, management_enabled, "
                  "routes_enabled, analysis_enabled, comercial_enabled FROM workspace_permissions "
                  "WHERE workspace_name IS NOT NULL AND workspace_name <> ''")
flags = ("tags_enabled", "positivation_enabled", "management_enabled", "routes_enabled", "analysis_enabled", "comercial_enabled")
print("@@" + json.dumps([{"id": l["workspace_id"], "nome": l["workspace_name"],
                          "recursos": sum(1 for f in flags if l.get(f))} for l in linhas], ensure_ascii=False))
"""

_trava = threading.Lock()


def _norm(texto: str) -> str:
    s = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def atualizar() -> list[dict]:
    """Lê a lista em prod (só SELECT). Levanta erro se não conseguir."""
    saida = prod.python_no_backend(_CONSULTA, timeout=90)
    linha = next((l for l in saida.splitlines() if l.startswith("@@")), None)
    if not linha:
        raise RuntimeError(f"não consegui ler os workspaces: {saida.strip()[-300:]}")
    itens = sorted(json.loads(linha[2:]), key=lambda w: w["nome"].lower())
    with _trava:
        ARQUIVO.write_text(json.dumps({"atualizadoEm": time.time(), "itens": itens}, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    return itens


def catalogo() -> list[dict]:
    """A lista local; se estiver velha, atualiza em segundo plano (não trava a conversa)."""
    dados = json.loads(ARQUIVO.read_text(encoding="utf-8")) if ARQUIVO.exists() else {}
    if time.time() - dados.get("atualizadoEm", 0) > VALIDADE:
        threading.Thread(target=_atualizar_quieto, daemon=True, name="workspaces").start()
    itens = dados.get("itens") or []
    if not TESTE.get("id") or any(w["id"] == TESTE["id"] for w in itens):
        return itens
    return [*itens, TESTE]


_ultima_tentativa = [0.0]


def _atualizar_quieto() -> None:
    """Uma atualização por vez, e no máximo uma tentativa a cada 30 min se prod não responder."""
    with _trava:
        if time.time() - _ultima_tentativa[0] < 1800:
            return
        _ultima_tentativa[0] = time.time()
    try:
        atualizar()
    except Exception as e:  # noqa: BLE001
        print(f"[workspaces] {e}", flush=True)


def buscar(texto: str, limite: int = 6) -> list[dict]:
    """Workspaces cujo nome contém todas as palavras do texto (sem acento, sem caixa)."""
    palavras = _norm(texto).split()
    if not palavras:
        return []
    achados = []
    for w in catalogo():
        nome = _norm(w["nome"])
        tokens = nome.split()
        if all(any(t.startswith(p) for t in tokens) for p in palavras):
            achados.append((len(nome), w))  # nome mais curto = mais exato
    return [w for _, w in sorted(achados, key=lambda x: x[0])][:limite]


def repetidos(nome: str) -> list[dict]:
    """Workspaces com exatamente o mesmo nome (acontece: o mesmo cliente cadastrado duas vezes)."""
    alvo = _norm(nome)
    return [w for w in catalogo() if _norm(w["nome"]) == alvo]


def principal(candidatos: list[dict]) -> dict | None:
    """Entre nomes repetidos: o protegido, senão o único com mais recursos ligados. Empate = ninguém."""
    protegidos = [w for w in candidatos if protegido(w["id"])]
    if len(protegidos) == 1:
        return protegidos[0]
    ordem = sorted(candidatos, key=lambda w: w.get("recursos", 0), reverse=True)
    if len(ordem) > 1 and ordem[0].get("recursos", 0) > ordem[1].get("recursos", 0):
        return ordem[0]
    return ordem[0] if len(ordem) == 1 else None


def por_id(wid: str) -> dict | None:
    return next((w for w in catalogo() if w["id"] == wid), None)


def protegido(wid: str | None) -> str | None:
    """Nome do cliente protegido, se o workspace for um deles."""
    return next((nome for pref, nome in PROTEGIDOS.items() if (wid or "").startswith(pref)), None)
