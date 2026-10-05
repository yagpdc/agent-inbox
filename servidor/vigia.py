"""Vigia do Google Chat: lê as DMs do Yago e entrega cada conversa pro orquestrador.

A cada ciclo:
  1. lê as mensagens novas das DMs e dos espaços (em espaço, só o que menciona o Yago);
  2. DEBOUNCE: se a pessoa ainda está digitando (última mensagem há menos de 20 s), espera
     ela terminar e trata tudo junto, como um contexto só;
  3. cada conversa vai pro orquestrador, que decide o que falar e o que fazer;
  4. manda o que estava esperando o Yago sair de alguma conversa e libera pedidos na espera.

O espaço do celular é outra coisa: o que o Yago escreve ali é decisão sobre tarefas (movel.py).
"""

import hashlib
import threading
import traceback
from datetime import datetime, timedelta, timezone

from . import barramento, chat, db, google, movel, runner

INTERVALO = 20             # segundos entre leituras
INTERVALO_DIGITANDO = 8    # enquanto alguém está no meio de várias mensagens
DEBOUNCE = timedelta(seconds=20)
PRIMEIRA_LEITURA = timedelta(hours=2)
TENTATIVAS = 3             # conversa que falhou no orquestrador: tenta de novo antes de desistir
CORES = ["#c2408a", "#22a06b", "#7b6ff8", "#d98a06", "#1b8ec9", "#d83b41", "#0f8b8d", "#8a5cf6"]

_parar = threading.Event()
_digitando = False  # alguém no meio de várias mensagens: lê de novo mais rápido
_falhas: dict[str, int] = {}  # espaço -> tentativas que falharam seguidas


def _rfc3339(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _estado() -> dict:
    return db.config().get("vigia", {})


def _salvar_estado(**patch) -> None:
    db.salvar_config("vigia", patch)


def _pessoa_id(usuario: str) -> str:
    """users/123 -> pessoa no banco (cria na primeira vez)."""
    pid = "u" + usuario.split("/")[1]
    atual = db.pessoas().get(pid)
    if atual and atual["iniciais"] != "?" and atual.get("email"):
        return pid
    p = chat.perfil(usuario) or {}  # vazio se a People API falhar: grava provisório e tenta de novo depois
    nome = p.get("nome")
    partes = [p for p in (nome or "").split() if p[:1].isalpha()]
    iniciais = (partes[0][0] + (partes[-1][0] if len(partes) > 1 else "")).upper() if partes else "?"
    cor = CORES[int(hashlib.md5(pid.encode()).hexdigest(), 16) % len(CORES)]
    with db._trava:  # noqa: SLF001
        db.con().execute(
            "INSERT OR REPLACE INTO pessoas(id, nome, iniciais, cor, chat_id, foto, email) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (pid, nome or (atual or {}).get("nome") or "Colega", iniciais if nome else (atual or {}).get("iniciais", "?"),
             cor, usuario, p.get("foto") or (atual or {}).get("foto"), p.get("email")),
        )
        db.con().commit()
    barramento.publicar("pessoas", pessoas=db.pessoas())  # o painel passa a conhecer quem é
    return pid


def _guardar_mensagem(m: dict, pessoa: str, classificacao: str | None, tarefa: str | None = None) -> None:
    with db._trava:  # noqa: SLF001
        db.con().execute(
            "INSERT OR REPLACE INTO mensagens(id, espaco, pessoa, texto, recebida_em, classificacao, tarefa) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (m["name"], m["name"].split("/messages/")[0], pessoa, m.get("text", ""), m["createTime"], classificacao, tarefa),
        )
        db.con().commit()


def _ja_vista(nome: str) -> bool:
    with db._trava:  # noqa: SLF001
        return db.con().execute("SELECT 1 FROM mensagens WHERE id = ?", (nome,)).fetchone() is not None


def _hora(m: dict) -> datetime:
    return datetime.fromisoformat(m["createTime"].replace("Z", "+00:00"))


def _do_yago(m: dict, eu: str) -> bool:
    """Mensagem escrita pelo próprio Yago (as do assistente saem com o usuário dele, mas não contam)."""
    return m.get("sender", {}).get("name") == eu and not chat.do_assistente(m)


def _yago_na_conversa(historico: list[dict], eu: str) -> bool:
    """Você escreveu nessa conversa há pouco? Então ela é sua e o assistente fica quieto."""
    minutos = db.config().get("respostaDm", {}).get("inativaMin", 10)
    limite = datetime.now(timezone.utc) - timedelta(minutes=minutos)
    return any(_do_yago(x, eu) and _hora(x) > limite for x in historico)


