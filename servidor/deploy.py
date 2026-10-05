"""Regra de deploy, uma por repo.

Fontes: o CLAUDE.md e os guias de deploy de cada repo.

geodriva            sempre `git push origin main` antes; o script depende do que mudou;
                    back e front juntos -> deploy-all (back sobe antes do front).
hub-driva           não tem deploy manual. Você valida no local, a branch entra na
                    atlas-homolog e o PR squash pra main dispara o build (~15 min).
drivaio (site)      push na main do drivaio publica o driva.io sozinho.
reactivation-service  deploy manual (Dokku), fora do Inbox Agent por enquanto.
sem código          nada a subir.
Se um deploy falhar: mostrar o erro e perguntar. Nunca corrigir sozinho em prod.
"""

from . import local  # noqa: E402

SSH = local.valor("deploySsh", "ssh prod 'bash ~/app/scripts/{}'")


def plano_de_deploy(arquivos: list[str], repo: str = "geodriva") -> dict:
    if not arquivos:
        return {"tipo": "nenhum", "resumo": "Sem código alterado. Não há o que subir.", "passos": []}

    if repo == "hub-driva":
        return {
            "tipo": "hub",
            "resumo": "Hub: você valida no local, a branch entra na atlas-homolog e o PR squash pra main dispara o build.",
            "passos": [
                "Você valida no localhost:3000 (atlas-homolog)",
                "npx eslint <arquivos> com 0 erros",
                "git merge --no-ff origin/<branch> na atlas-homolog",
                "PR squash atlas-homolog → main pela API do GitHub (build automático, ~15 min)",
            ],
        }

    if repo == "drivaio":
        return {
            "tipo": "site",
            "resumo": "Site: o push na main do drivaio publica o driva.io automaticamente.",
            "passos": ["git fetch origin main (a main não pode ter andado)", "git push origin HEAD:main (repo drivaio)"],
        }

    if repo == "reactivation-service":
        return {
            "tipo": "manual",
            "resumo": "reactivation-service: deploy manual pelo Dokku (ver o README do serviço).",
            "passos": [],
        }

    back = any(a.startswith("backend/") for a in arquivos)
    front = any(a.startswith("frontend/") for a in arquivos)
    if back and front:
        script, porque = "deploy-all.sh", "Back e front mudaram"
    elif front:
        script, porque = "deploy-front.sh", "Só o frontend mudou"
    else:
        script, porque = "deploy-back.sh", "Só o backend mudou"

    return {
        "tipo": script.removesuffix(".sh"),
        "resumo": f"geodriva: {porque.lower()}, então é o {script}.",
        "passos": ["git push origin main (repo geodriva)", SSH.format(script)],
    }
