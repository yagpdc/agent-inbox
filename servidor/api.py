"""Servidor local do painel (só biblioteca padrão).

  GET  /                              painel (arquivos de web/)
  GET  /api/estado                    tudo que o painel precisa
  GET  /api/ao-vivo                   atualizações em tempo real (SSE)
  POST /api/tarefas/<id>/<acao>       decisões: planejar, aprovar, reprovar, deploy...
  PUT  /api/config/<chave>            preferências

Só escuta em 127.0.0.1: nada fica exposto na rede.
"""

import json
import mimetypes
import queue
import re
import threading
import time
import unicodedata
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import (agenda, agentes, assistente, barramento, db, dev_local, jornada, local, movel, prs,
               recuperar, runner, tempo, vigia, workspaces)

WEB = db.RAIZ / "web"
# Muda a cada vez que o código do painel muda; o painel aberto recarrega sozinho quando percebe.
VERSAO = str(max((p.stat().st_mtime_ns for p in WEB.rglob("*") if p.is_file()), default=0))
MODELOS = {"claude-haiku-4-5", "claude-sonnet-5", "claude-opus-5"}
ESFORCOS = {"low", "medium", "high", "xhigh", "max"}
CATEGORIAS = {"site", "hub", "mapa", "camadas", "reativacao", "duvida"}  # os agentes
SUBS = {"mapa": {"bug", "feature"}}

ROTA_TAREFA = re.compile(r"^/api/tarefas/(T-\d+)/([a-z-]+)$")
ROTA_CONFIG = re.compile(r"^/api/config/([A-Za-z]+)$")
ROTA_FALAS = re.compile(r"^/api/tarefas/(T-\d+)/falas$")
ROTA_ORIGEM = re.compile(r"^/api/tarefas/(T-\d+)/mensagens$")
ROTA_AGENTE = re.compile(r"^/api/agentes/([a-z]+)(?:/(contexto|aprendizados))?$")
ROTA_ATENDIMENTO = re.compile(r"^/api/atendimentos/(A-\d+)/(cancelar)$")
# "deixa comigo" escrito no chat é você assumindo, não instrução pro agente seguir.
EU_CUIDO = re.compile(r"\b(deixa (que eu|comigo)|eu (cuido|fa[çc]o|resolvo|vejo)( isso| essa| disso)?|fica comigo)\b", re.I)


class Conflito(Exception):
    """A tarefa não está no estado certo pra essa decisão (ex.: clique duplo)."""


def _exigir(t: dict, *status: str) -> None:
    if t["status"] not in status:
        raise Conflito(f"{t['id']} já mudou de etapa. Atualizei a tela.")


def _publicar(t: dict) -> dict:
    barramento.publicar("tarefa", tarefa=t)
    return t


def _evento(texto: str, tid: str) -> None:
    barramento.publicar("evento", evento=db.registrar_evento(texto, tarefa=tid))


# ---------------- criar tarefa na mão (tela Tarefas) ----------------

def criar_tarefa(corpo: dict) -> dict:
    """Tarefa que você anota: fica com você (ou com um agente, que você libera com "Pode fazer")."""
    titulo = str(corpo.get("titulo") or "").strip()
    if not titulo:
        raise ValueError("dê um nome pra tarefa")
    para = str(corpo.get("responsavel") or "yago")
    if para != "yago" and para not in CATEGORIAS:
        raise ValueError("responsável inválido")
    eu = db.config().get("vigia", {}).get("eu") or ""
    pessoa = "u" + eu.split("/")[-1] if eu else next(
        (pid for pid, p in db.pessoas().items()
         if local.valor("emailDoDono") and (p.get("email") or "").lower() == local.valor("emailDoDono").lower()), None)
    if not pessoa or pessoa not in db.pessoas():
        raise ValueError("não achei você na lista de pessoas (o vigia precisa ter lido o Chat uma vez)")
    prioridade = corpo.get("prioridade") if corpo.get("prioridade") in ("P0", "P1", "P2", "P3") else "P2"
    prazo = str(corpo.get("prazo") or "").strip() or None
    pai = str(corpo.get("pai") or "") or None
    if pai and (not db.tarefa(pai) or db.tarefa(pai).get("pai")):
        raise ValueError("tarefa-mãe inválida (só um nível de subtarefa)")
    t = db.criar_tarefa({
        "titulo": titulo[:160], "tipo": "tarefa", "status": "comigo" if para == "yago" else "identificada",
        "categoria": None if para == "yago" else para, "sub": None, "prioridade": prioridade, "prazo": prazo, "pai": pai,
        "pessoa": pessoa, "pedido": str(corpo.get("pedido") or titulo).strip(),
    })
    _evento("Você criou a tarefa", t["id"])
    return _publicar(t)


