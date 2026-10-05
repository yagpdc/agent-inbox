"""Deploy de camada personalizada, em dois passos (decisão do Yago):

  1. teste    a camada sobe no workspace de teste pra ele ver no mapa de verdade;
  2. cliente  com o ok dele, a MESMA camada (copiada pelo id, com o que ele ajustou na tela) vai pro
              workspace do cliente, e é conferida no banco em sessão só leitura.

O agente só produz os dados (camadas.json + .geojson na pasta de entregas da tarefa). Quem grava é o
carregador fixo ferramentas/camada.py, num container descartável do backend (docker compose run --rm),
o mesmo caminho que o Yago usava na mão. Gravar em prod só depois que ele liberar: config camadas.gravarEmProd.
"""

import json
import subprocess

from . import barramento, db, prod, workspaces

FERRAMENTA = db.RAIZ / "ferramentas" / "camada.py"
REMOTO = "/tmp/inbox-{tid}"


def _cfg() -> dict:
    return db.config().get("camadas", {})


def _pacote(tid: str):
    from .runner import ENTREGAS  # evita import circular
    return ENTREGAS / tid


def plano_de_deploy(t: dict, entregues: list[str]) -> dict:
    tem_manifesto = "camadas.json" in entregues
    return {
        "tipo": "camada", "etapa": "teste",
        "resumo": (f"Subir no {workspaces.TESTE['nome']} pra você conferir no mapa." if tem_manifesto else
                   "O agente não deixou o camadas.json: não dá pra subir. Peça o ajuste na conversa."),
        "passos": [f"Subir no {workspaces.TESTE['nome']}", "Você confere no mapa",
                   f"Copiar pro workspace do cliente ({(t.get('ficha') or {}).get('workspace', {}).get('nome', '?')})",
                   "Conferir no banco (só leitura)"],
    }


def _rodar(tid: str, *argumentos: str, somente_leitura: bool = False) -> dict:
    """Manda o pacote pro servidor e roda o carregador num container descartável."""
    if not _cfg().get("gravarEmProd"):
        raise RuntimeError("Gravar camada em prod ainda não foi liberado (config camadas.gravarEmProd).")
    remoto = REMOTO.format(tid=tid)
    pacote = _pacote(tid)
    arquivos = [str(p) for p in pacote.iterdir() if p.is_file() and p.suffix in (".json", ".geojson")]
    prod.rodar(f"rm -rf {remoto} && mkdir -p {remoto}", timeout=60)
    destino = f"{prod.ssh()[-1]}:{remoto}/"
    r = subprocess.run(["scp", "-o", "BatchMode=yes", "-q", str(FERRAMENTA), *arquivos, destino],
                       capture_output=True, text=True, timeout=300,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0:
        raise RuntimeError(f"scp falhou: {(r.stderr or r.stdout).strip()[-300:]}")
    leitura = "-e PGOPTIONS='-c default_transaction_read_only=on' " if somente_leitura else ""
    email = _cfg().get("email")
    comando = (f"cd /home/ubuntu/geodriva && docker compose -f docker-compose.backend.yml run --rm --no-deps -T "
               f"-e PYTHONPATH=/app -e CAMADA_WORKSPACE_TESTE={workspaces.TESTE['id']} "
               f"{leitura}{f'-e CAMADA_EMAIL={email} ' if email else ''}"
               f"-v {remoto}:/pkg:ro -w /pkg backend python /pkg/camada.py {' '.join(argumentos)}")
    try:
        saida = prod.rodar(comando, timeout=900)
    except RuntimeError as e:
        saida = str(e)
    linha = next((l for l in reversed(saida.splitlines()) if l.startswith("@@")), None)
    if not linha:
        raise RuntimeError(f"o carregador não respondeu: {saida.strip()[-400:]}")
    resultado = json.loads(linha[2:])
    if not resultado.get("ok"):
        raise RuntimeError(resultado.get("erro") or "o carregador recusou")
    return resultado


def subir_no_teste(tid: str) -> dict:
    t = db.tarefa(tid)
    res = t.get("resultado") or {}
    anteriores = ",".join(c["id"] for c in (res.get("camadasTeste") or []))
    r = _rodar(tid, "subir", workspaces.TESTE["id"], *([anteriores] if anteriores else []))
    conf = _rodar(tid, "conferir", workspaces.TESTE["id"], ",".join(c["id"] for c in r["criadas"]), somente_leitura=True)
    nomes = ", ".join(f"{c['nome']} ({c['feicoes']} feições)" for c in r["criadas"])
    deploy = {**res["deploy"], "etapa": "cliente",
              "resumo": f"Está no {workspaces.TESTE['nome']}: {nomes}. Confira no mapa (recarregue: a lista tem "
                        f"cache de 1 min). Liberando, copio pro workspace do cliente."}
    t = db.atualizar_tarefa(tid, esperando=None, resultado={**res, "camadasTeste": r["criadas"],
                                                            "conferenciaTeste": conf["camadas"], "deploy": deploy})
    barramento.publicar("tarefa", tarefa=t)
    barramento.publicar("evento", evento=db.registrar_evento(f"Camada no {workspaces.TESTE['nome']}", tarefa=tid))
    barramento.publicar("aviso", aviso="deploy", tarefa=t)
    return r


def copiar_para_cliente(tid: str) -> dict:
    t = db.tarefa(tid)
    res = t.get("resultado") or {}
    cliente = (t.get("ficha") or {}).get("workspace") or {}
    if not cliente.get("id"):
        raise RuntimeError("A ficha não tem o workspace do cliente.")
    ids = ",".join(c["id"] for c in (res.get("camadasTeste") or []))
    if not ids:
        raise RuntimeError("Nada no workspace de teste pra copiar.")
    r = _rodar(tid, "copiar", workspaces.TESTE["id"], cliente["id"], ids)
    conf = _rodar(tid, "conferir", cliente["id"], ",".join(c["id"] for c in r["criadas"]), somente_leitura=True)
    t = db.atualizar_tarefa(tid, resultado={**res, "camadasCliente": r["criadas"], "conferenciaCliente": conf["camadas"]})
    barramento.publicar("tarefa", tarefa=t)
    return r


def fazer_deploy(tid: str) -> bool:
    """1º clique sobe no teste; 2º copia pro cliente. True quando chegou no cliente."""
    etapa = (db.tarefa(tid).get("resultado") or {}).get("deploy", {}).get("etapa")
    if etapa == "cliente":
        copiar_para_cliente(tid)
        return True
    subir_no_teste(tid)
    return False


def depois_da_execucao(tid: str) -> None:
    """Com o carregador liberado, o passo 1 (teste) não espera clique: você já recebe pra conferir no mapa."""
    if not _cfg().get("gravarEmProd") or not _cfg().get("testeSozinho", True):
        return
    try:
        subir_no_teste(tid)
    except Exception as e:  # noqa: BLE001
        barramento.publicar("fala", texto=f"{tid}: não consegui subir no workspace de teste ({str(e)[:160]}).")
