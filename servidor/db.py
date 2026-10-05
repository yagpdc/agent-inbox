"""Banco SQLite do Inbox Agent: um arquivo só (inbox-agent/tarefas.db).

Tabelas:
  pessoas    quem manda mensagem no Chat
  tarefas    uma linha por tarefa; plano/execução/resultado ficam em JSON
  eventos    histórico (alimenta "Atividade recente" e as métricas)
  mensagens  o que o vigia leu do Chat e como classificou
  config     preferências (resposta a saudações etc.)
"""

import json
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

from . import local

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO = RAIZ / "tarefas.db"

# Uma conexão compartilhada: toda leitura e escrita passa pela trava
# (o vigia, os agentes e a API usam o banco ao mesmo tempo).
_trava = threading.RLock()

ESQUEMA = """
CREATE TABLE IF NOT EXISTS pessoas (
  id        TEXT PRIMARY KEY,
  nome      TEXT NOT NULL,
  iniciais  TEXT NOT NULL,
  cor       TEXT NOT NULL,
  foto      TEXT,                  -- URL da foto do perfil Google
  chat_id   TEXT UNIQUE            -- users/<id> no Google Chat
);

CREATE TABLE IF NOT EXISTS tarefas (
  id           TEXT PRIMARY KEY,   -- T-042
  titulo       TEXT NOT NULL,
  status       TEXT NOT NULL,      -- identificada | comigo | triagem | pergunta | resposta | aprovacao | execucao | revisao | feito
  tipo         TEXT NOT NULL DEFAULT 'tarefa',  -- tarefa (muda código) | duvida (responde com texto)
  espaco       TEXT,               -- spaces/<id> do Chat, pra responder
  thread       TEXT,
  categoria    TEXT,
  sub          TEXT,
  prioridade   TEXT NOT NULL DEFAULT 'P2',
  pessoa       TEXT NOT NULL REFERENCES pessoas(id),
  pedido       TEXT NOT NULL,
  chat_url     TEXT,
  esperando    TEXT,
  descartada   INTEGER NOT NULL DEFAULT 0,
  plano        TEXT,               -- JSON
  execucao     TEXT,               -- JSON
  resultado    TEXT,               -- JSON
  pergunta     TEXT,               -- JSON: dúvidas do agente esperando você
  resposta     TEXT,               -- JSON: resposta pronta pro Chat {texto, sessao, fontes}
  anexos       TEXT,               -- JSON: imagens/arquivos que vieram no Chat (nomes em anexos/<id>/)
  criada_em    TEXT NOT NULL,
  concluida_em TEXT,
  atualizada_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS tarefas_status ON tarefas(status);

CREATE TABLE IF NOT EXISTS falas (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  tarefa  TEXT NOT NULL REFERENCES tarefas(id),
  quem    TEXT NOT NULL,      -- voce | agente | sistema
  texto   TEXT NOT NULL,
  quando  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS falas_tarefa ON falas(tarefa);

CREATE TABLE IF NOT EXISTS eventos (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  tipo     TEXT,                   -- resposta_dm | NULL
  tarefa   TEXT REFERENCES tarefas(id),
  pessoa   TEXT REFERENCES pessoas(id),
  texto    TEXT NOT NULL,
  detalhe  TEXT,
  quando   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS eventos_quando ON eventos(quando);

CREATE TABLE IF NOT EXISTS mensagens (
  id            TEXT PRIMARY KEY,  -- spaces/<id>/messages/<id>
  espaco        TEXT,
  pessoa        TEXT REFERENCES pessoas(id),
  texto         TEXT NOT NULL,
  recebida_em   TEXT NOT NULL,
  classificacao TEXT,              -- tarefa | complemento | ignorada
  tarefa        TEXT REFERENCES tarefas(id)
);

CREATE TABLE IF NOT EXISTS config (
  chave TEXT PRIMARY KEY,
  valor TEXT NOT NULL              -- JSON
);

-- Um pedido sendo montado pelo orquestrador numa DM, até virar tarefa.
CREATE TABLE IF NOT EXISTS atendimentos (
  id            TEXT PRIMARY KEY,  -- A-012
  espaco        TEXT NOT NULL,
  pessoa        TEXT REFERENCES pessoas(id),
  estado        TEXT NOT NULL,     -- coletando | confirmando | na_espera | despachado | cancelado
  ficha         TEXT,              -- JSON: o pedido do jeito que o agente vai ler
  tarefa        TEXT REFERENCES tarefas(id),
  turnos        INTEGER NOT NULL DEFAULT 0,
  confirmacao_em TEXT,             -- quando o resumo foi mandado pra ela confirmar
  yago_chamado  INTEGER NOT NULL DEFAULT 0,  -- já chamou o Yago por causa deste rascunho
  criado_em     TEXT NOT NULL,
  atualizado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS atendimentos_espaco ON atendimentos(espaco, estado);
"""

