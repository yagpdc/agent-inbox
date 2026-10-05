"""Google Agenda: compromissos do dia e sugestões. Só é lida quando você pede pelo pet.

Sugestão = quem está na reunião e tem pedido aberto com você ("André tem 2 pedidos abertos").
Precisa do escopo calendar.readonly (python -m servidor login de novo, se o token for antigo).
"""

import unicodedata
from datetime import datetime, timedelta

from . import db, google

API = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
SEM_PERMISSAO = "Sem permissão pra ler a agenda. Rode o login do Google de novo (python -m servidor login)."
API_DESLIGADA = "A Google Calendar API está desativada no projeto do Google Cloud. Ative e tente de novo."


def mensagem_de_erro(e: Exception) -> str:
    texto = str(e)
    if " 403 " in texto:
        return API_DESLIGADA if ("has not been used" in texto or "is disabled" in texto) else SEM_PERMISSAO
    return texto[:300]


def _hora(ev: dict, campo: str) -> datetime | None:
    d = ev.get(campo, {})
    return datetime.fromisoformat(d["dateTime"]) if "dateTime" in d else None  # sem hora = dia inteiro


def _link_video(ev: dict) -> str | None:
    if ev.get("hangoutLink"):
        return ev["hangoutLink"]
    pontos = ev.get("conferenceData", {}).get("entryPoints", [])
    return next((p.get("uri") for p in pontos if p.get("entryPointType") == "video"), None)


def eventos(de: datetime, ate: datetime) -> list[dict]:
    r = google.chamar("GET", API, {
        "timeMin": de.isoformat(), "timeMax": ate.isoformat(),
        "singleEvents": "true", "orderBy": "startTime", "maxResults": 50,
    })
    saida = []
    for ev in r.get("items", []):
        if ev.get("status") == "cancelled":
            continue
        eu = next((a for a in ev.get("attendees", []) if a.get("self")), None)
        if eu and eu.get("responseStatus") == "declined":
            continue
        inicio, fim = _hora(ev, "start"), _hora(ev, "end")
        saida.append({
            "id": ev["id"],
            "titulo": ev.get("summary") or "(sem título)",
            "inicio": inicio.isoformat() if inicio else None,
            "fim": fim.isoformat() if fim else None,
            "diaInteiro": inicio is None,
            "link": _link_video(ev),
            "url": ev.get("htmlLink"),
            "pessoas": [
                {"nome": a.get("displayName") or a.get("email", "").split("@")[0], "email": a.get("email")}
                for a in ev.get("attendees", []) if not a.get("self") and not a.get("resource")
            ],
        })
    return saida


def hoje() -> list[dict]:
    inicio = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    pessoas = db.pessoas()
    saida = []
    for e in eventos(inicio, inicio + timedelta(days=1)):
        for c in e["pessoas"]:  # a agenda costuma trazer só o e-mail: usa o nome de quem já conhecemos do Chat
            pid = _pessoa_do_convidado(c, pessoas)
            if pid:
                c["nome"] = pessoas[pid]["nome"]
        saida.append({**e, "sugestoes": sugestoes(e)})
    return saida


# ---------------- sugestões ----------------

def _tokens(texto: str) -> list[str]:
    s = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return [p for p in "".join(ch if ch.isalnum() else " " for ch in s).split() if p]


def _pessoa_do_convidado(convidado: dict, pessoas: dict) -> str | None:
    email = (convidado.get("email") or "").lower()
    for pid, p in pessoas.items():
        if email and (p.get("email") or "").lower() == email:
            return pid
    alvo = set(_tokens(convidado["nome"])) | set(_tokens(email.split("@")[0]))
    for pid, p in pessoas.items():
        t = _tokens(p["nome"])
        if len(t) >= 2 and t[0] in alvo and t[-1] in alvo:
            return pid
    return None


def sugestoes(ev: dict) -> list[dict]:
    """Pedidos abertos de quem está na reunião: bom momento pra resolver ou dar retorno."""
    pessoas = db.pessoas()
    abertas = [t for t in db.tarefas() if t["status"] != "feito"]
    saida = []
    for convidado in ev["pessoas"]:
        pid = _pessoa_do_convidado(convidado, pessoas)
        dele = [t for t in abertas if t["pessoa"] == pid] if pid else []
        if dele:
            nome = pessoas[pid]["nome"].split(" ")[0]
            plural = "pedidos abertos" if len(dele) > 1 else "pedido aberto"
            saida.append({
                "texto": f"{nome} tem {len(dele)} {plural} com você. Dá pra dar retorno na reunião.",
                "tarefas": [{"id": t["id"], "titulo": t["titulo"]} for t in dele[:3]],
            })
    return saida
