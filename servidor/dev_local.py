"""Servidores de desenvolvimento locais durante as tarefas (hub e site).

Quando uma execução começa num repo com front, a porta dele passa a servir a
cópia da tarefa (recarrega sozinho enquanto o agente edita):
  hub-driva  -> localhost:3000 (Vite). Ao terminar, volta pro hub principal (atlas-homolog).
  drivaio    -> localhost:5173 (Next). Abre uma aba na página alterada. Ao terminar, desliga.

Só encerra o que estiver na porta se for o servidor esperado (node + vite/next).
"""

import shutil
import subprocess
import threading
from pathlib import Path

from . import barramento, db

DRIVA = db.RAIZ.parent
LOG = db.RAIZ / "logs" / "dev-local.log"
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)

REPOS = {
    "hub-driva": {
        "porta": 3000,
        "principal": DRIVA / "hub-driva",
        "comando": ["npx", "vite", "--port", "3000", "--strictPort"],
        "assinatura": "vite",
        "voltar_ao_principal": True,
        "abrir_aba": False,  # você já deixa a 3000 aberta
        "dev_hacks": ["src/api/axios.ts", "src/api/_geodriva/client.ts"],  # overrides locais: nunca vão pro commit
    },
    "drivaio": {
        "porta": 5173,
        "principal": DRIVA / "drivaio",
        "comando": ["npx", "next", "dev", "-p", "5173", "--webpack"],  # node_modules é junction: webpack lida melhor
        "assinatura": "next",
        "voltar_ao_principal": False,
        "abrir_aba": True,
        "dev_hacks": [],
    },
}

_trava = threading.Lock()


def _ps(comando: str) -> str:
    r = subprocess.run(["powershell", "-NoProfile", "-Command", comando],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=SEM_JANELA)
    return r.stdout.strip()


def _processo_na_porta(porta: int) -> tuple[int, str] | None:
    saida = _ps(
        f"$c = Get-NetTCPConnection -LocalPort {porta} -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; "
        "if ($c) { $p = Get-CimInstance Win32_Process -Filter \"ProcessId = $($c.OwningProcess)\"; "
        "\"$($p.ProcessId)|$($p.Name)|$($p.CommandLine)\" }"
    )
    if not saida:
        return None
    pid, nome, linha = (saida.split("|", 2) + ["", ""])[:3]
    return int(pid), f"{nome} {linha}"


def _liberar(cfg: dict) -> None:
    dono = _processo_na_porta(cfg["porta"])
    if not dono:
        return
    pid, linha = dono
    if "node" not in linha.lower() or cfg["assinatura"] not in linha.lower():
        raise RuntimeError(f"A porta {cfg['porta']} está com outro programa ({linha[:80]}). Não mexi.")
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=SEM_JANELA)


def _preparar_copia(cfg: dict, pasta: Path) -> None:
    """Leva .env e dev hacks do repo principal pra cópia da tarefa, fora do git."""
    principal = cfg["principal"]
    for env in principal.glob(".env*"):
        if env.name != ".env.example" and env.is_file() and not (pasta / env.name).exists():
            shutil.copy2(env, pasta / env.name)
    for rel in cfg["dev_hacks"]:
        origem, destino = principal / rel, pasta / rel
        if origem.exists() and origem.read_bytes() != (destino.read_bytes() if destino.exists() else b""):
            shutil.copy2(origem, destino)
            subprocess.run(["git", "-C", str(pasta), "update-index", "--skip-worktree", rel], capture_output=True)


def _estado() -> dict:
    return db.config().get("devLocal", {})


def _subir(repo: str, pasta: Path, tarefa: str | None, url: str | None) -> None:
    cfg = REPOS[repo]
    with _trava:
        _liberar(cfg)
        LOG.parent.mkdir(exist_ok=True)
        saida = open(LOG, "a", encoding="utf-8")
        saida.write(f"\n=== {db.agora()} {repo}: subindo {pasta} ({tarefa or 'principal'})\n")
        saida.flush()
        subprocess.Popen(["cmd", "/c", *cfg["comando"]], cwd=pasta, stdout=saida, stderr=subprocess.STDOUT,
                         creationflags=SEM_JANELA)
        db.salvar_config("devLocal", {repo: {"tarefa": tarefa, "pasta": str(pasta), "url": url}})
    barramento.publicar("devLocal", devLocal=_estado())


def _rota(arquivos: list[str]) -> str:
    """app/gtm-summit/componentes/X.tsx -> /gtm-summit (ignora grupos '(x)' e pastas internas)."""
    for a in arquivos:
        partes = a.replace("\\", "/").split("/")
        if "app" in partes[:2]:  # aceita "app/..." e "drivaio/app/..."
            segmentos = []
            for p in partes[partes.index("app") + 1:-1]:
                if p.startswith(("(", "[", "_")) or p in ("componentes", "components", "secoes", "api"):
                    break
                segmentos.append(p)
            return "/" + "/".join(segmentos)
    return "/"


def mostrar_tarefa(repo: str, pasta: Path, tarefa: str, arquivos: list[str]) -> None:
    """A porta do repo passa a mostrar a cópia desta tarefa (e abre a aba, se for o caso)."""
    cfg = REPOS.get(repo)
    if not cfg or _estado().get(repo, {}).get("tarefa") == tarefa:
        return
    _preparar_copia(cfg, pasta)
    url = f"http://localhost:{cfg['porta']}" + (_rota(arquivos) if repo == "drivaio" else "/")
    _subir(repo, pasta, tarefa, url)
    barramento.publicar("fala", texto=f"{url} agora mostra a {tarefa}.")
    if cfg["abrir_aba"]:
        # dá tempo do servidor subir; a aba tem nome fixo por porta, então é sempre a mesma
        threading.Timer(12, barramento.abrir_aba, args=(url, f"inbox-local-{cfg['porta']}")).start()


def tarefa_terminou(tarefa: str) -> None:
    """Se alguma porta estava com esta tarefa: volta pro principal ou desliga."""
    for repo, info in _estado().items():
        if info.get("tarefa") != tarefa:
            continue
        cfg = REPOS[repo]
        try:
            if cfg["voltar_ao_principal"]:
                _subir(repo, cfg["principal"], None, f"http://localhost:{cfg['porta']}/")
                barramento.publicar("fala", texto=f"localhost:{cfg['porta']} voltou pro {repo} principal.")
            else:
                with _trava:
                    _liberar(cfg)
                    db.salvar_config("devLocal", {repo: {"tarefa": None, "pasta": None, "url": None}})
                barramento.publicar("devLocal", devLocal=_estado())
        except Exception as e:  # noqa: BLE001
            barramento.publicar("fala", texto=f"Não consegui liberar a porta {cfg['porta']}: {e}")


def url_da_tarefa(tarefa: str) -> str | None:
    return next((i.get("url") for i in _estado().values() if i.get("tarefa") == tarefa), None)
