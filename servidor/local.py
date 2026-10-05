"""Valores desta instalação que não vão pro git: ids, hosts, e-mails.

Ficam em local.json, na raiz (ignorado pelo git). O modelo é local.exemplo.json.
Sem o arquivo, cada valor cai num padrão neutro e as partes que dependem dele ficam
sem efeito (ex.: sem workspace de teste, o agente de camadas não grava nada).
"""

import json
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent.parent / "local.json"


def _carregar() -> dict:
    try:
        return json.loads(ARQUIVO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


_LOCAL = _carregar()


def valor(chave: str, padrao=None):
    return _LOCAL.get(chave, padrao)
