"""Repassa conversas reais do Chat pelo orquestrador, sem enviar nada e sem rodar agente.

  python -m testes.replay u116110648650993081979 [--max 60]

Usa uma cópia descartável do banco, sem as tarefas antigas (senão o orquestrador
acharia que tudo é complemento delas). As mensagens da pessoa entram em rajadas (intervalo < 90 s),
na ordem em que chegaram; o que o orquestrador "responde" entra no histórico como se tivesse sido
enviado. Imprime a conversa e, no fim, quantos pedidos foram despachados.
"""

import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from servidor import db  # noqa: E402

BASE = RAIZ / "tarefas.db"


def preparar_banco() -> Path:
    """Cópia descartável do banco (pela API de backup: vale mesmo com o servidor rodando)."""
    tmp = Path(tempfile.mkdtemp(prefix="replay-")) / "tarefas.db"
    origem = sqlite3.connect(f"file:{BASE.as_posix()}?mode=ro", uri=True)
    destino = sqlite3.connect(tmp)
    origem.backup(destino)
    origem.close()
    destino.close()
    db.CAMINHO = tmp
    db._con = None  # noqa: SLF001
    db.iniciar()
    c = db.con()
    c.executescript("""
        DELETE FROM falas; DELETE FROM eventos; UPDATE mensagens SET tarefa = NULL;
        DELETE FROM atendimentos; DELETE FROM tarefas;
    """)
    db.salvar_config("respostaDm", {"ativa": True})
    c.commit()
    return tmp


def main():
    pessoa = sys.argv[1]
    maximo = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 999
    preparar_banco()
    msgs = [dict(r) for r in db.con().execute(
        "SELECT * FROM mensagens WHERE pessoa = ? ORDER BY recebida_em", (pessoa,)).fetchall()][:maximo]
    if not msgs:
        sys.exit("sem mensagens dessa pessoa")
    nome = db.pessoas()[pessoa]["nome"]
    espaco = msgs[0]["espaco"]
    usuario = "users/" + pessoa[1:]

    from servidor import chat, orquestrador, runner, vigia
    historico: list[dict] = []
    log: list[str] = []
    feitos = {"despachos": [], "pesquisas": [], "chamadas": [], "reaberturas": []}
    relogio = [None]

    def msg(texto, autor, assistente=False, quando=None):
        n = len(historico) + 1
        return {"name": f"{espaco}/messages/r{n:04d}", "text": texto, "createTime": quando,
                "sender": {"name": autor, "type": "HUMAN"}, "_assistente": assistente}

    def enviar(esp, texto, thread=None):
        quando = (datetime.fromisoformat(relogio[0].replace("Z", "+00:00")) + timedelta(seconds=30)).isoformat()
        historico.append(msg(texto, "users/yago", True, quando.replace("+00:00", "Z")))
        log.append(f"    ASSISTENTE: {texto}")

    chat.meu_usuario = lambda: "users/yago"
    chat.ultimas = lambda esp, n=15: historico[-n:]
    chat.nome = lambda u: nome if u == usuario else "Colega"
    chat.do_assistente = lambda m: m.get("_assistente", False)
    chat.enviar = enviar
    chat.tipo_do_espaco = lambda esp: "DIRECT_MESSAGE"
    runner.yago_na_conversa = lambda esp: False
    runner.enviar_arquivos = lambda *a, **k: None
    orquestrador.RESPOSTA_ATE = timedelta(days=3650)
    orquestrador._baixar_anexos = lambda *a, **k: None  # noqa: SLF001

    def planejar(tid, *a, **k):
        t = db.tarefa(tid)
        feitos["despachos"].append(t)
        log.append(f"    >>> DESPACHADO {tid} [{t['categoria']}] {t['titulo']}\n        ficha: {t['ficha']}")

    def pesquisar(tid, *a, **k):
        feitos["pesquisas"].append(tid)
        log.append(f"    >>> PESQUISA {tid}: {db.tarefa(tid)['pedido']}")

    def chamar(esp, item, motivo):
        feitos["chamadas"].append(motivo)
        log.append(f"    >>> CHAMA O YAGO: {motivo}")

    def reabrir(tid, texto):
        feitos["reaberturas"].append(tid)
        log.append(f"    >>> REABRE {tid}: {texto}")

    runner.planejar = planejar
    runner.pesquisar = pesquisar
    runner.reabrir = reabrir
    vigia._chamar_yago = chamar  # noqa: SLF001

    # rajadas: mensagens com menos de 90 s entre si viram um "novas" só (o debounce faz isso na vida real)
    rajadas, atual = [], []
    for m in msgs:
        if atual and (datetime.fromisoformat(m["recebida_em"].replace("Z", "+00:00"))
                      - datetime.fromisoformat(atual[-1]["recebida_em"].replace("Z", "+00:00"))).total_seconds() > 90:
            rajadas.append(atual)
            atual = []
        atual.append(m)
    rajadas.append(atual)

    for rajada in rajadas:
        novas = []
        for m in rajada:
            novo = msg(m["texto"], usuario, quando=m["recebida_em"])
            novo["name"] = m["id"]
            novas.append(novo)
            log.append(f"{m['recebida_em'][5:16].replace('T', ' ')} {nome.split()[0]}: {m['texto'][:400]}")
        relogio[0] = rajada[-1]["recebida_em"]
        historico.extend(novas)
        item = {"espaco": {"name": espaco, "spaceType": "DIRECT_MESSAGE"}, "novas": novas,
                "historico": list(historico[-orquestrador.HISTORICO:]), "pessoa": pessoa, "dm": True}
        try:
            orquestrador.tratar(espaco, item, "users/yago")
        except Exception as e:  # noqa: BLE001
            log.append(f"    !!! ERRO: {e!r}")
        print("\n".join(log), flush=True)
        log.clear()

    abertos = db.atendimentos()
    print("\n==== RESUMO", nome)
    print(f"mensagens: {len(msgs)} em {len(rajadas)} rajadas")
    print(f"despachados: {len(feitos['despachos'])}  " + "; ".join(f"{t['id']} [{t['categoria']}] {t['titulo']}"
                                                            for t in feitos["despachos"]))
    print(f"pesquisas: {len(feitos['pesquisas'])}  chamadas ao Yago: {len(feitos['chamadas'])}  "
          f"reaberturas: {len(feitos['reaberturas'])}")
    print(f"rascunhos ainda abertos: {[(a['id'], a['estado'], (a['ficha'] or {}).get('titulo')) for a in abertos]}")


if __name__ == "__main__":
    main()