CONFIG_PADRAO = {
    "orquestrador": {
        "autonomo": True,   # pedido confirmado pela pessoa já vai pro agente (desligado: espera o seu clique)
        "nome": "Shotoku",  # Príncipe Shōtoku, o mediador: como o orquestrador aparece no painel
        "maxAbertas": 2,    # pedidos em andamento por pessoa; o próximo espera um terminar
        "dominios": local.valor("dominios", []),  # quem pode fazer pedido
    },
    "camadas": {
        "gravarEmProd": False,  # o carregador fixo grava camada em prod (teste e cliente): liberado pelo Yago
        "testeSozinho": True,   # com o carregador liberado, o passo do workspace de teste não espera clique
        "email": "",            # created_by das camadas (vazio = o dos scripts antigos)
    },
    "execucao": {"ligada": True},  # desligada: o orquestrador conversa e cria tarefas, mas nenhum agente começa
    "movel": {"ativo": False},  # mandar as decisões pro Chat do celular (liga quando sair do PC)
    "respostaDm": {
        "ativa": False,  # manda mensagem em nome do Yago: começa desligada
        "inativaMin": 10,  # você escreveu na conversa há menos que isso: ele fica quieto
        "textoConfirmar": "Vou confirmar isso com o Yago e já te retorno por aqui.",
        "textoPendente": "Conferi aqui: isso ainda não está pronto. Já estou montando um plano pra resolver, e o Yago assume em breve.",
        "enviarSemAprovar": False,  # rascunho de resposta (fora de DM) vai só com o seu clique
    },
}

JSON_COLS = ("plano", "execucao", "resultado", "pergunta", "resposta", "anexos", "ficha", "marcos", "origem")