def _me_menciona(m: dict, eu: str) -> bool:
    return any(
        a.get("type") == "USER_MENTION" and a.get("userMention", {}).get("user", {}).get("name") == eu
        for a in m.get("annotations", [])
    )


# ---------------- ciclo ----------------

def ciclo() -> None:
    global _digitando
    eu = chat.meu_usuario()
    agora = datetime.now(timezone.utc)
    ultima = _estado().get("ultimaLeitura")
    desde = datetime.fromisoformat(ultima.replace("Z", "+00:00")) if ultima else agora - PRIMEIRA_LEITURA

    novas_por_espaco: dict[str, dict] = {}
    for esp in chat.espacos():
        ativo = esp.get("lastActiveTime")
        if ativo and datetime.fromisoformat(ativo.replace("Z", "+00:00")) <= desde:
            continue
        for m in chat.mensagens(esp["name"], _rfc3339(desde)):
            autor = m.get("sender", {})
            if autor.get("type") != "HUMAN":
                continue
            if esp["name"] == movel.espaco() and autor.get("name") == eu:
                # Espaço do celular: o que você escreve ali é decisão, não pedido novo.
                if _ja_vista(m["name"]):
                    continue
                _guardar_mensagem(m, _pessoa_id(autor["name"]), "comando")
                tid = movel.tarefa_da_thread((m.get("thread") or {}).get("name"))
                if tid:
                    movel.processar(tid, m.get("text", ""))
                else:
                    movel.comando_geral(m.get("text", ""))
                continue
            if autor.get("name") == eu or _ja_vista(m["name"]):
                continue
            if esp.get("spaceType") == "SPACE" and not _me_menciona(m, eu):
                continue  # em espaços, só o que é pra você
            novas_por_espaco.setdefault(esp["name"], {"espaco": esp, "novas": []})["novas"].append(m)

    # Debounce: quem mandou mensagem há menos de 20 s provavelmente ainda está escrevendo.
    # Essas conversas esperam o próximo ciclo, e a leitura não avança além delas.
    segurar_ate = agora
    _digitando = False
    for nome in list(novas_por_espaco):
        novas = novas_por_espaco[nome]["novas"]
        if agora - max(_hora(m) for m in novas) < DEBOUNCE:
            _digitando = True
            segurar_ate = min(segurar_ate, min(_hora(m) for m in novas) - timedelta(seconds=1))
            del novas_por_espaco[nome]

    for nome in _triar(novas_por_espaco, eu):  # falhou: a leitura não passa dela, tenta no próximo ciclo
        segurar_ate = min(segurar_ate, min(_hora(m) for m in novas_por_espaco[nome]["novas"]) - timedelta(seconds=1))
    _salvar_estado(ultimaLeitura=_rfc3339(segurar_ate), erro=None)

    from . import orquestrador  # evita import circular
    for passo in (orquestrador.enviar_pendentes, orquestrador.liberar_esperas):
        try:
            passo()
        except Exception as e:  # noqa: BLE001
            print(f"[vigia] {passo.__name__} falhou: {e!r}", traceback.format_exc(), sep="\n", flush=True)


def _triar(novas_por_espaco: dict, eu: str) -> list[str]:
    """Entrega cada conversa pro orquestrador. Devolve as que falharam e vão ser tentadas de novo."""
    from . import orquestrador  # evita import circular
    falharam = []
    for nome_esp, item in novas_por_espaco.items():
        try:
            item["historico"] = chat.ultimas(nome_esp, orquestrador.HISTORICO)
            item["pessoa"] = _pessoa_id(item["novas"][-1]["sender"]["name"])
            item["dm"] = item["espaco"].get("spaceType") == "DIRECT_MESSAGE"
            orquestrador.tratar(nome_esp, item, eu)
            _falhas.pop(nome_esp, None)
        except Exception as e:  # noqa: BLE001
            print(f"[vigia] orquestrador falhou em {nome_esp}: {e!r}", traceback.format_exc(), sep="\n", flush=True)
            _falhas[nome_esp] = _falhas.get(nome_esp, 0) + 1
            if _falhas[nome_esp] < TENTATIVAS:
                falharam.append(nome_esp)
                continue
            _falhas.pop(nome_esp, None)
            for m in item["novas"]:
                _guardar_mensagem(m, item.get("pessoa") or _pessoa_id(m["sender"]["name"]), "erro")
            if item.get("pessoa"):
                _chamar_yago(nome_esp, item, f"Não consegui tratar essa conversa ({str(e)[:100]}).")
    if novas_por_espaco:
        barramento.publicar("metricas", metricas=db.metricas())
    return falharam


