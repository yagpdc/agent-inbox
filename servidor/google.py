"""Login no Google (OAuth para app de computador, com PKCE) e chamadas REST.

  python -m servidor login     abre o navegador uma vez; o token fica em credenciais/token.json

Nada disso sai da máquina além das chamadas para o próprio Google.
"""

import base64
import hashlib
import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from . import db

PASTA = db.RAIZ / "credenciais"
CLIENTE = PASTA / "google-oauth.json"
TOKEN = PASTA / "token.json"

ESCOPOS = [
    "https://www.googleapis.com/auth/chat.messages.readonly",
    "https://www.googleapis.com/auth/chat.spaces.readonly",
    "https://www.googleapis.com/auth/chat.messages.create",
    "https://www.googleapis.com/auth/directory.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]

_trava = threading.Lock()


class SemLogin(Exception):
    """Ainda não rodou `python -m servidor login` (ou o acesso foi revogado)."""


def _cliente() -> dict:
    return json.loads(CLIENTE.read_text(encoding="utf-8"))["installed"]


def _post_form(url: str, dados: dict) -> dict:
    corpo = urllib.parse.urlencode(dados).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=corpo), timeout=30) as r:
        return json.loads(r.read())


def _salvar(token: dict) -> None:
    token["expira_em"] = time.time() + token.get("expires_in", 3600) - 60
    TOKEN.write_text(json.dumps(token), encoding="utf-8")


def tem_login() -> bool:
    return TOKEN.exists()


# ---------------- login (uma vez) ----------------

def login() -> None:
    cli = _cliente()
    verificador = secrets.token_urlsafe(64)
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    estado = secrets.token_urlsafe(16)
    recebido: dict = {}

    class Retorno(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            recebido.update({k: v[0] for k, v in q.items()})
            ok = "code" in q and q.get("state", [""])[0] == estado
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "Pronto. Pode fechar esta aba." if ok else "Não deu certo. Volte ao terminal."
            self.wfile.write(f"<p style='font-family:sans-serif'>Inbox Agent: {msg}</p>".encode())

    servidor = HTTPServer(("127.0.0.1", 0), Retorno)
    redirect = f"http://127.0.0.1:{servidor.server_port}"
    url = cli["auth_uri"] + "?" + urllib.parse.urlencode({
        "client_id": cli["client_id"],
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": " ".join(ESCOPOS),
        "access_type": "offline",
        "prompt": "consent",
        "code_challenge": desafio,
        "code_challenge_method": "S256",
        "state": estado,
    })
    print("Abrindo o navegador para o login do Google...")
    print(f"Se não abrir, acesse:\n{url}\n")
    webbrowser.open(url)
    while "code" not in recebido and "error" not in recebido:
        servidor.handle_request()
    servidor.server_close()

    if recebido.get("state") != estado or "code" not in recebido:
        raise SystemExit(f"Login cancelado: {recebido.get('error', 'resposta inválida')}")

    token = _post_form(cli["token_uri"], {
        "client_id": cli["client_id"],
        "client_secret": cli["client_secret"],
        "code": recebido["code"],
        "code_verifier": verificador,
        "grant_type": "authorization_code",
        "redirect_uri": redirect,
    })
    PASTA.mkdir(exist_ok=True)
    _salvar(token)
    faltando = set(ESCOPOS) - set(token.get("scope", "").split())
    print("Login feito." + (f" Atenção, sem permissão para: {', '.join(faltando)}" if faltando else ""))


# ---------------- token e chamadas ----------------

def _token_valido() -> str:
    with _trava:
        if not TOKEN.exists():
            raise SemLogin("Faça o login: python -m servidor login")
        token = json.loads(TOKEN.read_text(encoding="utf-8"))
        if time.time() < token.get("expira_em", 0):
            return token["access_token"]
        cli = _cliente()
        try:
            novo = _post_form(cli["token_uri"], {
                "client_id": cli["client_id"],
                "client_secret": cli["client_secret"],
                "refresh_token": token["refresh_token"],
                "grant_type": "refresh_token",
            })
        except urllib.error.HTTPError as e:
            raise SemLogin(f"O login expirou ou foi revogado ({e.code}). Rode: python -m servidor login") from e
        token.update(novo)
        _salvar(token)
        return token["access_token"]


def chamar(metodo: str, url: str, params: dict | None = None, corpo: dict | None = None) -> dict:
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(url, data=dados, method=metodo)
    req.add_header("Authorization", f"Bearer {_token_valido()}")
    if dados:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        detalhe = e.read().decode(errors="replace")[:300]
        raise RuntimeError(f"Google {e.code} em {url.split('?')[0]}: {detalhe}") from e
