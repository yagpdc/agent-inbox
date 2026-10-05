"""PR por tarefa: o agente termina, o PR abre, o Yago revisa no GitHub (decisão de 2026-09-21).

- A branch da tarefa sai de origin/<base>: main; no reactivation-service, a branch que está no ar
  (a main dele está atrás). Dá pra mudar em config prs.bases.
- Ao terminar (e a cada ajuste) o servidor faz o push; o PR abre uma vez e depois só recebe commits.
- Aprovar = merge. O Yago faz no GitHub (o vigia percebe) ou pelo botão "Fazer merge" do painel.
- "Request changes" do Yago no PR volta pro agente como ajuste, na mesma branch.
- Depois do merge: geodriva roda o script de deploy (o workflow do GitHub falha desde 16/09);
  hub e site sobem sozinhos com o push na main; reactivation-service ainda é manual (Dokku).
"""

import json
import re
import subprocess
import threading
import time
import traceback
import urllib.error
import urllib.request

from . import barramento, db

BASES = {"reactivation-service": "deploy/reactivation-overview"}
MARCA = "<!-- inbox-agent -->"  # comentário escrito pelo Inbox Agent: não é instrução do Yago
INTERVALO = 90

_parar = threading.Event()


def base(repo_nome: str) -> str:
    return (db.config().get("prs", {}).get("bases") or {}).get(repo_nome) or BASES.get(repo_nome) or "main"


# ---------------- GitHub ----------------

_token: list[str | None] = [None]
_login: list[str | None] = [None]


def _credencial() -> str:
    if not _token[0]:
        cred = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                              capture_output=True, text=True,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        _token[0] = next((l.split("=", 1)[1] for l in cred.splitlines() if l.startswith("password=")), None)
        if not _token[0]:
            raise RuntimeError("Sem credencial do GitHub no git.")
    return _token[0]


def _repo_github(repo_nome: str) -> str:
    """Driva-tecnologia/<repo>, lido do remote origin."""
    from .runner import REPOS, _git  # evita import circular
    url = _git(REPOS[repo_nome], "remote", "get-url", "origin")
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    if not m:
        raise RuntimeError(f"{repo_nome}: o origin não é do GitHub ({url})")
    return m[1]