# ---------------- decisões ----------------

def decidir(tid: str, acao: str, corpo: dict) -> dict:
    t = db.tarefa(tid)
    if t is None:
        raise KeyError(tid)

    if acao in ("descartar", "assumir", "concluir", "finalizar", "parar"):
        runner.tirar_da_fila(tid)  # você resolveu: não ocupa mais a vez
        runner.marcar_seguir(tid, False)

    if acao == "editar":
        # Organização (tela Tarefas): prioridade, prazo e título. Não mexe no andamento.
        patch = {}
        if "prioridade" in corpo:
            if corpo["prioridade"] not in ("P0", "P1", "P2", "P3"):
                raise ValueError("prioridade inválida")
            patch["prioridade"] = corpo["prioridade"]
        if "prazo" in corpo:
            prazo = str(corpo["prazo"] or "").strip()
            if prazo and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", prazo):
                raise ValueError("prazo inválido (AAAA-MM-DD)")
            patch["prazo"] = prazo or None
        if str(corpo.get("titulo") or "").strip():
            patch["titulo"] = str(corpo["titulo"]).strip()[:160]
        if "pai" in corpo:  # vira (ou deixa de ser) subtarefa
            pai = str(corpo["pai"] or "") or None
            if pai and (pai == tid or not db.tarefa(pai) or db.tarefa(pai).get("pai")):
                raise ValueError("tarefa-mãe inválida (só um nível de subtarefa)")
            patch["pai"] = pai
        if not patch:
            raise ValueError("nada pra mudar")
        return _publicar(db.atualizar_tarefa(tid, **patch))

    if acao == "responsavel":
        # "yago" = fica com você; um tipo de agente = passa pra ele (você libera com "Pode fazer").
        para = str(corpo.get("para") or "")
        if para == "yago":
            if t["status"] in ("triagem", "execucao"):
                raise Conflito("Tem agente trabalhando nessa tarefa agora. Pare antes de assumir.")
            _evento("Ficou com você", tid)
            return _publicar(db.atualizar_tarefa(tid, status="comigo" if t["status"] != "feito" else "feito"))
        if para not in CATEGORIAS:
            raise ValueError("responsável inválido")
        patch = {"categoria": para}
        if t["status"] == "comigo":
            patch["status"] = "identificada"
        _evento(f"Passou pro agente {agentes.definicao(para).get('apelido', para)}", tid)
        return _publicar(db.atualizar_tarefa(tid, **patch))

    if acao == "classificar":
        cat, _, sub = corpo.get("valor", "").partition(":")
        if cat not in CATEGORIAS or (sub and sub not in SUBS.get(cat, set())):
            raise ValueError("categoria inválida")
        return _publicar(db.atualizar_tarefa(tid, categoria=cat, sub=sub or None))

    if acao == "assumir":
        _exigir(t, "identificada")
        _publicar(db.atualizar_tarefa(tid, status="comigo"))
        _evento("Ficou com você", tid)

    elif acao == "ver-local":
        # Sobe (ou reabre) o servidor local com a cópia desta tarefa.
        repo = (t["plano"] or {}).get("repo")
        pasta = runner.WORKTREES / f"{tid}-{repo}"
        if repo not in dev_local.REPOS or not pasta.exists():
            raise ValueError("Essa tarefa não tem cópia com front pra mostrar.")
        arquivos = (t["resultado"] or {}).get("arquivos") or t["plano"].get("arquivos", [])
        threading.Thread(target=dev_local.mostrar_tarefa, args=(repo, pasta, tid, arquivos), daemon=True).start()
        return t

    elif acao == "terminal":
        runner.abrir_terminal(tid)
        return t

    elif acao == "pesquisar":
        _exigir(t, "identificada", "comigo")
        _evento("Você liberou a pesquisa", tid)
        runner.pesquisar(tid)

    elif acao == "falar":
        # Fala com a sessão que está trabalhando agora; se não houver, vira pedido de ajuste.
        texto = str(corpo.get("texto", "")).strip()
        arquivos = runner.arquivos_validos(tid, corpo.get("arquivos"))
        if not texto and not arquivos:
            raise ValueError("escreva alguma coisa")
        if arquivos and not ((t["pergunta"] or {}).get("etapa") == "conversa"):
            # Pro agente: entram nos anexos da tarefa, e ele vê os arquivos na pasta.
            t = _publicar(db.atualizar_tarefa(tid, anexos=list(dict.fromkeys([*(t["anexos"] or []), *arquivos]))))
            texto = (texto + "\n\n" if texto else "") + "Anexei: " + ", ".join(arquivos) + " (na pasta de anexos da tarefa)."
        if runner.falar_com(tid, texto):
            return db.tarefa(tid)  # sessão viva: entra no próximo passo dela

        barramento.publicar("falaTarefa", fala=db.registrar_fala(tid, "voce", texto))
        # Escrever numa tarefa que depende de você é dizer "vai em frente": ele segue
        # com o que você escreveu e executa quando o plano fechar.
        if t["status"] == "pergunta":
            _evento("Você respondeu na conversa", tid)
            runner.marcar_seguir(tid)
            runner.responder_em_texto(tid, texto, arquivos)
        elif t["status"] == "aprovacao":
            if not t["categoria"]:
                raise Conflito("Classifique antes de executar.")
            modelo, esforco = runner.modelo_recomendado(t)
            _evento("Você mandou seguir pela conversa", tid)
            runner.executar(tid, modelo, esforco)
        elif t["status"] == "identificada" and EU_CUIDO.search(texto):
            _publicar(db.atualizar_tarefa(tid, status="comigo"))
            _evento("Ficou com você", tid)
        elif t["status"] in ("identificada", "comigo"):
            _evento("Você mandou seguir pela conversa", tid)
            runner.marcar_seguir(tid)
            runner.planejar(tid) if t["tipo"] != "duvida" else runner.pesquisar(tid)
        elif t["status"] == "revisao" and (t["execucao"] or {}).get("sessao"):
            e = t["execucao"]
            _evento("Você pediu ajuste", tid)
            runner.executar(tid, e.get("modelo", "claude-sonnet-5"), e.get("esforco"),
                            retomar={"sessao": e["sessao"], "texto": runner.texto_ajuste(texto)})
        else:
            _evento("Você anotou uma instrução", tid)
            _publicar(db.atualizar_tarefa(tid, esperando="Anotei. Vale quando você liberar a próxima etapa."))

    elif acao == "tirar-arquivo":
        nome = str(corpo.get("nome", ""))
        if not nome.startswith("voce-") or "/" in nome or "\\" in nome:
            raise ValueError("só dá pra tirar arquivo que você anexou")
        (runner.ANEXOS / tid / nome).unlink(missing_ok=True)
        restantes = [n for n in (t["anexos"] or []) if n != nome]
        if restantes != (t["anexos"] or []):
            return _publicar(db.atualizar_tarefa(tid, anexos=restantes or None))
        return t

    elif acao == "assumir-conversa":
        # Você deixou o assistente tocar essa conversa: pesquisa e responde sozinho daqui pra frente.
        if not t["espaco"]:
            raise Conflito("Essa tarefa não veio do Chat.")
        runner.definir_modo(t["espaco"], "assumida", t["pessoa"])
        _evento("Você deixou o assistente assumir a conversa", tid)
        if t["status"] in ("identificada", "comigo"):
            runner.pesquisar(tid)
        elif t["status"] == "resposta" and (t["resposta"] or {}).get("texto"):
            runner.enviar_resposta(tid, t["resposta"]["texto"])
        # em triagem: a pesquisa em andamento já envia sozinha ao terminar

    elif acao == "soltar-conversa":
        if t["espaco"]:
            runner.definir_modo(t["espaco"], None)
        _evento("Voltou a te repassar a conversa", tid)

    elif acao == "enviar":
        _exigir(t, "resposta")
        texto = str(corpo.get("texto", "")).strip()
        if not texto:
            raise ValueError("a resposta está vazia")
        if not t["espaco"]:
            raise Conflito("Não sei em qual conversa responder.")
        runner.enviar_resposta(tid, texto, runner.arquivos_validos(tid, corpo.get("arquivos")))

    elif acao == "planejar":
        _exigir(t, "identificada", "comigo")
        _evento("Você liberou o plano", tid)
        runner.marcar_seguir(tid, False)  # só o plano: para na sua aprovação
        runner.planejar(tid)

    elif acao == "fazer":
        # Um clique só: planeja e já executa. Para na revisão, no seu local, e o deploy segue seu.
        _exigir(t, "identificada", "comigo")
        _evento("Você mandou fazer (plano + execução)", tid)
        runner.marcar_seguir(tid)
        runner.planejar(tid)

    elif acao == "aprovar":
        _exigir(t, "aprovacao")
        if not t["categoria"]:
            raise Conflito("Classifique antes de executar.")
        modelo, esforco = corpo.get("modelo"), corpo.get("esforco")
        if modelo not in MODELOS or (esforco is not None and esforco not in ESFORCOS):
            raise ValueError("modelo ou esforço inválido")
        if modelo == "claude-haiku-4-5":
            esforco = None  # Haiku não aceita esforço
        _evento("Você aprovou a execução", tid)
        runner.executar(tid, modelo, esforco)

    elif acao == "responder":
        _exigir(t, "pergunta")
        respostas = [str(r).strip() for r in corpo.get("respostas", [])]
        if len(respostas) != len(t["pergunta"]["itens"]) or not all(respostas):
            raise ValueError("responda todas as perguntas")
        _evento("Você respondeu", tid)
        runner.responder(tid, respostas)

    elif acao == "devolver":
        # Pedir ajuste: continua a mesma sessão da execução com o que você quer mudar.
        _exigir(t, "revisao")
        ajuste = str(corpo.get("ajuste", "")).strip()
        if not ajuste:
            raise ValueError("escreva o que quer ajustar")
        e = t["execucao"] or {}
        if not e.get("sessao"):
            raise Conflito("Não achei a sessão da execução pra continuar.")
        _evento("Você pediu ajuste", tid)
        runner.executar(tid, e.get("modelo", "claude-sonnet-5"), e.get("esforco"),
                        retomar={"sessao": e["sessao"], "texto": runner.texto_ajuste(ajuste)})

    elif acao == "reprovar":
        _exigir(t, "aprovacao")
        _evento("Você reprovou o plano", tid)
        runner.planejar(tid, motivo=corpo.get("motivo"))

    elif acao == "deploy":
        _exigir(t, "revisao")
        if (t["esperando"] or "").startswith("Fazendo deploy"):
            raise Conflito("O deploy já está rodando.")
        fechamento = None
        if "avisar" in corpo:
            fechamento = {"avisar": bool(corpo.get("avisar")), "texto": str(corpo.get("fechamento", "")).strip(),
                          "arquivos": runner.arquivos_validos(tid, corpo.get("arquivos"))}
        runner.fazer_deploy(tid, fechamento)

    elif acao == "descartar":
        _exigir(t, "identificada", "comigo", "pergunta", "resposta", "aprovacao")
        _publicar(db.atualizar_tarefa(tid, status="feito", descartada=True, concluidaEm=db.agora()))
        _evento("Descartada, não era tarefa", tid)
        mensagem = str(corpo.get("mensagem", "")).strip()
        arquivos = runner.arquivos_validos(tid, corpo.get("arquivos"))
        if (mensagem or arquivos) and t["espaco"]:
            # Opcional: avisa a pessoa, do jeito que você explicou, que isso não vai ser feito.
            runner.redigir_e_enviar(tid, f"O Yago não vai fazer esse pedido. O que ele quer que você diga: "
                                         f"{mensagem or 'avise com educação e mande o anexo'}", arquivos)

    elif acao == "concluir":
        _exigir(t, "revisao")
        _publicar(db.atualizar_tarefa(tid, status="feito", concluidaEm=db.agora()))
        _evento("Concluída sem deploy", tid)
        runner.remover_worktree(t)
        if corpo.get("avisar"):
            runner.fechar_com_pessoa(tid, str(corpo.get("fechamento", "")),
                                     runner.arquivos_validos(tid, corpo.get("arquivos")))

    elif acao == "parar":
        _exigir(t, "execucao")
        _publicar(db.atualizar_tarefa(tid, status="aprovacao", execucao=None))
        runner.parar(tid)
        _evento("Você parou a execução", tid)

    elif acao == "finalizar":
        # Você resolveu por conta própria: encerra em qualquer etapa aberta.
        _exigir(t, "identificada", "comigo", "triagem", "pergunta", "resposta", "aprovacao", "execucao", "revisao")
        runner.parar(tid)
        resultado = t["resultado"] or {}
        _publicar(db.atualizar_tarefa(
            tid, status="feito", concluidaEm=db.agora(), esperando=None,
            resultado={**resultado, "resumo": resultado.get("resumo") or "Resolvida por você.", "porVoce": True},
        ))
        _evento("Você finalizou", tid)
        if corpo.get("avisar"):
            runner.fechar_com_pessoa(tid, str(corpo.get("fechamento", "")),
                                     runner.arquivos_validos(tid, corpo.get("arquivos")))

    elif acao == "reabrir":
        _exigir(t, "feito")
        resultado = t["resultado"]
        if resultado and resultado.get("porVoce"):
            resultado = None if resultado.get("resumo") == "Resolvida por você." else {**resultado, "porVoce": False}
        _publicar(db.atualizar_tarefa(
            tid, status="aprovacao" if t["plano"] else "identificada",
            descartada=False, concluidaEm=None, resultado=resultado,
        ))
        _evento("Você reabriu", tid)

    else:
        raise KeyError(acao)

    if acao in ("concluir", "parar", "finalizar", "descartar"):
        # A 3000 volta pro hub principal se estava mostrando esta tarefa.
        threading.Thread(target=dev_local.tarefa_terminou, args=(tid,), daemon=True).start()
    barramento.publicar("metricas", metricas=db.metricas())
    return db.tarefa(tid)


