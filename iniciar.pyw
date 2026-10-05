"""Inicia o Inbox Agent sem janela.

  pythonw iniciar.pyw             sobe (se preciso) e abre o painel
  pythonw iniciar.pyw --agendado  usado pela tarefa agendada do Windows (logon e a cada 5 min):
                                  se já estiver rodando, não faz nada

Log em inbox-agent/logs/servidor.log.
"""

import socket
import sys
import time
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
PORTA = 8787
URL = f"http://localhost:{PORTA}/"
AGENDADO = "--agendado" in sys.argv


def painel_aberto() -> bool:
    import json
    from urllib.request import urlopen
    try:
        with urlopen(f"http://127.0.0.1:{PORTA}/api/abas", timeout=2) as r:
            return json.load(r)["abas"] > 0
    except Exception:  # noqa: BLE001
        return False


def ja_rodando() -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", PORTA)) == 0


PAUSA = RAIZ / "pausado"


def pausado() -> bool:
    """Pausa só pra esta sessão do Windows: vale enquanto o PC não for reiniciado/deslogado.

    Assim o auto-start continua valendo amanhã sem você precisar lembrar de religar.
    """
    if not PAUSA.exists():
        return False
    import ctypes
    ligado_ha = ctypes.windll.kernel32.GetTickCount64() / 1000  # segundos desde o boot
    if PAUSA.stat().st_mtime < time.time() - ligado_ha:
        PAUSA.unlink(missing_ok=True)  # a pausa é de antes deste boot: vale de novo
        return False
    return True


if pausado():
    sys.exit(0)

if ja_rodando():
    if not AGENDADO and not painel_aberto():
        webbrowser.open(URL)
    sys.exit(0)

(RAIZ / "logs").mkdir(exist_ok=True)
log = open(RAIZ / "logs" / "servidor.log", "a", encoding="utf-8", buffering=1)
sys.stdout = sys.stderr = log  # pythonw não tem console
print(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} iniciando ({'tarefa agendada' if AGENDADO else 'manual'})")

sys.path.insert(0, str(RAIZ))
from servidor.api import rodar  # noqa: E402

def abrir_se_preciso():
    # Painéis que já estavam abertos reconectam sozinhos em poucos segundos; só abre se nenhum voltar.
    from servidor import barramento
    if not barramento.abas():
        webbrowser.open(URL)


threading.Timer(10, abrir_se_preciso).start()
rodar(PORTA, dev=False)