# nome no banco -> nome no front
# categoria = o agente que cuida (site, hub, mapa, camadas, reativacao, duvida)
CAMPOS = {
    "id": "id", "titulo": "titulo", "status": "status", "categoria": "categoria", "sub": "sub",
    "prioridade": "prioridade", "pessoa": "pessoa", "pedido": "pedido", "chat_url": "chatUrl",
    "esperando": "esperando", "descartada": "descartada", "plano": "plano", "execucao": "execucao",
    "resultado": "resultado", "pergunta": "pergunta", "resposta": "resposta", "tipo": "tipo", "anexos": "anexos",
    "espaco": "espaco", "thread": "thread", "criada_em": "criadaEm", "concluida_em": "concluidaEm",
    "ficha": "ficha", "workspace": "workspace", "marcos": "marcos", "atendimento": "atendimento",
    "prazo": "prazo", "pai": "pai", "origem": "origem",
}
PRIORIDADES = {"urgente": "P0", "alta": "P1", "normal": "P2", "baixa": "P3"}  # P0 vai primeiro na fila
DO_FRONT = {v: k for k, v in CAMPOS.items()}


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def conectar() -> sqlite3.Connection:
    con = sqlite3.connect(CAMINHO, timeout=10, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


_con = None


def con() -> sqlite3.Connection:
    global _con
    if _con is None:
        _con = conectar()
    return _con


def iniciar() -> None:
    with _trava:
        c = con()
        c.executescript(ESQUEMA)
        for chave, padrao in CONFIG_PADRAO.items():
            linha = c.execute("SELECT valor FROM config WHERE chave = ?", (chave,)).fetchone()
            atual = json.loads(linha[0]) if linha else {}
            completo = {**padrao, **atual}  # chaves novas entram com o padrão; as suas ficam como estão
            c.execute("INSERT OR REPLACE INTO config(chave, valor) VALUES (?, ?)", (chave, json.dumps(completo, ensure_ascii=False)))
        c.execute("DELETE FROM config WHERE chave IN ('agentes', 'saudacao', 'hubDev')")  # regras antigas
        colunas = {r[1] for r in c.execute("PRAGMA table_info(tarefas)")}
        novas = {
            "pergunta": "TEXT", "resposta": "TEXT", "espaco": "TEXT", "thread": "TEXT", "anexos": "TEXT",
            "tipo": "TEXT NOT NULL DEFAULT 'tarefa'",
            "ficha": "TEXT", "workspace": "TEXT", "marcos": "TEXT", "atendimento": "TEXT",
            "prazo": "TEXT",  # AAAA-MM-DD: quando quem pediu precisa
            "pai": "TEXT",    # subtarefa: id da tarefa-mãe
            "origem": "TEXT",  # JSON: as mensagens exatas que a pessoa mandou no Chat [{quando, texto}]
        }
        for coluna, tipo in novas.items():  # bancos criados antes dessas colunas
            if coluna not in colunas:
                c.execute(f"ALTER TABLE tarefas ADD COLUMN {coluna} {tipo}")
        c.execute("UPDATE tarefas SET categoria = 'hub' WHERE categoria = 'generica'")  # virou o agente hub
        colunas_at = {r[1] for r in c.execute("PRAGMA table_info(atendimentos)")}
        for coluna, tipo in {"confirmacao_em": "TEXT", "yago_chamado": "INTEGER NOT NULL DEFAULT 0"}.items():
            if coluna not in colunas_at:
                c.execute(f"ALTER TABLE atendimentos ADD COLUMN {coluna} {tipo}")
        colunas_pessoas = {r[1] for r in c.execute("PRAGMA table_info(pessoas)")}
        if "foto" not in colunas_pessoas:
            c.execute("ALTER TABLE pessoas ADD COLUMN foto TEXT")
        if "email" not in colunas_pessoas:  # liga convidados da agenda às pessoas do Chat
            c.execute("ALTER TABLE pessoas ADD COLUMN email TEXT")
        c.commit()


# ---------------- tarefas ----------------

def _para_front(linha: sqlite3.Row) -> dict:
    t = {}
    for col, nome in CAMPOS.items():
        valor = linha[col]
        if col in JSON_COLS and valor is not None:
            valor = json.loads(valor)
        if col == "descartada":
            valor = bool(valor)
        t[nome] = valor
    return t


def _inserir_tarefa(c: sqlite3.Connection, t: dict) -> None:
    linha = {DO_FRONT[k]: v for k, v in t.items() if k in DO_FRONT}
    for col in JSON_COLS:
        if linha.get(col) is not None:
            linha[col] = json.dumps(linha[col], ensure_ascii=False)
    linha["atualizada_em"] = agora()
    cols = ", ".join(linha)
    marcas = ", ".join("?" for _ in linha)
    c.execute(f"INSERT OR REPLACE INTO tarefas({cols}) VALUES ({marcas})", list(linha.values()))


def tarefas() -> list[dict]:
    with _trava:
        linhas = con().execute("SELECT * FROM tarefas ORDER BY criada_em DESC").fetchall()
    return [_para_front(l) for l in linhas]


def tarefa(tid: str) -> dict | None:
    with _trava:
        linha = con().execute("SELECT * FROM tarefas WHERE id = ?", (tid,)).fetchone()
    return _para_front(linha) if linha else None


def criar_tarefa(t: dict) -> dict:
    with _trava:
        c = con()
        ids = [r[0] for r in c.execute("SELECT id FROM tarefas")]
        maior = max((int(i.split("-")[1]) for i in ids), default=0)
        t = {"id": f"T-{maior + 1:03d}", "criadaEm": agora(), **t}
        _inserir_tarefa(c, t)
        c.commit()
    return tarefa(t["id"])


def atualizar_tarefa(tid: str, **campos_front) -> dict:
    """Recebe nomes do front (camelCase). None apaga o campo."""
    sets, valores = [], []
    for nome, valor in campos_front.items():
        col = DO_FRONT[nome]
        if col in JSON_COLS and valor is not None:
            valor = json.dumps(valor, ensure_ascii=False)
        if col == "descartada":
            valor = int(bool(valor))
        sets.append(f"{col} = ?")
        valores.append(valor)
    sets.append("atualizada_em = ?")
    valores += [agora(), tid]
    with _trava:
        c = con()
        c.execute(f"UPDATE tarefas SET {', '.join(sets)} WHERE id = ?", valores)
        c.commit()
    return tarefa(tid)


def mensagens_da_tarefa(t: dict) -> list[dict]:
    """O que a pessoa escreveu no Chat que originou a tarefa (o guardado na tarefa, senão o ligado no vigia)."""
    if t.get("origem"):
        return t["origem"]
    with _trava:
        linhas = con().execute(
            "SELECT recebida_em, texto FROM mensagens WHERE tarefa = ? AND pessoa = ? ORDER BY recebida_em",
            (t["id"], t["pessoa"])).fetchall()
    return [{"quando": r["recebida_em"], "texto": r["texto"]} for r in linhas if (r["texto"] or "").strip()]


def mensagens_da_pessoa(espaco: str, pessoa: str, desde_utc: str) -> list[dict]:
    with _trava:
        linhas = con().execute(
            "SELECT recebida_em, texto FROM mensagens WHERE espaco = ? AND pessoa = ? AND recebida_em >= ? ORDER BY recebida_em",
            (espaco, pessoa, desde_utc)).fetchall()
    return [{"quando": r["recebida_em"], "texto": r["texto"]} for r in linhas if (r["texto"] or "").strip()]


def tarefas_abertas_de(pessoa: str) -> list[dict]:
    """Pedidos da pessoa que ainda não terminaram (conta pro limite de pedidos em andamento)."""
    return [t for t in tarefas() if t["pessoa"] == pessoa and t["tipo"] == "tarefa"
            and t["status"] != "feito" and not t["descartada"]]


# ---------------- atendimentos ----------------

ABERTOS = ("coletando", "confirmando", "na_espera")


def _atendimento(linha: sqlite3.Row) -> dict:
    a = dict(linha)
    a["ficha"] = json.loads(a["ficha"]) if a["ficha"] else None
    return a


def atendimento(aid: str) -> dict | None:
    with _trava:
        linha = con().execute("SELECT * FROM atendimentos WHERE id = ?", (aid,)).fetchone()
    return _atendimento(linha) if linha else None


def atendimento_aberto(espaco: str) -> dict | None:
    """O pedido que está sendo montado nessa conversa (no máximo um por vez)."""
    marcas = ", ".join("?" for _ in ABERTOS)
    with _trava:
        linha = con().execute(
            f"SELECT * FROM atendimentos WHERE espaco = ? AND estado IN ({marcas}) ORDER BY criado_em DESC LIMIT 1",
            (espaco, *ABERTOS)).fetchone()
    return _atendimento(linha) if linha else None


def atendimentos(estados: tuple = ABERTOS) -> list[dict]:
    marcas = ", ".join("?" for _ in estados)
    with _trava:
        linhas = con().execute(f"SELECT * FROM atendimentos WHERE estado IN ({marcas}) ORDER BY atualizado_em DESC",
                               estados).fetchall()
    return [_atendimento(l) for l in linhas]


def criar_atendimento(espaco: str, pessoa: str | None, ficha: dict | None = None) -> dict:
    with _trava:
        c = con()
        ids = [r[0] for r in c.execute("SELECT id FROM atendimentos")]
        maior = max((int(i.split("-")[1]) for i in ids), default=0)
        aid = f"A-{maior + 1:03d}"
        c.execute("INSERT INTO atendimentos(id, espaco, pessoa, estado, ficha, criado_em, atualizado_em) "
                  "VALUES (?, ?, ?, 'coletando', ?, ?, ?)",
                  (aid, espaco, pessoa, json.dumps(ficha, ensure_ascii=False) if ficha else None, agora(), agora()))
        c.commit()
    return atendimento(aid)


def atualizar_atendimento(aid: str, **campos) -> dict:
    sets, valores = [], []
    for nome, valor in campos.items():
        if nome == "ficha" and valor is not None:
            valor = json.dumps(valor, ensure_ascii=False)
        sets.append(f"{nome} = ?")
        valores.append(valor)
    sets.append("atualizado_em = ?")
    valores += [agora(), aid]
    with _trava:
        c = con()
        c.execute(f"UPDATE atendimentos SET {', '.join(sets)} WHERE id = ?", valores)
        c.commit()
    return atendimento(aid)


# ---------------- pessoas, eventos, config ----------------

def pessoas() -> dict:
    with _trava:
        linhas = con().execute("SELECT * FROM pessoas").fetchall()
    return {r["id"]: {"nome": r["nome"], "iniciais": r["iniciais"], "cor": r["cor"], "foto": r["foto"], "email": r["email"]}
            for r in linhas}


def registrar_fala(tarefa: str, quem: str, texto: str) -> dict:
    """Uma linha da conversa da tarefa (é o que você lê e responde no painel)."""
    f = {"tarefa": tarefa, "quem": quem, "texto": texto, "quando": agora()}
    with _trava:
        c = con()
        cur = c.execute("INSERT INTO falas(tarefa, quem, texto, quando) VALUES (:tarefa, :quem, :texto, :quando)", f)
        c.commit()
    return {**f, "id": cur.lastrowid}


def falas(tarefa: str, limite: int = 200) -> list[dict]:
    with _trava:
        linhas = con().execute(
            "SELECT * FROM falas WHERE tarefa = ? ORDER BY id DESC LIMIT ?", (tarefa, limite)
        ).fetchall()
    return [{k: r[k] for k in ("id", "tarefa", "quem", "texto", "quando")} for r in reversed(linhas)]


def registrar_evento(texto: str, tarefa: str | None = None, pessoa: str | None = None,
                     tipo: str | None = None, detalhe: str | None = None) -> dict:
    e = {"tipo": tipo, "tarefa": tarefa, "pessoa": pessoa, "texto": texto, "detalhe": detalhe, "quando": agora()}
    with _trava:
        c = con()
        cur = c.execute(
            "INSERT INTO eventos(tipo, tarefa, pessoa, texto, detalhe, quando) VALUES (:tipo, :tarefa, :pessoa, :texto, :detalhe, :quando)",
            e,
        )
        c.commit()
    return {**e, "id": cur.lastrowid}


def eventos(limite: int = 30, antes: int | None = None) -> list[dict]:
    """Mais recentes primeiro. `antes` = id do último já carregado (pra paginar a atividade)."""
    with _trava:
        linhas = con().execute(
            "SELECT * FROM eventos WHERE id < ? ORDER BY id DESC LIMIT ?",
            (antes if antes is not None else 2**62, limite),
        ).fetchall()
    return [{k: r[k] for k in ("id", "tipo", "tarefa", "pessoa", "texto", "detalhe", "quando")} for r in linhas]


def config() -> dict:
    with _trava:
        linhas = con().execute("SELECT * FROM config").fetchall()
    return {r["chave"]: json.loads(r["valor"]) for r in linhas}


def salvar_config(chave: str, patch: dict) -> dict:
    atual = config().get(chave, {})
    novo = {**atual, **patch}
    with _trava:
        c = con()
        c.execute("INSERT OR REPLACE INTO config(chave, valor) VALUES (?, ?)", (chave, json.dumps(novo, ensure_ascii=False)))
        c.commit()
    return novo


def metricas() -> dict:
    semana = (datetime.now() - timedelta(days=7)).isoformat(timespec="seconds")

    def um(sql, *args):
        with _trava:
            return con().execute(sql, args).fetchone()[0]

    return {
        "concluidas7d": um("SELECT COUNT(*) FROM tarefas WHERE status = 'feito' AND descartada = 0 AND concluida_em >= ?", semana),
        "ignoradas": um("SELECT COUNT(*) FROM mensagens WHERE classificacao = 'ignorada'"),
        "respostasDm": um("SELECT COUNT(*) FROM eventos WHERE tipo = 'resposta_dm'"),
    }


def estado() -> dict:
    return {
        "tarefas": tarefas(),
        "atendimentos": atendimentos(),
        "pessoas": pessoas(),
        "eventos": eventos(),
        "config": config(),
        "metricas": metricas(),
    }
