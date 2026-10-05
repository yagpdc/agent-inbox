"""Horas trabalhadas no dia: conta o tempo em que o notebook está ligado e acordado.

Um relógio bate a cada 30 s e soma o intervalo desde a batida anterior. Se o notebook
suspendeu, hibernou ou desligou, a próxima batida chega muito depois — esse buraco não
é somado. É isso que faz o timer pausar sozinho quando você fecha a tampa pra se mexer,
sem depender de o painel estar aberto.

Zera à meia-noite; os últimos 60 dias ficam guardados.
"""

import threading
import time
from datetime import date

from . import barramento, db

BATIDA = 30        # segundos entre batidas
BURACO = 120       # intervalo maior que isso = notebook estava dormindo/desligado: não conta
META_PADRAO = 8    # horas

_parar = threading.Event()


def _estado() -> dict:
    return db.config().get("jornada", {})


def resumo() -> dict:
    e = _estado()
    hoje = date.today().isoformat()
    return {
        "dia": hoje,
        "segundos": e.get("segundos", 0) if e.get("dia") == hoje else 0,
        "metaHoras": e.get("metaHoras", META_PADRAO),
        "historico": e.get("historico", {}),
    }


def _bater() -> None:
    agora = time.time()
    hoje = date.today().isoformat()
    e = _estado()
    historico = dict(e.get("historico", {}))
    segundos = e.get("segundos", 0) if e.get("dia") == hoje else 0
    ultima = e.get("ultimaBatida")
    if ultima and 0 < agora - ultima <= BURACO:
        segundos += agora - ultima  # estava acordado desde a última batida
    historico[hoje] = round(segundos)
    for dia in sorted(historico)[:-60]:  # guarda só os últimos 60 dias
        historico.pop(dia)
    db.salvar_config("jornada", {"dia": hoje, "segundos": segundos, "ultimaBatida": agora, "historico": historico})


def _laco() -> None:
    avisado = 0
    while not _parar.is_set():
        try:
            _bater()
            if time.time() - avisado >= 60:  # o painel atualiza a cada minuto
                barramento.publicar("jornada", jornada=resumo())
                avisado = time.time()
        except Exception:  # noqa: BLE001
            pass  # o timer nunca pode derrubar o servidor
        _parar.wait(BATIDA)


def iniciar() -> None:
    threading.Thread(target=_laco, daemon=True, name="jornada").start()
