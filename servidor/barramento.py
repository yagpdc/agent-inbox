"""Canal de atualização ao vivo (Server-Sent Events).

Cada aba aberta do painel assina uma fila. Qualquer parte do servidor chama
`publicar(...)` e todas as abas recebem na hora, sem F5.

Tipos publicados:
  tarefa      {"tarefa": {...}}                         tarefa criada/alterada
  evento      {"evento": {...}}                         entrou na atividade recente
  aviso       {"aviso": "tarefa|plano|deploy", "tarefa": {...}}   pede decisão sua
  fala        {"texto": "..."}                          o pet fala algo
  metricas    {"metricas": {...}}
  recarregar  {}                                        código do painel mudou (modo dev)
  abrirAba    {"url": "...", "nome": "..."}             o painel abre/reaproveita a aba com esse nome
"""

import json
import queue
import threading

_assinantes: set[queue.Queue] = set()
_trava = threading.Lock()


def assinar() -> queue.Queue:
    fila: queue.Queue = queue.Queue(maxsize=200)
    with _trava:
        _assinantes.add(fila)
    return fila


def cancelar(fila: queue.Queue) -> None:
    with _trava:
        _assinantes.discard(fila)


def abas() -> int:
    """Quantas abas do painel estão conectadas agora."""
    with _trava:
        return len(_assinantes)


def abrir_aba(url: str, nome: str) -> None:
    """Reaproveita a aba pelo nome (via painel); só abre uma nova se não houver painel aberto."""
    if abas():
        publicar("abrirAba", url=url, nome=nome)
    else:
        import webbrowser
        webbrowser.open(url)


def publicar(tipo: str, **dados) -> None:
    if tipo == "aviso":  # a mesma decisão, também no celular
        from . import movel  # evita import circular
        movel.avisar(dados.get("aviso", ""), dados.get("tarefa") or {})
    mensagem = f"event: {tipo}\ndata: {json.dumps(dados, ensure_ascii=False)}\n\n"
    with _trava:
        for fila in list(_assinantes):
            try:
                fila.put_nowait(mensagem)
            except queue.Full:  # aba travada/esquecida: derruba, ela reconecta sozinha
                _assinantes.discard(fila)
