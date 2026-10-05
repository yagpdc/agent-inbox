"""Roda SÓ o plano (Opus, só leitura) de um pedido com ficha, pra ver se o agente acha o lugar certo.

  python testes/plano.py testes/fichas/exemplo.json

Usa uma cópia descartável do banco e o modo autônomo desligado: o plano fica pronto e para ali
(nada de execução, worktree ou servidor local). Imprime o plano.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from testes.replay import preparar_banco  # noqa: E402
from servidor import db, runner  # noqa: E402


def main():
    ficha = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    preparar_banco()
    db.salvar_config("orquestrador", {"autonomo": False})
    pessoa = next(iter(db.pessoas()))
    t = db.criar_tarefa({"titulo": ficha["titulo"], "tipo": "tarefa", "status": "identificada",
                         "categoria": ficha["tipo"], "sub": ficha.get("sub") or None, "prioridade": "P1",
                         "pessoa": pessoa, "pedido": ficha["pedido"], "ficha": ficha,
                         "workspace": (ficha.get("workspace") or {}).get("id")})
    runner.planejar(t["id"])
    inicio = time.time()
    while db.tarefa(t["id"])["status"] == "triagem" and time.time() - inicio < 20 * 60:
        time.sleep(10)
    final = db.tarefa(t["id"])
    print(f"status: {final['status']}  ({int(time.time() - inicio)} s)  esperando: {final.get('esperando')}")
    print(json.dumps(final.get("plano") or final.get("pergunta"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
