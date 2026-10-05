"""python -m servidor [--porta 8787] [--sem-dev]
python -m servidor login      login do Google (uma vez)
python -m servidor vigia      roda um ciclo do vigia e mostra o resultado (teste)
"""

import argparse

p = argparse.ArgumentParser(prog="servidor")
p.add_argument("comando", nargs="?", choices=["login", "vigia"])
p.add_argument("--porta", type=int, default=8787)
p.add_argument("--sem-dev", action="store_true", help="não recarrega o painel quando o código muda")
args = p.parse_args()

if args.comando == "login":
    from .google import login
    login()
elif args.comando == "vigia":
    from . import chat, db, vigia
    db.iniciar()
    print("Eu:", chat.meu_usuario(), "-", chat.nome(chat.meu_usuario()))
    print("Espaços:", len(chat.espacos()))
    vigia.ciclo()
    print("Estado:", db.config().get("vigia"))
else:
    from .api import rodar
    rodar(args.porta, dev=not args.sem_dev)
