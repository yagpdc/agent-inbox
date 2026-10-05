"""Google Chat (com o login do Yago) + nomes pela People API."""

import json
from functools import lru_cache

from .google import chamar

CHAT = "https://chat.googleapis.com/v1"
PEOPLE = "https://people.googleapis.com/v1"


def espacos() -> list[dict]:
    """DMs e espaços em que o Yago está (só os que tiveram atividade recente importam)."""
    todos, pagina = [], None
    while True:
        r = chamar("GET", f"{CHAT}/spaces", {"pageSize": 1000, "pageToken": pagina})
        todos += r.get("spaces", [])
        pagina = r.get("nextPageToken")
        if not pagina:
            return todos


def mensagens(espaco: str, desde_rfc3339: str, limite: int = 1000) -> list[dict]:
    """Todas as mensagens desde a data, da mais velha pra mais nova (paginando: a API devolve 100 por vez)."""
    todas, pagina = [], None
    while len(todas) < limite:
        params = {"filter": f'createTime > "{desde_rfc3339}"', "orderBy": "createTime asc", "pageSize": 100}
        if pagina:
            params["pageToken"] = pagina
        r = chamar("GET", f"{CHAT}/{espaco}/messages", params)
        todas += r.get("messages", [])
        pagina = r.get("nextPageToken")
        if not pagina:
            break
    return todas[:limite]


def ultimas(espaco: str, quantas: int = 8) -> list[dict]:
    r = chamar("GET", f"{CHAT}/{espaco}/messages", {"orderBy": "createTime desc", "pageSize": quantas})
    return list(reversed(r.get("messages", [])))


_tipos: dict[str, str] = {}


def tipo_do_espaco(espaco: str) -> str:
    """DIRECT_MESSAGE | GROUP_CHAT | SPACE (guardado depois da primeira consulta)."""
    if espaco not in _tipos:
        _tipos[espaco] = chamar("GET", f"{CHAT}/{espaco}").get("spaceType", "SPACE")
    return _tipos[espaco]


def baixar_anexo(anexo: dict) -> bytes | None:
    """Conteúdo de um anexo enviado no Chat (imagens, arquivos). None se não for baixável."""
    import urllib.parse
    import urllib.request

    from .google import _token_valido

    ref = (anexo.get("attachmentDataRef") or {}).get("resourceName")
    if not ref:
        return None  # ex.: arquivo do Drive, que não vem por aqui
    url = f"{CHAT}/media/{urllib.parse.quote(ref, safe='')}?alt=media"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {_token_valido()}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def enviar(espaco: str, texto: str, thread: str | None = None) -> dict:
    corpo = {"text": texto}
    params = None
    if thread:
        corpo["thread"] = {"name": thread}
        params = {"messageReplyOption": "REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD"}
    enviada = chamar("POST", f"{CHAT}/{espaco}/messages", params, corpo)
    _registrar_do_assistente(enviada)
    return enviada


def enviar_arquivo(espaco: str, caminho, texto: str = "", thread: str | None = None) -> dict:
    """Sobe um arquivo pro Chat e manda como anexo (imagem aparece com prévia, o resto como arquivo)."""
    import mimetypes
    import urllib.request
    import uuid
    from pathlib import Path

    from .google import _token_valido  # noqa: PLC2701 — mesmo token do resto do Chat

    caminho = Path(caminho)
    tipo = mimetypes.guess_type(caminho.name)[0] or "application/octet-stream"
    fronteira = uuid.uuid4().hex
    corpo = (
        f"--{fronteira}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
        + json.dumps({"filename": caminho.name})
        + f"\r\n--{fronteira}\r\nContent-Type: {tipo}\r\n\r\n"
    ).encode() + caminho.read_bytes() + f"\r\n--{fronteira}--\r\n".encode()
    req = urllib.request.Request(
        f"https://chat.googleapis.com/upload/v1/{espaco}/attachments:upload?uploadType=multipart",
        data=corpo, method="POST",
        headers={"Authorization": f"Bearer {_token_valido()}",
                 "Content-Type": f"multipart/related; boundary={fronteira}"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        subido = json.loads(r.read())
    mensagem = {"text": texto, "attachment": [subido]}
    params = None
    if thread:
        mensagem["thread"] = {"name": thread}
        params = {"messageReplyOption": "REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD"}
    enviada = chamar("POST", f"{CHAT}/{espaco}/messages", params, mensagem)
    _registrar_do_assistente(enviada)
    return enviada


def _registrar_do_assistente(m: dict) -> None:
    """A mensagem sai com o usuário do Yago; guardamos o id pra não confundir com ele respondendo."""
    from . import db  # evita import circular
    if not m.get("name"):
        return
    with db._trava:  # noqa: SLF001
        db.con().execute(
            "INSERT OR REPLACE INTO mensagens(id, espaco, pessoa, texto, recebida_em, classificacao, tarefa) VALUES (?, ?, NULL, ?, ?, 'assistente', NULL)",
            (m["name"], m["name"].split("/messages/")[0], m.get("text", ""), m.get("createTime", "")),
        )
        db.con().commit()


def do_assistente(m: dict) -> bool:
    """Foi o assistente (e não o Yago) que mandou? Pelo registro do envio ou, nas antigas, pela assinatura."""
    from . import db  # evita import circular
    with db._trava:  # noqa: SLF001
        if db.con().execute("SELECT 1 FROM mensagens WHERE id = ? AND classificacao = 'assistente'", (m.get("name"),)).fetchone():
            return True
    return "assistente do Yago" in m.get("text", "")


@lru_cache(maxsize=1)
def meu_usuario() -> str:
    """users/<id> do Yago: a única pessoa que aparece em todas as DMs recentes. Fica guardado."""
    from . import db  # evita import circular

    salvo = db.config().get("vigia", {}).get("eu")
    if salvo:
        return salvo

    dms = sorted(
        (e for e in espacos() if e.get("spaceType") == "DIRECT_MESSAGE" and e.get("lastActiveTime")),
        key=lambda e: e["lastActiveTime"], reverse=True,
    )
    comum = None
    for esp in dms[:15]:
        autores = {m["sender"]["name"] for m in ultimas(esp["name"], 30) if m.get("sender", {}).get("type") == "HUMAN"}
        if len(autores) < 2:
            continue  # precisa de mensagem dos dois lados
        comum = autores if comum is None else comum & autores
        if comum is not None and len(comum) == 1:
            eu = next(iter(comum))
            db.salvar_config("vigia", {"eu": eu})
            return eu
    raise RuntimeError("Não consegui descobrir o seu usuário no Chat.")


_perfis: dict[str, dict] = {}


def perfil(usuario: str) -> dict | None:
    """users/<id> -> {"nome", "foto", "email"}. None se a People API não responder (tenta de novo na próxima)."""
    if usuario in _perfis:
        return _perfis[usuario]
    try:
        r = chamar("GET", f"{PEOPLE}/people/{usuario.split('/')[1]}", {
            "personFields": "names,photos,emailAddresses",
            "sources": "READ_SOURCE_TYPE_PROFILE",
        })
        fotos = [f for f in r.get("photos", []) if not f.get("default")]
        _perfis[usuario] = {
            "nome": r["names"][0]["displayName"],
            "foto": fotos[0]["url"] if fotos else None,
            "email": next((e["value"] for e in r.get("emailAddresses", []) if e.get("value")), None),
        }
        return _perfis[usuario]
    except Exception:  # noqa: BLE001
        return None


def nome(usuario: str) -> str | None:
    p = perfil(usuario)
    return p["nome"] if p else None