def _falar(espaco: str, item: dict, texto: str) -> None:
    if runner.yago_na_conversa(espaco):
        return  # você entrou na conversa enquanto ele pensava: fica quieto
    try:
        chat.enviar(espaco, texto)  # DM: na conversa principal, não numa thread
    except Exception as e:  # noqa: BLE001
        barramento.publicar("fala", texto=f"Não consegui responder no Chat: {str(e)[:120]}")
        return
    e = db.registrar_evento("Respondi a DM", tipo="resposta_dm", pessoa=item["pessoa"], detalhe=texto[:80])
    barramento.publicar("evento", evento=e)


def _chamar_yago(espaco: str, item: dict, motivo: str) -> None:
    """Vira uma decisão sua: o que a pessoa disse e um campo pra você orientar a resposta."""
    pessoa = db.pessoas().get(item["pessoa"], {}).get("nome", "Colega")
    disse = "\n".join(m.get("text", "") for m in item["novas"])[:1500]
    aberta = next((t for t in db.tarefas() if t["espaco"] == espaco and t["status"] == "pergunta"
                   and (t.get("pergunta") or {}).get("etapa") == "conversa"), None)
    if aberta:
        # Já tem uma decisão sua aberta dessa conversa: atualiza ela em vez de criar outra.
        itens = [{"pergunta": f"{motivo} O que eu respondo?", "opcoes": []}]
        avisado = (aberta["pergunta"] or {}).get("avisadoEm") or ""
        de_novo = not avisado or datetime.now() - datetime.fromisoformat(avisado) > timedelta(minutes=30)
        t = db.atualizar_tarefa(aberta["id"], pedido=f"{aberta['pedido']}\n\n{disse}"[-3000:],
                                pergunta={**aberta["pergunta"], "itens": itens,
                                          "avisadoEm": db.agora() if de_novo else avisado})
        barramento.publicar("tarefa", tarefa=t)
        if de_novo:  # a mesma conversa não fica pipocando: um aviso a cada 30 min
            barramento.publicar("evento", evento=db.registrar_evento("Conversa precisa de você: mensagem nova", tarefa=t["id"]))
            barramento.publicar("aviso", aviso="pergunta", tarefa=t)
        return
    t = db.criar_tarefa({
        "titulo": f"Conversa com {pessoa.split(' ')[0]}",
        "tipo": "duvida",
        "espaco": espaco,
        "thread": item["novas"][-1].get("thread", {}).get("name"),
        "status": "pergunta",
        "categoria": None, "sub": None, "prioridade": "P1",
        "pessoa": item["pessoa"],
        "pedido": disse,
        "chatUrl": item["espaco"].get("spaceUri"),
        "pergunta": {"etapa": "conversa", "avisadoEm": db.agora(),
                     "itens": [{"pergunta": f"{motivo} O que eu respondo?", "opcoes": []}]},
    })
    barramento.publicar("tarefa", tarefa=t)
    barramento.publicar("evento", evento=db.registrar_evento("Conversa precisa de você", tarefa=t["id"]))
    barramento.publicar("aviso", aviso="pergunta", tarefa=t)


# ---------------- laço ----------------

def _laco() -> None:
    while not _parar.is_set():
        try:
            ciclo()
        except google.SemLogin as e:
            _salvar_estado(erro=str(e))
            barramento.publicar("vigia", ok=False, erro=str(e))
            _parar.wait(600)
            continue
        except Exception as e:  # noqa: BLE001
            print(f"[vigia] ciclo falhou: {e!r}", traceback.format_exc(), sep="\n", flush=True)  # vai pro logs/servidor.log
            _salvar_estado(erro=str(e)[:300])
            barramento.publicar("vigia", ok=False, erro=str(e)[:300])
        else:
            barramento.publicar("vigia", ok=True, erro=None)
        # Alguém no meio de várias mensagens: volta logo pra responder assim que terminar.
        _parar.wait(INTERVALO_DIGITANDO if _digitando else INTERVALO)


def iniciar() -> bool:
    if not google.tem_login() or not db.config().get("vigia", {}).get("ativo", True):
        return False
    threading.Thread(target=_laco, daemon=True, name="vigia").start()
    return True