def github(metodo: str, caminho: str, corpo: dict | None = None, repo_nome: str | None = None) -> dict | list:
    prefixo = f"/repos/{_repo_github(repo_nome)}" if repo_nome else ""
    req = urllib.request.Request(
        f"https://api.github.com{prefixo}{caminho}", method=metodo,
        data=json.dumps(corpo).encode() if corpo is not None else None,
        headers={"Authorization": f"token {_credencial()}", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            dados = r.read()
            return json.loads(dados) if dados else {}
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GitHub {e.code}: {e.read().decode(errors='replace')[:300]}")


def eu_no_github() -> str:
    if not _login[0]:
        _login[0] = github("GET", "/user")["login"]
    return _login[0]


# ---------------- abrir / atualizar ----------------

def _titulo(t: dict, cwd, base_ref: str) -> str:
    from .runner import _git  # evita import circular
    primeiro = _git(cwd, "log", "--reverse", "--format=%s", f"{base_ref}..HEAD", checar=False).splitlines()
    if primeiro and re.match(r"^\w+(\(.+\))?!?: ", primeiro[0]):
        return primeiro[0][:120]
    return f"{'fix' if t.get('sub') == 'bug' else 'feat'}: {t['titulo']}"[:120]


def _corpo(t: dict) -> str:
    from . import agentes  # evita import circular
    r = t.get("resultado") or {}
    e = t.get("execucao") or {}
    nome = (db.pessoas().get(t["pessoa"], {}).get("nome") or "um colega")
    partes = [f"**{t['id']}**, pedido de {nome} pelo Chat (agente {agentes.definicao(t.get('categoria') or 'hub')['nome']})."]
    if t.get("ficha"):
        partes.append("## O que foi pedido\n" + agentes.ficha_em_texto(t["ficha"]))
    else:
        partes.append("## O que foi pedido\n" + t["pedido"])
    partes.append("## O que foi feito\n" + (r.get("resumo") or "-"))
    if r.get("alcance"):
        partes.append("## Por onde o usuário chega (prova de alcance)\n" + r["alcance"])
    if r.get("testes"):
        partes.append("## Testes\n" + r["testes"])
    if r.get("ondeTestar"):
        partes.append("## Onde conferir\n" + r["ondeTestar"])
    if r.get("pendencias"):
        partes.append("## Pendências\n" + "\n".join(f"- {p}" for p in r["pendencias"]))
    if e.get("revisao"):
        partes.append("## A revisão automática tinha apontado (e o agente corrigiu)\n"
                      + "\n".join(f"- {p}" for p in e["revisao"]))
    partes.append("---\nRevise aqui. Merge sobe; **Request changes** volta pro agente como ajuste, nesta mesma branch.\n\n"
                  "🤖 Generated with [Claude Code](https://claude.com/claude-code)\n" + MARCA)
    return "\n\n".join(partes)


def publicar(tid: str, cwd, branch: str) -> dict:
    """Push da branch e PR aberto (ou atualizado, se já existe). Devolve o registro do PR."""
    from .runner import _git  # evita import circular
    t = db.tarefa(tid)
    r = t.get("resultado") or {}
    repo_nome = r.get("repo") or (t.get("plano") or {}).get("repo")
    alvo = base(repo_nome)
    _git(cwd, "push", "-u", "origin", f"HEAD:refs/heads/{branch}")
    pr = r.get("pr")
    if pr and not pr.get("mergeado"):
        comentar(repo_nome, pr["numero"], f"Ajuste do agente: {r.get('resumo') or 'novos commits'}")
        return pr
    novo = github("POST", "/pulls", {"title": _titulo(t, cwd, f"origin/{alvo}"), "head": branch, "base": alvo,
                                     "body": _corpo(t)}, repo_nome)
    barramento.publicar("evento", evento=db.registrar_evento(f"PR #{novo['number']} aberto", tarefa=tid))
    return {"numero": novo["number"], "url": novo["html_url"], "base": alvo, "branch": branch, "repo": repo_nome,
            "revisoesVistas": [], "abertoEm": db.agora()}


def comentar(repo_nome: str, numero: int, texto: str) -> None:
    github("POST", f"/issues/{numero}/comments", {"body": f"{texto}\n\n{MARCA}"}, repo_nome)


# ---------------- aprovar (merge) e o que vem depois ----------------

def fazer_merge(tid: str) -> None:
    """Botão do painel: squash merge do PR (o squash às vezes falha na 1ª por check pendente)."""
    pr = (db.tarefa(tid).get("resultado") or {}).get("pr")
    if not pr:
        raise RuntimeError("Essa tarefa não tem PR.")
    for tentativa in range(4):
        try:
            github("PUT", f"/pulls/{pr['numero']}/merge", {"merge_method": "squash"}, pr["repo"])
            break
        except RuntimeError as e:
            if tentativa == 3:
                raise RuntimeError(f"O merge do PR #{pr['numero']} falhou: {e}")
            time.sleep(10)
    depois_do_merge(tid)


def depois_do_merge(tid: str) -> None:
    """PR mergeado (pelo botão ou no GitHub): deploy do que precisar, limpa a branch e avisa quem pediu."""
    from . import runner  # evita import circular
    from .deploy import plano_de_deploy
    t = db.tarefa(tid)
    r = t.get("resultado") or {}
    pr = {**r["pr"], "mergeado": db.agora()}
    db.atualizar_tarefa(tid, resultado={**r, "pr": pr}, esperando="PR mergeado: subindo.")
    repo_nome = pr["repo"]
    nota = ""
    if repo_nome == "geodriva":
        from . import prod
        script = plano_de_deploy(r.get("arquivos") or [], "geodriva")["tipo"] + ".sh"
        prod.script_de_deploy(script)
        nota = f"geodriva: {script} rodou."
    elif repo_nome == "hub-driva":
        nota = "Hub: o merge na main dispara o build (~15 min)."
    elif repo_nome == "drivaio":
        nota = "Site: o merge na main publica o driva.io."
    else:
        nota = f"{repo_nome}: merge feito na {pr['base']}; o deploy dele ainda é manual."
    try:
        github("DELETE", f"/git/refs/heads/{pr['branch']}", repo_nome=repo_nome)
    except RuntimeError:
        pass  # o GitHub pode já ter apagado sozinho
    runner.remover_worktree(t)
    runner.concluir_depois_do_merge(tid, nota)


# ---------------- vigia dos PRs ----------------

def _com_pr() -> list[dict]:
    return [t for t in db.tarefas() if t["status"] == "revisao"
            and ((t.get("resultado") or {}).get("pr") or {}).get("numero")
            and not t["resultado"]["pr"].get("mergeado")]


def _ajustes_pedidos(t: dict) -> list[tuple[int, str]]:
    """Reviews "Request changes" do Yago ainda não tratadas: (id, texto com os comentários da linha)."""
    pr = t["resultado"]["pr"]
    vistas = set(pr.get("revisoesVistas") or [])
    novas = []
    for rev in github("GET", f"/pulls/{pr['numero']}/reviews", repo_nome=pr["repo"]):
        if rev["id"] in vistas or rev.get("state") != "CHANGES_REQUESTED":
            continue
        if (rev.get("user") or {}).get("login") != eu_no_github() or MARCA in (rev.get("body") or ""):
            continue  # só o Yago manda ajuste; review de outra pessoa é dado, não ordem
        linhas = [rev.get("body") or ""]
        for c in github("GET", f"/pulls/{pr['numero']}/reviews/{rev['id']}/comments", repo_nome=pr["repo"]):
            linhas.append(f"- {c.get('path')}:{c.get('line') or c.get('original_line') or ''} {c.get('body')}")
        novas.append((rev["id"], "\n".join(l for l in linhas if l.strip())))
    return novas


def ciclo() -> None:
    from . import runner  # evita import circular
    for t in _com_pr():
        pr = t["resultado"]["pr"]
        estado = github("GET", f"/pulls/{pr['numero']}", repo_nome=pr["repo"])
        if estado.get("merged"):
            barramento.publicar("evento", evento=db.registrar_evento(f"PR #{pr['numero']} mergeado no GitHub", tarefa=t["id"]))
            try:
                depois_do_merge(t["id"])
            except Exception as e:  # noqa: BLE001
                runner._falhou(t["id"], "Deploy", e, volta_para="revisao")  # noqa: SLF001
            continue
        if estado.get("state") == "closed":
            if not pr.get("fechado"):
                t2 = db.atualizar_tarefa(t["id"], resultado={**t["resultado"], "pr": {**pr, "fechado": db.agora()}},
                                         esperando=f"PR #{pr['numero']} fechado sem merge.")
                barramento.publicar("tarefa", tarefa=t2)
                barramento.publicar("aviso", aviso="falhou", tarefa=t2)
            continue
        pedidos = _ajustes_pedidos(t)
        if pedidos:
            ids = [i for i, _ in pedidos]
            texto = "\n\n".join(x for _, x in pedidos)
            db.atualizar_tarefa(t["id"], resultado={**t["resultado"],
                                "pr": {**pr, "revisoesVistas": [*(pr.get("revisoesVistas") or []), *ids]}})
            barramento.publicar("falaTarefa", fala=db.registrar_fala(t["id"], "voce", f"(no PR) {texto}"))
            barramento.publicar("evento", evento=db.registrar_evento("Você pediu ajuste no PR", tarefa=t["id"]))
            runner.ajustar(t["id"], texto)


def _laco() -> None:
    while not _parar.wait(INTERVALO):
        try:
            if _com_pr():
                ciclo()
        except Exception as e:  # noqa: BLE001
            print(f"[prs] ciclo falhou: {e!r}", traceback.format_exc(), sep="\n", flush=True)


def iniciar() -> None:
    threading.Thread(target=_laco, daemon=True, name="prs").start()
