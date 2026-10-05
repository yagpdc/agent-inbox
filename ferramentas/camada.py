#!/usr/bin/env python3
"""Carregador de camadas do Inbox Agent. Fixo e revisado: o agente só produz os dados.

Roda DENTRO de um container descartável do backend de prod (não toca no backend no ar):

  cd /home/ubuntu/geodriva && docker compose -f docker-compose.backend.yml run --rm --no-deps -T \
    -e PYTHONPATH=/app -v /tmp/inbox-T-061:/pkg:ro -w /pkg backend python /pkg/camada.py <comando> ...

Comandos:
  listar   <ws>
  subir    <ws> [ids-anteriores]   sobe as camadas de camadas.json. ids-anteriores (só no workspace de teste):
                                   camadas que ESTA tarefa subiu antes e podem ser trocadas. Qualquer outro nome
                                   repetido ABORTA.
  copiar   <ws-origem> <ws-destino> <id,id>   copia pelo id o que o Yago validou; nome repetido no destino ABORTA
  conferir <ws> <id,id>            só leitura: 1 camada por id, contagem e geometrias válidas

A última linha é @@{json} com o resultado, pro Inbox Agent ler.
"""
import json
import os
import sys

from app.database import agro_execute, agro_query
from app.routers.custom_layers import CreateLayerIn, FeatureIn, _create

# workspace onde a camada sobe primeiro pra conferência; só nele dá pra apagar a versão anterior
TESTE = os.environ.get("CAMADA_WORKSPACE_TESTE", "")
EMAIL = os.environ.get("CAMADA_EMAIL", "")
GEOMETRIAS = {"point", "line", "polygon"}


def sair(ok: bool, **dados):
    print("@@" + json.dumps({"ok": ok, **dados}, ensure_ascii=False, default=str))
    sys.exit(0 if ok else 1)


def camadas_do(ws: str) -> dict:
    linhas = agro_query("SELECT id, name, feature_count FROM custom_layers WHERE workspace_id = %s", (ws,))
    return {str(r["id"]): {"nome": r["name"], "feicoes": r["feature_count"]} for r in linhas}


def manifesto() -> list[dict]:
    itens = json.load(open("camadas.json", encoding="utf-8"))
    if not isinstance(itens, list) or not itens:
        sair(False, erro="camadas.json vazio ou fora do formato (lista de camadas).")
    for c in itens:
        falta = [k for k in ("nome", "geometria", "arquivo") if not c.get(k)]
        if falta or c["geometria"] not in GEOMETRIAS:
            sair(False, erro=f"camada fora do formato: {c.get('nome')} (falta {falta or 'geometria válida'})")
        if not os.path.isfile(c["arquivo"]) or "/" in c["arquivo"] or "\\" in c["arquivo"]:
            sair(False, erro=f"arquivo não está no pacote: {c['arquivo']}")
    return itens


def subir(ws: str, anteriores: set[str]):
    itens = manifesto()
    hoje = camadas_do(ws)
    por_nome = {v["nome"]: k for k, v in hoje.items()}
    trocar = []
    for c in itens:
        lid = por_nome.get(c["nome"])
        if lid and not (ws == TESTE and lid in anteriores):
            sair(False, erro=f"já existe camada '{c['nome']}' nesse workspace que não é desta tarefa. Nada foi gravado.")
        if lid:
            trocar.append(lid)
    for lid in trocar:  # só no teste, só o que esta tarefa mesma subiu antes
        agro_execute("DELETE FROM custom_layers WHERE id = %s AND workspace_id = %s", (lid, TESTE))
    criadas = []
    for c in itens:
        fc = json.load(open(c["arquivo"], encoding="utf-8"))
        feicoes = [FeatureIn(geometry=f["geometry"], props=f.get("properties") or {}) for f in fc["features"]]
        meta = _create(ws, EMAIL, CreateLayerIn(name=c["nome"], geometry_type=c["geometria"],
                                                style=c.get("style") or {}, features=feicoes))
        criadas.append({"id": str(meta.get("id")), "nome": c["nome"], "feicoes": len(feicoes)})
    sair(True, workspace=ws, criadas=criadas, trocadas=trocar)


def copiar(origem: str, destino: str, ids: list[str]):
    hoje = camadas_do(destino)
    nomes_destino = {v["nome"] for v in hoje.values()}
    fontes = []
    for lid in ids:
        linha = agro_query("SELECT name, geometry_type, style FROM custom_layers WHERE id = %s AND workspace_id = %s",
                           (lid, origem))
        if not linha:
            sair(False, erro=f"camada {lid} não está no workspace de origem. Nada foi gravado.")
        if linha[0]["name"] in nomes_destino:
            sair(False, erro=f"o cliente já tem uma camada '{linha[0]['name']}'. Nada foi gravado.")
        fontes.append((lid, linha[0]))
    criadas = []
    for lid, meta in fontes:
        feicoes = agro_query("SELECT ST_AsGeoJSON(geom) AS g, props FROM custom_layer_features WHERE layer_id = %s "
                             "ORDER BY id", (lid,))
        style = meta["style"] if isinstance(meta["style"], dict) else json.loads(meta["style"] or "{}")
        novo = _create(destino, EMAIL, CreateLayerIn(
            name=meta["name"], geometry_type=meta["geometry_type"], style=style,
            features=[FeatureIn(geometry=json.loads(f["g"]),
                                props=f["props"] if isinstance(f["props"], dict) else json.loads(f["props"] or "{}"))
                      for f in feicoes]))
        criadas.append({"origem": lid, "id": str(novo.get("id")), "nome": meta["name"], "feicoes": len(feicoes)})
    sair(True, workspace=destino, criadas=criadas)


def conferir(ws: str, ids: list[str]):
    so_leitura = agro_query("SHOW default_transaction_read_only")[0]
    if list(so_leitura.values())[0] != "on":
        sair(False, erro="conferir precisa rodar em sessão só leitura (PGOPTIONS).")
    resultado = []
    for lid in ids:
        meta = agro_query("SELECT name, feature_count FROM custom_layers WHERE id = %s AND workspace_id = %s", (lid, ws))
        if not meta:
            sair(False, erro=f"camada {lid} não encontrada no workspace.")
        linhas = agro_query("SELECT COUNT(*) AS n, COUNT(*) FILTER (WHERE NOT ST_IsValid(geom)) AS invalidas "
                            "FROM custom_layer_features WHERE layer_id = %s", (lid,))[0]
        resultado.append({"id": lid, "nome": meta[0]["name"], "feicoes": linhas["n"],
                          "declaradas": meta[0]["feature_count"], "invalidas": linhas["invalidas"]})
    ok = all(r["feicoes"] == r["declaradas"] and r["feicoes"] > 0 and r["invalidas"] == 0 for r in resultado)
    sair(ok, workspace=ws, camadas=resultado)


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        sair(False, erro="sem comando")
    cmd, resto = args[0], args[1:]
    if cmd == "listar" and len(resto) == 1:
        sair(True, workspace=resto[0], camadas=camadas_do(resto[0]))
    elif cmd == "subir" and len(resto) in (1, 2):
        subir(resto[0], set(filter(None, (resto[1] if len(resto) == 2 else "").split(","))))
    elif cmd == "copiar" and len(resto) == 3:
        copiar(resto[0], resto[1], [i for i in resto[2].split(",") if i])
    elif cmd == "conferir" and len(resto) == 2:
        conferir(resto[0], [i for i in resto[1].split(",") if i])
    else:
        sair(False, erro=f"comando inválido: {' '.join(args)}")
