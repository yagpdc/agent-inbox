"""Acesso ao servidor de prod, num lugar só.

O host é um alias do ~/.ssh/config, definido em local.json (`prodSshHost`).
Dá pra trocar o comando inteiro em config.prod.ssh sem mexer no código.

Só dois usos: rodar os scripts de deploy do repo e ler (SELECT/diagnóstico). Nada manual em prod.
"""

import subprocess

from . import db, local

PADRAO = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", local.valor("prodSshHost", "prod")]


def ssh() -> list[str]:
    return list(db.config().get("prod", {}).get("ssh") or PADRAO)


def rodar(remoto: str, entrada: str | None = None, timeout: int = 900) -> str:
    """Roda um comando no servidor. Erro (código != 0) vira RuntimeError com o fim da saída."""
    r = subprocess.run([*ssh(), remoto], input=entrada, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    saida = (r.stdout + r.stderr).strip()
    if r.returncode != 0:
        raise RuntimeError(saida[-600:] or f"ssh saiu com código {r.returncode}")
    return r.stdout


def python_no_backend(codigo: str, timeout: int = 120) -> str:
    """Roda Python dentro do container do backend do geodriva (só pra leitura/diagnóstico)."""
    return rodar("docker exec -i backend python", entrada=codigo, timeout=timeout)


def script_de_deploy(nome: str) -> str:
    """Um dos scripts do repo (deploy-back.sh, deploy-front.sh, deploy-all.sh). Nunca outra coisa."""
    if nome not in ("deploy-back.sh", "deploy-front.sh", "deploy-all.sh"):
        raise ValueError(f"script de deploy desconhecido: {nome}")
    return rodar(f"bash /home/ubuntu/geodriva/scripts/{nome}", timeout=900)