# ---------------- HTTP ----------------

class Painel(BaseHTTPRequestHandler):
    server_version = "InboxAgent/0.1"

    def log_message(self, fmt, *args):  # só erros no console
        if args and str(args[1]).startswith(("4", "5")):
            super().log_message(fmt, *args)

    def _json(self, dados, status=HTTPStatus.OK):
        corpo = json.dumps(dados, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _receber_arquivo(self, tid: str) -> dict:
        """Arquivo que você anexou: vai pra pasta de anexos da tarefa (o agente também enxerga)."""
        from urllib.parse import unquote
        t = db.tarefa(tid)
        if not t:
            raise KeyError(tid)
        tamanho = int(self.headers.get("Content-Length") or 0)
        if not tamanho or tamanho > 25 * 1024 * 1024:
            raise ValueError("arquivo vazio ou maior que 25 MB")
        original = unquote(self.headers.get("X-Nome") or "arquivo")
        limpo = re.sub(r"[^A-Za-z0-9.\-]+", "_", unicodedata.normalize("NFKD", original).encode("ascii", "ignore").decode())[-80:] or "arquivo"
        nome = f"voce-{int(time.time())}-{limpo}"
        pasta = runner.ANEXOS / tid
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / nome).write_bytes(self.rfile.read(tamanho))
        return {"nome": nome, "original": original}  # só vira anexo da tarefa quando você envia

    def _corpo(self) -> dict:
        tamanho = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(tamanho) or b"{}") if tamanho else {}

    # --- GET ---
    def do_GET(self):
        caminho = self.path.split("?")[0]
        if caminho == "/api/estado":
            return self._json({**db.estado(), "versao": VERSAO, **runner.estado_fila(), "jornada": jornada.resumo(),
                               "agentes": agentes.nomes()})
        if caminho == "/api/eventos":
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            antes = int(q["antes"][0]) if q.get("antes", [""])[0].isdigit() else None
            limite = min(100, int(q["limite"][0])) if q.get("limite", [""])[0].isdigit() else 30
            return self._json({"eventos": db.eventos(limite, antes)})
        if m := ROTA_ORIGEM.match(caminho):
            t = db.tarefa(m[1])
            return self._json({"mensagens": db.mensagens_da_tarefa(t) if t else []})
        if m := ROTA_FALAS.match(caminho):
            return self._json({"falas": db.falas(m[1])})
        if caminho == "/api/tempo":
            try:
                return self._json(tempo.agora())
            except Exception as e:  # noqa: BLE001
                return self._json({"erro": f"não consegui ver o tempo agora ({str(e)[:120]})"},
                                  HTTPStatus.SERVICE_UNAVAILABLE)
        if caminho == "/api/agenda":
            try:
                return self._json({"eventos": agenda.hoje()})
            except Exception as e:  # noqa: BLE001
                return self._json({"erro": agenda.mensagem_de_erro(e)}, HTTPStatus.SERVICE_UNAVAILABLE)
        if caminho == "/api/abas":
            return self._json({"abas": barramento.abas()})
        if caminho == "/api/agentes":
            return self._json({"agentes": agentes.painel(), "atendimentos": db.atendimentos(),
                               "orquestrador": db.config().get("orquestrador", {}),
                               "camadas": db.config().get("camadas", {})})
        if caminho == "/api/ao-vivo":
            return self._ao_vivo()
        if caminho.startswith("/anexos/"):
            return self._estatico(caminho, base=db.RAIZ / "anexos", prefixo="/anexos/")
        if caminho.startswith("/entregas/"):
            return self._estatico(caminho, base=runner.ENTREGAS, prefixo="/entregas/")
        return self._estatico(caminho)

    def _estatico(self, caminho: str, base: Path = WEB, prefixo: str = "/"):
        from urllib.parse import unquote
        relativo = unquote(caminho[len(prefixo):]) if caminho != "/" else "index.html"
        alvo = (base / relativo).resolve()
        if base.resolve() not in alvo.parents or not alvo.is_file():
            return self._json({"erro": "não encontrado"}, HTTPStatus.NOT_FOUND)
        tipo = mimetypes.guess_type(alvo.name)[0] or "application/octet-stream"
        if alvo.suffix == ".js":
            tipo = "text/javascript"
        dados = alvo.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{tipo}; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-store")  # sempre a versão mais nova do painel
        self.end_headers()
        self.wfile.write(dados)

    def _ao_vivo(self):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        fila = barramento.assinar()
        try:
            self.wfile.write(b"retry: 2000\n\n")
            self.wfile.flush()
            while True:
                try:
                    mensagem = fila.get(timeout=15)
                except queue.Empty:
                    mensagem = ": ping\n\n"  # mantém a conexão viva
                self.wfile.write(mensagem.encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        finally:
            barramento.cancelar(fila)

    # --- POST / PUT ---
    def do_POST(self):
        caminho = self.path.split("?")[0]
        try:
            if (m := ROTA_TAREFA.match(caminho)) and m[2] == "arquivo":
                return self._json(self._receber_arquivo(m[1]))
            if m := ROTA_TAREFA.match(caminho):
                return self._json(decidir(m[1], m[2], self._corpo()))
            if caminho == "/api/tarefas":
                return self._json(criar_tarefa(self._corpo()))
            if caminho in ("/api/pet/resumir", "/api/pet/priorizar"):
                assistente.pedir(caminho.rsplit("/", 1)[1])
                return self._json({"ok": True})
            if m := ROTA_ATENDIMENTO.match(caminho):
                a = db.atendimento(m[1])
                if not a:
                    raise KeyError(m[1])
                db.atualizar_atendimento(a["id"], estado="cancelado")
                barramento.publicar("atendimentos", atendimentos=db.atendimentos())
                return self._json({"ok": True})
            raise KeyError(caminho)
        except KeyError as e:
            self._json({"erro": f"não encontrado: {e}"}, HTTPStatus.NOT_FOUND)
        except Conflito as e:
            self._json({"erro": str(e)}, HTTPStatus.CONFLICT)
        except ValueError as e:
            self._json({"erro": str(e)}, HTTPStatus.BAD_REQUEST)

    def do_PUT(self):
        caminho = self.path.split("?")[0]
        if a := ROTA_AGENTE.match(caminho):
            try:
                corpo = self._corpo()
                if a[2]:
                    agentes.salvar_arquivo(a[1], a[2], str(corpo.get("texto", "")))
                    return self._json({"ok": True})
                return self._json(agentes.salvar_definicao(a[1], corpo))
            except KeyError as e:
                return self._json({"erro": f"não encontrado: {e}"}, HTTPStatus.NOT_FOUND)
            except ValueError as e:
                return self._json({"erro": str(e)}, HTTPStatus.BAD_REQUEST)
        m = ROTA_CONFIG.match(caminho)
        if not m:
            return self._json({"erro": "não encontrado"}, HTTPStatus.NOT_FOUND)
        novo = db.salvar_config(m[1], self._corpo())
        if m[1] == "execucao" and novo.get("ligada"):
            threading.Thread(target=runner.retomar_pausados, daemon=True, name="retomar").start()
        if m[1] == "movel" and novo.get("ativo"):
            # Ligou ao sair do PC: já manda o que está te esperando.
            threading.Thread(target=lambda: movel.enviar(movel.resumo_pendentes()), daemon=True).start()
        return self._json(novo)


# ---------------- recarregar o painel quando o código muda ----------------

def _vigiar_web(intervalo: float = 0.8) -> None:
    def assinatura():
        return {p: p.stat().st_mtime for p in WEB.rglob("*") if p.is_file()}

    anterior = assinatura()
    while True:
        time.sleep(intervalo)
        atual = assinatura()
        if atual != anterior:
            anterior = atual
            barramento.publicar("recarregar")


def rodar(porta: int = 8787, dev: bool = True) -> None:
    db.iniciar()
    if dev:
        threading.Thread(target=_vigiar_web, daemon=True).start()
    print("Vigia do Chat: " + ("ligado" if vigia.iniciar() else "desligado (sem login: python -m servidor login)"))
    print(f"Tarefas retomadas: {recuperar.iniciar()}")
    workspaces.catalogo()  # se a lista estiver velha, atualiza em segundo plano
    prs.iniciar()  # PR mergeado no GitHub / Request changes: o servidor percebe sozinho
    jornada.iniciar()  # horas trabalhadas: conta enquanto o notebook está acordado
    servidor = ThreadingHTTPServer(("127.0.0.1", porta), Painel)
    servidor.daemon_threads = True
    print(f"Inbox Agent em http://localhost:{porta}  (Ctrl+C pra sair)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
