"""Controlli senza rete: cosa cattura ogni strato contro un server finto. Uso: python test_strati.py"""
import contextlib
import io
import json
import re
import tempfile
import time
from pathlib import Path

import httpx2 as httpx

import segnali as sg
import strati as s
from opentelemetry import trace
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.trace import TracerProvider

CARTELLA = Path(tempfile.mkdtemp())
INTESTAZIONI = {"request-id": "req_finto", "anthropic-organization-id": "org-finta", "anthropic-workspace-id": "wrk-finto"}
VISTE = []  # le intestazioni che il client manda al provider
CORPI = []  # i corpi delle richieste: istruzioni, messaggi, strumenti
PAUSA = 0.15  # secondi di attesa del server finto prima di far chiamare lo strumento: rende l'overlap deterministico
# Cosa fa il modello finto oltre al giro base. Tutto spento: la demo di prima (coordina chiama i tre agenti e valida).
#   annidate    programma chiede anche a sale; valida ricontrolla con programma e avvisi, insieme
#   valida_sala la richiesta di valida ad avvisi nomina la sala B (e allora avvisi riporta l'avviso)
#   dialogo     avvisi chiede anche a programma (serve --correzione-dialogo: senza, non ha lo strumento)
#   ciclo       programma prova a richiamare questo agente (se stesso, o avvisi che l'ha chiamato nel dialogo)
FINTO = {"annidate": False, "valida_sala": False, "dialogo": False, "ciclo": None}


@contextlib.contextmanager
def finto(**scelte):
    prima = dict(FINTO)
    FINTO.update(scelte)
    try:
        yield
    finally:
        FINTO.clear()
        FINTO.update(prima)


def risposta_finta(richiesta):
    """Simula Claude. coordina chiama programma, sale, avvisi, poi valida, poi risponde; i tre agenti chiamano il
    loro strumento e rispondono; avvisi non riporta l'avviso sulla sala B (e' lo sbaglio che la demo osserva).
    Senza strumenti risponde come valida. Con FINTO acceso, anche le chiamate fra agenti (vedi sopra)."""
    VISTE.append(dict(richiesta.headers))
    corpo = json.loads(richiesta.content)
    CORPI.append(corpo)
    messaggi = corpo["messages"]
    ultimo = messaggi[-1]["content"]
    strumenti = {x["name"] for x in corpo.get("tools", [])}
    dati = next((x for x in corpo.get("tools", []) if x["name"].startswith("leggi_")), None)  # lo strumento dei dati
    pensiero = {"type": "thinking", "thinking": "Devo leggere il programma.", "signature": "x"}
    uso = {"input_tokens": 1000, "output_tokens": 50, "cache_read_input_tokens": 0}
    base = {"id": "msg_finto", "type": "message", "role": "assistant", "model": s.MODEL, "usage": uso}
    chiesti = {x["name"] for m in messaggi if isinstance(m["content"], list) for x in m["content"] if x.get("type") == "tool_use"}
    risultato = ultimo[-1]["content"] if isinstance(ultimo, list) else None
    risultati = {b["tool_use_id"].split("-", 1)[1]: str(b["content"]) for b in ultimo} if isinstance(ultimo, list) else {}
    prima_richiesta = messaggi[0]["content"]

    def chiama(nome, argomenti):
        return chiama_molti({nome: argomenti})

    def chiama_molti(chiamate):
        contenuto = [pensiero] + [{"type": "tool_use", "id": f"t{len(messaggi)}-{nome}", "name": nome, "input": argomenti}
                                  for nome, argomenti in chiamate.items()]
        return httpx.Response(200, headers=INTESTAZIONI, json={**base, "stop_reason": "tool_use", "content": contenuto})

    def rispondi(testo):
        return httpx.Response(200, headers=INTESTAZIONI,
                              json={**base, "stop_reason": "end_turn", "content": [pensiero, {"type": "text", "text": testo}]})

    if "valida" in strumenti:  # coordina
        richieste = {"programma": "A che ora è il workshop Kubernetes da zero?",
                     "sale": "In che sala è il workshop Kubernetes da zero?",
                     "avvisi": "Ci sono avvisi sul workshop Kubernetes da zero?"}
        if "valida" in chiesti:
            return rispondi(risultato)
        if "programma" in chiesti:
            return chiama("valida", {"domanda": s.DOMANDA, "risposta": "Oggi alle 15:00, sala B.",
                                     "contesto": "Programma: oggi 15:00, sala B."})
        contenuto = [pensiero] + [{"type": "tool_use", "id": f"t1-{n}", "name": n, "input": {"richiesta": r}}
                                  for n, r in richieste.items()]  # i tre insieme, in un solo giro
        return httpx.Response(200, headers=INTESTAZIONI, json={**base, "stop_reason": "tool_use", "content": contenuto})
    if FINTO["annidate"] and not dati and strumenti:  # valida con programma e avvisi come strumenti
        if len(messaggi) == 1:
            sala = "Ci sono avvisi sulla sala B oggi?" if FINTO["valida_sala"] else "Ci sono avvisi sul workshop Kubernetes da zero?"
            return chiama_molti({"programma": {"richiesta": "Giorno, ora e sala del workshop Kubernetes da zero?"},
                                 "avvisi": {"richiesta": sala}})
        if "chius" in risultati.get("avvisi", ""):
            return rispondi("La sala B è chiusa dalle 15:00: l'orario non è confermato.")
        return rispondi("Oggi alle 15:00, sala B.\n\nVerificato.")
    if dati and len(messaggi) == 1:
        argomenti = {c: ("B" if c == "sala" else "Kubernetes da zero") for c in dati["input_schema"].get("required", [])}
        time.sleep(PAUSA)  # solo nel test: i rami si sovrappongono sempre
        altri = {}
        if FINTO["annidate"] and "sale" in strumenti and dati["name"] == "leggi_programma":  # programma chiede il piano a sale
            altri["sale"] = {"richiesta": "In che sala e a che piano è il workshop Kubernetes da zero?"}
        if FINTO["dialogo"] and "programma" in strumenti and dati["name"] == "leggi_avvisi":  # avvisi chiede la sala a programma
            altri["programma"] = {"richiesta": "Giorno, ora e sala del workshop Kubernetes da zero?"}
        if FINTO["ciclo"] and dati["name"] == "leggi_programma" and (FINTO["ciclo"] == "programma" or "Giorno, ora e sala" in prima_richiesta):
            altri[FINTO["ciclo"]] = {"richiesta": "ancora tu?"}
        return chiama_molti({dati["name"]: argomenti, **altri})
    if dati:
        if dati["name"] == "leggi_avvisi" and ("sala B" in prima_richiesta or "sala B" in risultati.get("programma", "")):
            return rispondi("- " + s.AVVISO_CHIAVE)  # sa che e' la sala B: non lascia l'avviso fra i 400
        return rispondi({"leggi_programma": "Oggi alle 15:00, sala B" + (", piano 1." if FINTO["annidate"] else "."),
                         "leggi_sale": "Sala B, primo piano, 80 posti.",
                         "leggi_avvisi": "Nessun avviso sul workshop."}[dati["name"]])
    return rispondi("Oggi alle 15:00, sala B.\n\nVerificato.")


def corri(strato, guasto=True):
    s.STRATO = strato
    http = httpx.Client(transport=httpx.MockTransport(risposta_finta))
    client = s.cliente(api_key="finta", http_client=http)
    with contextlib.redirect_stdout(io.StringIO()) as fuori:
        reg = s.esegui(guasto, CARTELLA, client=client)
        s.mostra(reg)
    return reg, re.sub(r"\033\[\d+m", "", fuori.getvalue())  # senza colori


def nomi(reg):
    return [x["nome"] for x in reg["span"]]


def padre_di(reg, nome):
    per_id = {x["id"]: x for x in reg["span"]}
    return per_id[next(x for x in reg["span"] if x["nome"] == nome)["padre"]]["nome"]


def attributi(reg, nome):
    return next(x for x in reg["span"] if x["nome"] == nome)["attributi"]


# coordina: 3 giri (i tre agenti insieme, valida, risposta); programma, sale e avvisi 2 ciascuno; valida 1
CHIAMATE = 10
AGENTI = ("programma", "sale", "avvisi", "valida")


def test_strato_0_solo_log_e_fattura():
    reg, fuori = corri(0)
    assert reg["span"] == [] and reg["fattura"]["chiamate"] == CHIAMATE
    assert "200 in" in fuori and "fattura:" in fuori and "trace" not in fuori
    assert not any("traceparent" in h for h in VISTE[-CHIAMATE:])


def test_strato_0_una_riga_di_log_per_chiamata():
    reg, fuori = corri(0)
    assert len(reg["righe"]) == CHIAMATE and reg["metriche"] == [] and reg["log_otel"] == []
    assert {r["campi"]["richiesta"] for r in reg["righe"]} == {reg["richiesta"]}  # lo stesso id su ogni riga
    agenti = [r["campi"]["gen_ai.agent.name"] for r in reg["righe"]]
    assert {a: agenti.count(a) for a in set(agenti)} == {"coordina": 3, "programma": 2, "sale": 2, "avvisi": 2, "valida": 1}
    r = reg["righe"][0]["campi"]  # i nomi dei campi del conto, come li manda il provider
    assert (r["gen_ai.usage.input_tokens"], r["gen_ai.usage.output_tokens"], r["gen_ai.usage.cache_read.input_tokens"],
            r["gen_ai.usage.cache_write.input_tokens"]) == (1000, 50, 0, 0)
    assert r["gen_ai.response.model"] == s.MODEL and reg["righe"][0]["testo"] == "chiamata al modello"
    assert "chiamata al modello" in fuori and f"richiesta={reg['richiesta']}" in fuori and "gen_ai.usage.input_tokens=1000" in fuori
    assert 'LOG.info("chiamata al modello"' in s.codice(0) and "uuid.uuid4()" in s.codice(0)
    assert s.LOG.handlers == []  # l'impalcatura che tiene le righe esce con la run
    assert corri(0)[0]["richiesta"] != reg["richiesta"]  # un id per richiesta


def test_strato_1_le_metriche_dei_token():
    reg, fuori = corri(1)
    m = {(x["nome"], x["attributi"].get("gen_ai.agent.name")): x for x in reg["metriche"]}
    for agente, n in {"coordina": 3, "programma": 2, "sale": 2, "avvisi": 2, "valida": 1}.items():
        assert m[("gen_ai.client.inference.usage.input_tokens", agente)]["valore"] == 1000 * n
        assert m[("gen_ai.client.inference.usage.output_tokens", agente)]["valore"] == 50 * n
        h = m[("assistente.agente.token", agente)]
        assert h["conteggio"] == 1 and h["somma"] == 1050 * n  # un valore per agente, a fine richiesta
    a = m[("gen_ai.client.inference.usage.input_tokens", "avvisi")]["attributi"]
    assert (a["gen_ai.operation.name"], a["gen_ai.provider.name"], a["gen_ai.token.modality"]) == ("chat", "anthropic", "text")
    assert a["gen_ai.request.model"] == s.MODEL and len(reg["metriche"]) == 15
    assert all(not x["exemplar"] for x in reg["metriche"])  # allo strato 1 non c'e' la trace della richiesta
    assert "assistente.agente.token · coordina 3150 · " in fuori and "input_tokens 10000 · output_tokens 500" in fuori
    assert len(corri(1)[0]["metriche"]) == 15  # a ogni run solo la sua: la memoria legge in delta
    codice1 = s.codice(1)
    assert 'create_histogram("assistente.agente.token"' in codice1 and "TOKEN_AGENTE.record(n" in codice1
    assert "TOKEN_IN.add(ingresso, attributi)" in codice1 and "if STRATO" not in codice1


def test_strato_2_gli_exemplar_portano_la_trace_della_richiesta():
    reg, _ = corri(2)
    traccia = reg["span"][0]["trace"]
    istogramma = [x for x in reg["metriche"] if x["nome"] == "assistente.agente.token"]
    assert len(istogramma) == 5 and all(x["exemplar"] == [traccia] for x in istogramma)
    assert all(x["exemplar"] == [traccia] for x in reg["metriche"])  # anche i contatori: dentro invoke_agent


def test_strato_1_una_trace_per_chiamata_e_niente_contenuto():
    reg, fuori = corri(1)
    assert nomi(reg) == ["anthropic.messages.create"] * CHIAMATE
    assert s.esito(reg)["tracce"] == CHIAMATE
    a = reg["span"][0]["attributi"]
    assert a["gen_ai.operation.name"] == "chat" and a["anthropic.message.stop_reason"] == "tool_use"
    assert "gen_ai.response.finish_reasons" not in a and "gen_ai.input.messages" not in a
    assert all(a[k] == "oscurato" for k in s.ID_ACCOUNT)
    assert "org-finta" not in fuori and "chat ?" in fuori  # di chi sia la chiamata non si sa
    assert all("traceparent" in h for h in VISTE[-CHIAMATE:])  # l'SDK manda il contesto della trace al provider


def test_strato_2_una_trace_sola_e_il_grafo():
    reg, _ = corri(2)
    assert s.esito(reg)["tracce"] == 1
    assert nomi(reg)[-1] == "invoke_workflow assistente-evento"
    assert not any(n.startswith("execute_tool leggi_") for n in nomi(reg))  # gli strumenti dei dati sono dello strato 3
    for agente in AGENTI:  # gli archi fra agenti sono dello strato 2
        a = attributi(reg, f"execute_tool {agente}")
        assert "gen_ai.tool.call.arguments" not in a and a["gen_ai.transfer.target.name"] == agente
        assert a["gen_ai.agent.name"] == "coordina"


def test_strato_3_gli_strumenti_con_argomenti_e_risultato():
    reg, _ = corri(3)
    for nome in ("leggi_programma", "leggi_sale", "leggi_avvisi"):
        assert nomi(reg).count(f"execute_tool {nome}") == 1 and not attributi(reg, f"execute_tool {nome}") == {}
    assert "15:00" in attributi(reg, "execute_tool leggi_programma")["gen_ai.tool.call.result"]
    assert json.loads(attributi(reg, "execute_tool leggi_sale")["gen_ai.tool.call.result"])["sala"] == "B"
    assert json.loads(attributi(reg, "execute_tool leggi_programma")["gen_ai.tool.call.arguments"]) == {"sessione": "Kubernetes da zero"}
    giornata_piena = attributi(reg, "execute_tool leggi_avvisi")["gen_ai.tool.call.result"]  # tutte le pagine, una chiamata
    assert "Sala B: chiusa dalle 15:00" in giornata_piena and giornata_piena.count("\n") == 399
    assert "gen_ai.tool.call.arguments" in attributi(reg, "execute_tool valida")  # gli argomenti fra agenti sono un prompt
    assert all(not x["errore"] for x in reg["span"])  # nessun componente sbaglia


def span_di(reg, nome):
    return next(x for x in reg["span"] if x["nome"] == nome)


def test_strato_3_log_correlati_agli_span_degli_strumenti():
    reg, fuori = corri(3)
    traccia = reg["span"][0]["trace"]
    id_span = {n: span_di(reg, f"execute_tool {n}")["id"] for n in ("leggi_programma", "leggi_sale", "leggi_avvisi")}
    dei_dati = [r for r in reg["log_otel"] if "campi" not in r]  # le righe degli strumenti
    per_chiamata = [r for r in reg["log_otel"] if "campi" in r]  # le righe per chiamata dello strato 0, adesso con il contesto
    assert len(dei_dati) == 3 and len(per_chiamata) == CHIAMATE
    assert all(r["trace"] == traccia and r["livello"] == "INFO" for r in reg["log_otel"])
    agente_dello_span = {x["id"]: x["attributi"]["gen_ai.agent.name"] for x in reg["span"] if x["nome"].startswith("invoke_agent")}
    assert all(agente_dello_span[r["span"]] == r["campi"]["gen_ai.agent.name"] for r in per_chiamata)  # dentro l'invoke_agent di chi chiama
    assert "chiamata al modello gen_ai.agent.name=avvisi gen_ai.usage.input_tokens=1000" in fuori and "[invoke_agent avvisi]" in fuori
    per_testo = {r["testo"].split(":")[0]: r for r in dei_dati}  # scritti da thread diversi, ordine libero
    for nome, r in per_testo.items():
        assert r["span"] == id_span[nome] and len(r["span"]) == 16 and len(r["trace"]) == 32
    assert "leggi_avvisi: 40 pagine, 400 avvisi, filtro nessuno" in per_testo["leggi_avvisi"]["testo"]
    assert "leggi_programma: Kubernetes da zero dal programma pubblicato il 4/11 alle 18:00" in per_testo["leggi_programma"]["testo"]
    for r in reg["log_otel"]:  # l'orario del record, in epoch secondi, dentro lo span a cui appartiene
        x = next(x for x in reg["span"] if x["id"] == r["span"])
        assert x["inizio"] <= r["tempo"] <= x["fine"]
    assert "log con contesto" in fuori and "[execute_tool leggi_avvisi]" in fuori
    assert len(s.LOG.handlers) == 1  # un solo handler, non uno per run
    corri(3)
    assert len(s.LOG.handlers) == 1 and len(corri(3)[0]["log_otel"]) == 3 + CHIAMATE  # non si accumulano fra le run


def test_chiamate_dagli_span_come_le_righe_dal_vivo():
    reg, _ = corri(3)
    dagli_span = s.chiamate_dagli_span(reg["span"])
    chiave = lambda campi: (campi["gen_ai.agent.name"], campi["gen_ai.usage.input_tokens"], campi["gen_ai.usage.output_tokens"],
                           campi["gen_ai.usage.cache_read.input_tokens"])
    assert sorted(chiave(c["campi"]) for c in dagli_span) == sorted(chiave(r["campi"]) for r in reg["righe"])
    assert sorted(c["span"] for c in dagli_span) == sorted(r["span"] for r in reg["log_otel"] if "campi" in r)
    assert s.chiamate_dagli_span(corri(1)[0]["span"]) == []  # allo strato 1 l'agente non si sa


def test_sotto_lo_strato_3_i_log_non_hanno_contesto():
    for n in (0, 1, 2):
        reg, fuori = corri(n)
        assert reg["log_otel"] == [] and "log con contesto" not in fuori and s.LOG.handlers == []


def test_strato_4_da_dove_viene_il_dato_e_quanto():
    reg, _ = corri(4)
    assert sorted(nomi(reg)) == sorted(nomi(corri(3)[0]))  # lo strato 4 aggiunge attributi, non span
    assert attributi(reg, "execute_tool leggi_programma")["programma.pubblicato_il"] == "4/11 alle 18:00"
    assert attributi(reg, "execute_tool leggi_sale")["sale.fonte"] == "database delle sale"
    a = attributi(reg, "execute_tool leggi_avvisi")
    assert (a["avvisi.pagine"], a["avvisi.letti"], a["avvisi.filtro"]) == (40, 400, "nessuno")
    assert a["avvisi.aggiornati_alle"] == s.AVVISI_AGGIORNATI
    for nome in ("leggi_programma", "leggi_sale", "leggi_avvisi"):  # sotto lo strato 4 non ci sono
        assert not any(k.split(".")[0] in ("programma", "sale", "avvisi") for k in attributi(corri(3)[0], f"execute_tool {nome}"))
    reg, _ = corri(4, guasto=False)
    assert attributi(reg, "execute_tool leggi_avvisi")["avvisi.pagine"] == 3


def test_strato_4_con_il_filtro_per_sala():
    try:
        s.CORREZIONE = 2
        reg, _ = corri(4)
    finally:
        s.CORREZIONE = 0
    a = attributi(reg, "execute_tool leggi_avvisi")
    assert (a["avvisi.pagine"], a["avvisi.letti"], a["avvisi.filtro"]) == (1, 1, "sala B")
    assert any("filtro sala B" in r["testo"] for r in reg["log_otel"])


def test_righe_dei_nuovi_strati():
    codice3, codice4 = s.codice(3), s.codice(4)
    assert "LoggingHandler" in codice3 and "LoggingHandler" not in codice4
    assert "avvisi.pagine" in codice4 and "avvisi.pagine" not in codice3
    assert "LOG.info" not in codice3 + codice4  # il logging e' codice applicativo, non si marca


def test_url_dei_log_otlp():
    assert s.url_log("http://tempo:4318/v1/traces") == "http://tempo:4318/v1/logs"
    assert s.url_log("http://tempo:4318") == "http://tempo:4318/v1/logs"


def test_strato_5_il_contenuto_e_l_email():
    reg, fuori = corri(5)
    assert any("gen_ai.input.messages" in x["attributi"] for x in reg["span"])
    assert "pensiero di coordina: Devo leggere il programma." in fuori
    assert s.con_email(reg["span"]) > 0 and "email dell'utente" in fuori


def test_tranquilla_tre_pagine():
    reg, _ = corri(3, guasto=False)
    assert reg["modo"] == "sana" and reg["fattura"]["chiamate"] == CHIAMATE
    risultato = attributi(reg, "execute_tool leggi_avvisi")["gen_ai.tool.call.result"]
    assert risultato.count("\n") == 29 and "Sala B" not in risultato and "sala B" not in risultato


def test_orchestratore_grafo():
    reg, _ = corri(5)
    for agente in AGENTI:
        assert padre_di(reg, f"invoke_agent {agente}") == f"execute_tool {agente}"
    for agente, strumento in (("programma", "leggi_programma"), ("sale", "leggi_sale"), ("avvisi", "leggi_avvisi")):
        assert padre_di(reg, f"execute_tool {strumento}") == f"invoke_agent {agente}"
    passaggio = attributi(reg, "execute_tool valida")
    assert passaggio["gen_ai.agent.name"] == "coordina" and passaggio["gen_ai.transfer.mode"] == "return_to_caller"
    # la forma e' canonica: i rami partono in ordine libero, ma sono un insieme ordinato
    assert s.grafo(reg["span"]) == ["codice>coordina", "coordina>{avvisi(leggi_avvisi),programma(leggi_programma),sale(leggi_sale)}",
                                    "coordina>valida"]
    m = s.misura(reg)
    assert m["profondita"] == 5 and m["esito"] == "sbagliata" and m["valida_approva"] == 1


def test_i_tre_rami_girano_in_parallelo():
    reg, _ = corri(3)
    archi = [x for x in reg["span"] if x["nome"] in ("execute_tool programma", "execute_tool sale", "execute_tool avvisi")]
    assert len(archi) == 3 and {padre_di(reg, x["nome"]) for x in archi} == {"invoke_agent coordina"}
    assert len({x["padre"] for x in archi}) == 1  # lo stesso span, non tre omonimi
    assert max(x["inizio"] for x in archi) < min(x["fine"] for x in archi)  # gli intervalli si sovrappongono tutti
    assert s.esito(reg)["tracce"] == 1 and len({x["trace"] for x in reg["span"]}) == 1
    for agente, strumento in (("programma", "leggi_programma"), ("sale", "leggi_sale"), ("avvisi", "leggi_avvisi")):
        assert padre_di(reg, f"execute_tool {strumento}") == f"invoke_agent {agente}"  # il contesto e' arrivato ai thread


def test_risultati_nell_ordine_dei_tool_use():
    corri(2)
    giro = next(c for c in CORPI[::-1] if "programma" in {x["name"] for x in c.get("tools", [])}
                and isinstance(c["messages"][-1]["content"], list) and len(c["messages"][-1]["content"]) == 3)
    ids = [b["tool_use_id"] for b in giro["messages"][-1]["content"]]
    assert ids == ["t1-programma", "t1-sale", "t1-avvisi"]
    # anche se il primo finisce per ultimo, l'ordine non cambia
    fine = []

    def lento(client, chiamante, nome, id_chiamata, argomenti, stato):
        time.sleep({"a": 0.15, "b": 0.05, "c": 0.0}[nome])
        fine.append(nome)
        return nome.upper(), False

    vero, s.esegui_strumento = s.esegui_strumento, lento
    try:
        chiamate = [type("C", (), {"name": n, "id": n, "input": {}})() for n in "abc"]
        assert s.esegui_chiamate(None, "x", chiamate, {}) == [("A", False), ("B", False), ("C", False)]
    finally:
        s.esegui_strumento = vero
    assert fine == ["c", "b", "a"]


def test_eccezione_di_un_ramo_risale():
    def rotto(client, chiamante, nome, id_chiamata, argomenti, stato):
        if nome == "b":
            raise ValueError("ramo b")
        return nome, False

    vero, s.esegui_strumento = s.esegui_strumento, rotto
    try:
        chiamate = [type("C", (), {"name": n, "id": n, "input": {}})() for n in "abc"]
        try:
            s.esegui_chiamate(None, "x", chiamate, {})
        except ValueError as e:
            assert str(e) == "ramo b"
        else:
            raise AssertionError("l'eccezione e' sparita")
    finally:
        s.esegui_strumento = vero


def test_trova_con_chiave_vuota_non_trova_niente():
    assert s._trova(s.PROGRAMMA, "")[0] is None and s._trova(s.PROGRAMMA, "  ")[0] is None
    assert s._trova(s.PROGRAMMA, "kubernetes da zero")[0] == "Kubernetes da zero"
    assert json.loads(s.leggi_dato("leggi_programma", {}, {"piena": True}))["errore"] == "non trovato"


def test_tre_esiti_giornata_piena():
    v = lambda r: s.valuta(r, "guasto")
    # giuste: 14:00 come orario, il 15:00 solo come orario superato
    assert v("Oggi alle 14:00, sala B.") == "giusta"
    assert v("Il workshop è oggi in sala B, con orario probabilmente anticipato alle 14:00 rispetto alle 15:00 in programma.") == "giusta"
    assert v("Oggi alle 14:00 in sala B, non alle 15:00 come da programma.") == "giusta"
    assert v("Alle 14:00 in sala B (anticipato dalle 15:00 per la manutenzione).") == "giusta"
    assert v("Alle 14:00: la sala B chiude dalle 15:00 per manutenzione.") == "giusta"
    # avvisate: 15:00 come orario, ma con l'avvertimento
    assert v("Il workshop è oggi alle 15:00 in sala B, ma la sala B risulta chiusa dalle 15:00 per manutenzione elettrica, "
             "quindi potrebbe iniziare alle 14:00.") == "avvisata"
    assert v("È oggi alle 15:00 in Sala B (piano 1), ma c'è un avviso: sessioni un'ora prima, quindi probabilmente alle 14:00.") == "avvisata"
    assert v("Oggi alle 15:00 in sala B, ma la sala B è chiusa per manutenzione: chiedi allo staff.") == "avvisata"
    assert v("Alle 14:00, sala B; il programma indicava le 15:00.") == "giusta"
    assert v("Alle 14:00 in sala B, era alle 15:00 nel programma.") == "giusta"
    assert v("Alle 14:00 in sala B anziché alle 15:00.") == "giusta"
    assert v("Alle 14:00 in sala B, il programma diceva le 15:00.") == "giusta"
    # sbagliate: 15:00 senza avvertimenti, o nessun orario
    for frase in ("Oggi alle 15:00 in sala B, nessun avviso di chiusura o manutenzione.",
                  "Oggi alle 15:00 in sala B, non risulta che la sala sia chiusa.",
                  "Oggi alle 15:00 in sala B, nessuna anticipazione prevista.",
                  "Alle 15:00, non alle 14:00.",
                  "Oggi alle 15:00 in sala B. Il 14:00 è il pranzo."):
        assert v(frase) == "sbagliata", frase
    assert v("Alle 14:00 in sala B. Il 15:00 era l'orario del programma.") == "giusta"
    for frase in ("Alle 15:00 in sala B; gli avvisi non segnalano chiusure.",
                  "Alle 15:00 in sala B. Gli avvisi non indicano manutenzioni, però il programma potrebbe essere cambiato.",
                  "Alle 15:00 in sala B. Gli avvisi non parlano di manutenzione.",
                  "Alle 15:00 in sala B. Senza avvisi di chiusura.",
                  "Alle 15:00 in sala B. Non ho trovato avvisi di chiusura."):
        assert v(frase) == "sbagliata", frase
    assert v("Alle 15:00 in sala B, ma la sala B non sarà disponibile dalle 15:00.") == "avvisata"
    assert s.riporta_avviso("Gli avvisi non indicano manutenzioni, però la sala B chiude alle 15")
    for frase in ("La sala B non segnala chiusure", "Senza avvisi di chiusura per la sala B",
                  "Non ho trovato avvisi di chiusura per la sala B", "Per la sala B né chiusure né anticipi"):
        assert not s.riporta_avviso(frase), frase
    assert s.riporta_avviso("La sala B non sarà disponibile dalle 15")
    # la negazione vale solo nella sua clausola
    assert v("Oggi alle 15:00 in sala B. Nessun cambio di sala, ma la sala B chiude dalle 15:00.") == "avvisata"
    assert v("Oggi alle 15:00. Non ci sono variazioni: la sala B chiude dalle 15 e le sessioni sono anticipate.") == "avvisata"
    assert v("Oggi alle 15:00 in sala B, nessun avviso di chiusura o manutenzione.") == "sbagliata"
    assert v("Oggi alle 15:00. La sala B non è chiusa.") == "sbagliata"
    assert s.riporta_avviso("Nessun cambio di sala, ma la sala B chiude dalle 15:00")
    assert s.riporta_avviso("Non ci sono variazioni: la sala B chiude dalle 15 e le sessioni sono anticipate")
    assert not s.riporta_avviso("Nessun avviso di chiusura o manutenzione per la sala B")
    assert not s.riporta_avviso("La sala B non è chiusa")
    # e nell'altro verso, avvisate anche con un'altra frase che nega
    assert v("Oggi alle 15:00 in sala B. Nessun cambio di sala. Ma la sala B chiude per manutenzione.") == "avvisata"
    assert v("Oggi alle 15:00 in sala B, forse alle 14:00.") == "avvisata"
    assert v("Oggi alle 15:00 in sala B, potrebbe iniziare alle 14:00.") == "avvisata"
    assert v("Si tiene oggi alle 15:00 nella sala B.") == "sbagliata"
    assert v("Oggi alle 15:00 nella Sala B, e non risultano variazioni o annullamenti.") == "sbagliata"
    assert v("Non so dirtelo, chiedi allo staff.") == "sbagliata"
    assert v("Oggi alle 15:00, sala B, piano 1.") == "sbagliata"


def test_causa_solo_se_parla_della_sala_b_o_dell_anticipo():
    v = lambda r: s.valuta(r, "guasto")
    # rumore: chiusura o chiusure che non sono la sala B. Prima passavano per un avvertimento.
    for frase in ("Oggi alle 15:00 in sala B. La keynote di chiusura è alle 18:00.",
                  "Oggi alle 15:00 in sala B, piano 1. La sala C chiude alle 17.",
                  "Alle 15:00, sala B. Il banco accrediti è in manutenzione fino a mezzogiorno.",
                  "Oggi alle 15:00 in sala B; la cerimonia di chiusura è in sala A."):
        assert v(frase) == "sbagliata", frase
    # e nell'altro verso: la sala B (nella frase) con la sua causa, oppure l'anticipo, avvertono
    assert v("Oggi alle 15:00 in sala B, ma la sala B chiude per manutenzione.") == "avvisata"
    assert v("Oggi alle 15:00 in sala B, ma c'è un avviso di chiusura della sala B.") == "avvisata"
    assert v("Oggi alle 15:00 in sala B. Le sessioni del pomeriggio iniziano un'ora prima.") == "avvisata"
    assert v("Oggi alle 15:00 in sala B. Le sessioni pomeridiane sono state anticipate.") == "avvisata"
    # la sala B chiusa, nella stessa frase
    assert v("Oggi alle 15:00 in sala B. La sala B è chiusa dalle 15:00.") == "avvisata"
    # il rumore non toglie l'avvertimento vero che sta in un'altra frase
    assert v("Oggi alle 15:00 in sala B. La keynote di chiusura è alle 18:00. Ma la sala B chiude per manutenzione.") == "avvisata"


def test_quindici_superato_nelle_forme_dei_banchi_veri():
    v = lambda r: s.valuta(r, "guasto")
    # risposte vere del banco del 5/11 (registrazioni/strato-3 195128, strato-5-correzione-dialogo 210656)
    assert v('Il workshop è oggi alle 14:00 in sala B, al piano 1: il programma lo dava alle 15:00, ma per un avviso di oggi '
             'le sessioni del pomeriggio in sala B iniziano un\'ora prima per manutenzione dell\'impianto elettrico.') == "giusta"
    assert v("Oggi alle 14:00 in sala B, piano 1: il programma prevedeva le 15:00, ma per manutenzione elettrica le sessioni "
             "pomeridiane in sala B sono anticipate di un'ora.") == "giusta"
    assert v("Alle 14:00 in sala B. Il programma lo metteva alle 15:00.") == "giusta"
    assert v("Alle 14:00 in sala B, non alle 15:00 previste dal programma.") == "giusta"
    assert v("Alle 14:00 in sala B. In programma era alle 15:00.") == "giusta"
    # ma un 15:00 dato come orario, anche citando il programma al presente, non e' superato
    assert v("Il programma prevede le 15:00 in sala B.") == "sbagliata"
    assert v("Il programma lo dà alle 15:00, in sala B.") == "sbagliata"
    assert v("Il programma indica le 15:00 in sala B, ma non posso confermarlo: potrebbe essere alle 14:00.") == "avvisata"
    assert v("Il workshop è alle 15:00 in sala B, come prevedeva il programma. Nessun avviso.") == "sbagliata"


def test_due_esiti_giornata_tranquilla():
    v = lambda r: s.valuta(r, "sana")
    assert v("Si tiene oggi alle 15:00 nella sala B. Non risultano variazioni.") == "giusta"
    assert v("Oggi alle 15:00 in sala B, piano 1.") == "giusta"
    assert v("Oggi alle 14:00, sala B.") == "sbagliata"
    assert v("Alle 15:00 o forse alle 14:00.") == "sbagliata"
    assert v("Non so.") == "sbagliata"


def test_i_tre_esiti_nel_riepilogo_e_nelle_misure():
    m = s.esito({"span": [], "fattura": {"chiamate": 0, "in": 0, "cache": 0, "out": 0}, "risposta": "Alle 14:00.",
                 "modo": "guasto", "secondi": 1})
    assert m["esito"] == "giusta" and "giusta" not in m and "sbagliata" not in m


def test_il_piano_e_nelle_istruzioni_di_coordina():
    assert "piano" in s.istruzioni_coordina() and "ora, sala e piano" in s.istruzioni_coordina()


def tipo_di(voce: str) -> str:
    return voce.split(":")[0]


def test_avvisi_deterministici_e_senza_workshop():
    piena, tranquilla = s.avvisi(True), s.avvisi(False)
    assert len(piena) == s.PAGINE_PIENA and len(tranquilla) == s.PAGINE_TRANQUILLA
    assert all(len(p) == s.AVVISI_PER_PAGINA for p in piena + tranquilla)
    assert piena == s.avvisi(True) and tranquilla == s.avvisi(False)
    assert s.AVVISO_CHIAVE in piena[s.PAGINA_AVVISO - 1] and sum(s.AVVISO_CHIAVE in p for p in piena) == 1
    rumore = [v for p in piena for v in p if v != s.AVVISO_CHIAVE]
    assert len(set(rumore)) == len(rumore)  # vario
    for v in rumore:  # niente nomina il workshop, un suo orario, o la sala B
        assert not any(x in v.lower() for x in ("workshop", "kubernetes", "sala b")) and "14:" not in v and "15:" not in v
        assert not s.riporta_avviso(v), v  # il rivelatore non si fa ingannare dal rumore
    assert any("allarme" in v and "11:00" in v for v in rumore) and any("domani" in v for v in rumore)
    assert not any("sala b" in v.lower() for p in tranquilla for v in p)
    tipi = {}
    for v in rumore:  # equilibrio: nessun tipo di avviso prende il sopravvento, e i tipi sono tanti
        tipi[tipo_di(v)] = tipi.get(tipo_di(v), 0) + 1
    assert len(tipi) >= 20, tipi
    assert max(tipi.values()) / len(rumore) <= 0.15, tipi
    for k in ("Accessibilità", "Registrazioni", "Cambio relatore", "Feedback", "Merchandise", "Treni", "Navetta"):
        assert k in tipi, k


def test_correzione_istruzioni_e_filtro_per_sala():
    try:
        s.CORREZIONE = 1
        reg, _ = corri(5)
        assert istruzioni_di("su quella sala.") and reg["correzione"] == 1
        assert s.schemi()["leggi_avvisi"]["input_schema"].get("required") is None
        assert "Nessun avviso" not in s.leggi_dato("leggi_avvisi", {}, {"piena": True})  # col passo 1 le pagine sono tutte
        s.CORREZIONE = 2
        reg, _ = corri(5)
        assert reg["correzione"] == 2 and s.schemi()["leggi_avvisi"]["input_schema"]["required"] == ["sala"]
        assert istruzioni_di("usa quella indicata nella richiesta.")
        giornata = attributi(reg, "execute_tool leggi_avvisi")["gen_ai.tool.call.result"]
        assert giornata == "- " + s.AVVISO_CHIAVE  # solo la sala B, una riga
        assert s.leggi_dato("leggi_avvisi", {"sala": "b"}, {"piena": False}) == "Nessun avviso."
        for variante in ("B", "b", " B ", "sala B", "Sala B", "B."):  # il filtro non si rompe per come il modello scrive la sala
            assert s.leggi_dato("leggi_avvisi", {"sala": variante}, {"piena": True}) == "- " + s.AVVISO_CHIAVE, variante
        assert s.schemi()["leggi_avvisi"]["input_schema"]["properties"]["sala"]["enum"] == ["A", "B", "C"]
        assert s.leggi_dato("leggi_avvisi", {"sala": "A"}, {"piena": True}).startswith("- Sala A:")
    finally:
        s.CORREZIONE = 0


def istruzioni_di(agente_istruzioni_finiscono):
    return any(isinstance(c.get("system"), str) and c["system"].endswith(agente_istruzioni_finiscono)
               for c in CORPI[-CHIAMATE:])


def test_maschera_email():
    try:
        s.MASCHERA = True
        reg, fuori = corri(5)
    finally:
        s.MASCHERA = False
    assert s.con_email(reg["span"]) == 0 and "email dell'utente" not in fuori
    assert any("[email]" in (x["attributi"].get("gen_ai.input.messages") or "") for x in reg["span"])
    assert "[email]" in attributi(reg, "execute_tool valida")["gen_ai.tool.call.arguments"]  # anche dentro il JSON
    assert all(reg["span"][0]["attributi"][k] == "oscurato" for k in s.ID_ACCOUNT)
    reg, _ = corri(5)
    assert s.con_email(reg["span"]) > 0  # senza maschera l'email resta


def test_codice_pulito():
    for n in range(6):  # niente impalcatura della demo in nessuno strato (revisione finale, I2)
        assert not any(x in s.codice(n) for x in ("STRATO", "fai_provider", "MASCHERA")), n
    assert 'modo = "content"' in s.codice(5) and "MascheraEmail(processore)" in s.codice(5)
    assert "MascheraEmail" not in s.codice(1) and '"tracer_provider": provider' in s.codice(1)
    assert "open_telemetry=" in s.codice(1) and "**prova" not in s.codice(1)  # la slide non porta l'argomento dei test
    assert not s.codice(3).rstrip().endswith("fai_log()")  # niente chiamata orfana in fondo
    t = s.codice(3)
    assert 'span.set_attribute("gen_ai.tool.call.arguments"' in t and "if STRATO" not in t
    assert "\nspan.set_attribute(\"gen_ai.tool.call.arguments\"" in t  # il corpo dell'if perde il rientro
    assert not any(b.startswith((" ", "\t")) for b in s.codice(0).split("\n...\n"))  # lo strato 0 esce a margine, senza il lock
    assert "lock" not in s.codice(0) and 'stato["fattura"].append(r.usage)' in s.codice(0)
    assert '"out": sum(x.output_tokens for x in u)},' in s.codice(0)  # il dizionario della fattura e' intero
    assert "cache.read" not in open(s.__file__).read()


def test_approva_solo_un_verificato_in_fondo():
    # verdetti veri di valida, banco del 28/10
    assert s.approva("Il workshop è oggi alle 15:00 in sala B (ultimo aggiornamento 26 ore fa). Verificato.")
    assert s.approva("«Il workshop è oggi alle 15:00 in sala B.» Verificato.**")
    assert not s.approva('Il dato va confermato. Non è stato aggiunto "Verificato.".')
    assert not s.approva("Non posso aggiungere «Verificato.» alla versione attuale.")
    assert not s.approva("Il dato potrebbe non essere aggiornato, conviene verificarlo presso la segreteria.")
    assert not s.approva("Conviene verificare sul programma ufficiale orario, sala e giorno.")
    # in apertura, come ha fatto valida nel banco del 5/11 (taratura del 5/11, giro 3, run 182416)
    assert s.approva("Verificato. Il workshop \"Kubernetes da zero\" si tiene oggi alle 15:00 in sala B, al piano 1.")
    assert s.approva("Verificato.\n\nIl workshop si tiene oggi alle 15:00 nella sala B, al piano 1.")
    assert s.approva("**Verificato.** Il workshop si tiene oggi alle 15:00 in sala B.")
    assert s.approva("«Verificato.» Il workshop si tiene oggi alle 15:00 in sala B.")
    assert s.approva("  \"Verificato.\"\nOggi alle 15:00.")
    # rifiuti veri (giro-3 182539 e 182614, banco 28/10) che citano «Verificato.» senza approvare
    assert not s.approva("Non aggiungo «Verificato.» perché il contesto segnala che il dato non è aggiornato.")
    assert not s.approva("**Dato da confermare.** Non scrivo «Verificato.» perché il contesto non è aggiornato.")
    assert not s.approva("**Non verificato.** La risposta non è coerente con il contesto.")
    assert not s.approva("La risposta non può essere approvata come \"Verificato.\" perché il dato non è aggiornato.")
    assert not s.approva("Il dato va confermato, quindi non ho aggiunto «Verificato.».\n\nIl contesto indica 26 ore fa.")
    assert not s.approva("Il dato è verificato. Oggi alle 15:00.")


def test_replay_registrazione_dello_spike():
    reg, _ = corri(3)
    vecchia = {**json.loads(json.dumps(reg)), "variante": "A"}  # come le registrazioni nel tag spike-a-b
    with contextlib.redirect_stdout(io.StringIO()) as fuori:
        s.mostra(vecchia, registrata=True)
    assert "variante A" in fuori.getvalue().splitlines()[0]


def test_strumento_sconosciuto_e_un_errore():
    r = json.loads(s.leggi_dato("leggi_meteo", {}, {"piena": True}))
    assert r == {"errore": "strumento sconosciuto: leggi_meteo"}


def test_replay_strato_5_guasto_resta_corto():
    reg, _ = corri(5)
    giornata = attributi(reg, "execute_tool leggi_avvisi")["gen_ai.tool.call.result"]
    assert giornata.count("\n") + 1 == s.PAGINE_PIENA * s.AVVISI_PER_PAGINA  # lo span tiene tutto
    with contextlib.redirect_stdout(io.StringIO()) as fuori:
        s.mostra(json.loads(json.dumps(reg)), registrata=True)
    righe = re.sub(r"\033\[\d+m", "", fuori.getvalue()).splitlines()
    assert len(righe) < 120, len(righe)  # prima: oltre 500
    assert any("… 400 righe" in r for r in righe)


def test_banco_continua_dopo_una_run_fallita():
    sbagliare = [True]

    def server(richiesta):
        if sbagliare:
            return httpx.Response(500, json={"type": "error", "error": {"type": "api_error", "message": "guasto finto"}})
        return risposta_finta(richiesta)

    s.STRATO = 2
    client = s.cliente(api_key="finta", max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(server)))
    errori = io.StringIO()
    with contextlib.redirect_stderr(errori):
        orig = s.esegui

        def una_volta(guasto, cartella, client=None):
            try:
                return orig(guasto, cartella, client)
            finally:
                sbagliare.clear()  # la prima run fallisce, le altre vanno
        s.esegui = una_volta
        try:
            riuscite, fallite = s.esegui_banco(3, True, CARTELLA, client)
        finally:
            s.esegui = orig
    assert fallite == 1 and len(riuscite) == 2
    assert "run 1 fallita" in errori.getvalue() and "guasto finto" in errori.getvalue()
    # a fine banco, con una run fallita, il processo esce con stato 1; senza fallite, no
    with contextlib.redirect_stdout(io.StringIO()) as fuori:
        try:
            s.concludi_banco(3, riuscite, fallite)
            assert False, "doveva uscire"
        except SystemExit as e:
            assert e.code == 1
        s.concludi_banco(2, riuscite, 0)  # tutte riuscite: nessuna uscita
    assert "run fallite: 1 su 3" in fuori.getvalue()


def test_misure_sotto_lo_strato_2_senza_albero():
    cartella = Path(tempfile.mkdtemp()) / "strato-1"
    reg, _ = corri(1)
    cartella.mkdir(parents=True)
    (cartella / "a.json").write_text(json.dumps(reg))
    with contextlib.redirect_stdout(io.StringIO()) as fuori:
        s.misure([cartella])
    testo = fuori.getvalue()
    assert "serve lo strato 2" in testo and "forme dell'albero:" not in testo and "2 × " not in testo


def test_replay_riepilogo_righe():
    reg, dal_vivo = corri(3)
    with contextlib.redirect_stdout(io.StringIO()) as fuori:
        s.mostra(json.loads(json.dumps(reg)), registrata=True)
        s.riepilogo(CARTELLA)
        s.righe()
    testo = re.sub(r"\033\[\d+m", "", fuori.getvalue())
    assert dal_vivo.split("\n", 1)[1] in testo  # dal vivo e registrata si stampano uguali, intestazione a parte
    assert "speso in tutto" in testo and "strato 5" in testo



def test_riassunto_sulla_radice():
    s.PRODUZIONE = True
    try:
        reg, _ = corri(5)
    finally:
        s.PRODUZIONE = False
    radice = next(x for x in reg["span"] if x["padre"] is None)
    atteso = sg.riassunto({**reg, "span": [x for x in reg["span"] if x is not radice]})
    assert atteso["richiesta.forma"] and atteso["richiesta.costo_microusd"] > 0
    visti = {k: v for k, v in radice["attributi"].items() if k.startswith("richiesta.")}
    assert visti.pop("richiesta.correzione") == "nessuna" and visti.pop("richiesta.versione_prompt") == s.versione_prompt(0)
    assert visti == atteso


def test_riassunto_due_trace_insieme():
    p = sg.RiassuntoSullaRadice(5)
    tp = TracerProvider()
    tp.add_span_processor(p)
    t = tp.get_tracer("prova")
    a, b = t.start_span("invoke_workflow a"), t.start_span("invoke_workflow b")
    with trace.use_span(a):
        t.start_span("anthropic.messages.create", attributes={"gen_ai.usage.input_tokens": 1000,
                                                             "gen_ai.usage.output_tokens": 50}).end()
    assert a.attributes["richiesta.costo_microusd"] == round(s.costo(1000, 0, 50) * 1e6)
    assert "richiesta.costo_microusd" not in b.attributes
    a.end()
    b.end()
    assert all(not v for v in vars(p).values() if isinstance(v, dict))  # nessuno stato resta dopo le radici


def test_otlp_mascherato():
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    fuori, vero = InMemorySpanExporter(), s.processore_otlp
    s.processore_otlp = lambda url: SimpleSpanProcessor(fuori)  # al posto di Tempo
    vero_log, urls = s.processore_otlp_log, []
    s.processore_otlp_log = lambda url: (urls.append(url), SimpleLogRecordProcessor(InMemoryLogRecordExporter()))[1]
    s.OTLP, s.MASCHERA = "http://finto", True
    try:
        corri(5)
    finally:
        s.processore_otlp, s.processore_otlp_log, s.OTLP, s.MASCHERA = vero, vero_log, None, False
    assert urls == ["http://finto/v1/logs"]
    span = [s.in_dict(x) for x in fuori.get_finished_spans()]
    assert span and s.con_email(span) == 0  # l'email non esce dal processo neanche verso il backend


def test_produzione_dal_vivo_porta_il_banco():
    s.PRODUZIONE = True
    try:
        reg, _ = corri(5)
    finally:
        s.PRODUZIONE = False
    radice = next(x for x in reg["span"] if x["padre"] is None)
    assert radice["attributi"]["banco.cartella"] == CARTELLA.name and radice["attributi"]["banco.modo"] == "guasto"

def corri_annidato(strato=5, correzione=0, guasto=True, **scelte):
    """Una run con il modello finto che si fa chiamare fra agenti (vedi FINTO) e la correzione scelta."""
    try:
        s.CORREZIONE = correzione
        with finto(**scelte):
            return corri(strato, guasto)
    finally:
        s.CORREZIONE = 0


def percorso(reg, x):
    """I nomi degli span da x alla radice, per verificare la parentela a piu' livelli."""
    per_id, fuori = {y["id"]: y for y in reg["span"]}, []
    while x:
        fuori.append(x["nome"])
        x = per_id.get(x["padre"])
    return fuori


def arcs(reg, verso, da=None):
    return s.archi(reg["span"], (verso,), da=da)


FORMA_ANNIDATA = ("codice>coordina "
                  "coordina>{avvisi(leggi_avvisi),programma({leggi_programma,sale(leggi_sale)}),sale(leggi_sale)} "
                  "coordina>valida({avvisi(leggi_avvisi),programma({leggi_programma,sale(leggi_sale)})})")
FORMA_DIALOGO = ("codice>coordina coordina>{avvisi({leggi_avvisi,programma(leggi_programma)}),programma(leggi_programma),"
                 "sale(leggi_sale)} coordina>valida")


def test_annidate_la_parentela_a_piu_livelli():
    reg, _ = corri_annidato(annidate=True)
    assert s.esito(reg)["tracce"] == 1
    sale_ = arcs(reg, "sale")
    assert [attr_ for attr_ in sorted(s.attr(x, "gen_ai.agent.name") for x in sale_)] == ["coordina", "programma", "programma"]
    # programma>sale: l'arco di sale sta dentro invoke_agent programma, che sta dentro l'arco di programma
    da_programma = arcs(reg, "sale", da="programma")[0]
    assert percorso(reg, da_programma)[:4] == ["execute_tool sale", "invoke_agent programma", "execute_tool programma",
                                              "invoke_agent coordina"] or percorso(reg, da_programma)[:4] == [
        "execute_tool sale", "invoke_agent programma", "execute_tool programma", "invoke_agent valida"]
    # e sotto l'arco di sale annidato, il suo agente e il suo strumento
    foglie = [x for x in reg["span"] if x["nome"] == "execute_tool leggi_sale"]
    assert len(foglie) == 3 and all(percorso(reg, x)[1] == "invoke_agent sale" for x in foglie)
    # valida>programma e valida>avvisi: due archi con chiamante valida, dentro invoke_agent valida
    for verso in ("programma", "avvisi"):
        x = arcs(reg, verso, da="valida")[0]
        assert percorso(reg, x)[:3] == [f"execute_tool {verso}", "invoke_agent valida", "execute_tool valida"]
        assert s.attr(x, "gen_ai.transfer.target.name") == verso and s.attr(x, "gen_ai.transfer.mode") == "return_to_caller"
    assert len({x["trace"] for x in reg["span"]}) == 1
    assert " ".join(s.grafo(reg["span"])) == FORMA_ANNIDATA


def test_annidate_il_parallelismo_vale_a_ogni_livello():
    reg, _ = corri_annidato(annidate=True)
    ricontrolli = s.archi(reg["span"], ("programma", "avvisi"), da="valida")
    assert len(ricontrolli) == 2 and len({x["padre"] for x in ricontrolli}) == 1  # lo stesso invoke_agent valida
    assert max(x["inizio"] for x in ricontrolli) < min(x["fine"] for x in ricontrolli)  # i due ricontrolli si sovrappongono
    # e la forma non dipende da chi parte prima
    for _ in range(3):
        assert s.grafo(corri_annidato(annidate=True)[0]["span"]) == s.grafo(reg["span"])
    # in sequenza (a mano): due gruppi, non un insieme
    a, b = [dict(x) for x in ricontrolli]
    assert a["fine"] > b["inizio"]
    b["inizio"], b["fine"] = a["fine"] + 1, a["fine"] + 2
    dopo = [x for x in reg["span"] if x["id"] not in {a["id"], b["id"]}] + [a, b]
    assert "valida(" in " ".join(s.grafo(dopo)) and ",programma" not in " ".join(s.grafo(dopo)).split("coordina>valida")[1][:30]


def test_annidate_le_misure_nuove():
    reg, _ = corri_annidato(annidate=True)
    m = s.misura(reg)
    assert m["sale_da_due"] and m["valida_avvisi"] and m["valida_programma"] and m["cicli"] == 0
    assert m["valida_avvisi_riporta"] is False  # il ricontrollo chiede del workshop: avvisi non sa della sala B
    assert m["avvisi_chiede_programma"] is False and m["profondita_agenti"] == 3  # coordina>valida>programma>sale
    assert m["stesso_giro"] and not m["avvisi_dopo_sala"] and m["avvisi_riporta"] is False  # le chiamate annidate non contano
    assert m["grafo"] == FORMA_ANNIDATA
    assert m["span"] == len(reg["span"]) and m["profondita"] > 5
    base = s.misura(corri(5)[0])
    assert base["sale_da_due"] is False and base["valida_avvisi"] is False and base["profondita_agenti"] == 1
    # ogni misura ha il suo strato minimo: sotto, None
    m2 = s.misura(corri_annidato(strato=2, annidate=True)[0])
    assert m2["sale_da_due"] and m2["valida_avvisi"] and m2["valida_avvisi_riporta"] is None and m2["avvisi_poi_riporta"] is None
    m1 = s.misura(corri_annidato(strato=1, annidate=True)[0])
    assert m1["sale_da_due"] is None and m1["cicli"] is None and m1["profondita_agenti"] is None


def test_annidate_valida_chiede_la_sala_e_avvisi_riporta():
    reg, _ = corri_annidato(annidate=True, valida_sala=True)
    m = s.misura(reg)
    assert m["valida_avvisi"] and m["valida_avvisi_riporta"] is True
    assert m["valida_approva"] == 0 and m["valida_chiamate"] == 1  # valida, informata, non approva
    assert m["avvisi_riporta"] is False  # coordina non l'ha chiesto con la sala: il suo avvisi non riporta


def test_pagine_di_coordina_e_dei_ricontrolli():
    reg, _ = corri_annidato(annidate=True)  # valida rilegge gli avvisi
    m = s.misura(reg)
    assert m["pagine_avvisi"] == 40 and m["pagine_ricontrolli"] == 40
    assert sg.segnali(reg)["pagine"] == 40  # il cruscotto usa il numero di coordina
    reg, _ = corri_annidato(correzione=3, dialogo=True)  # nel dialogo avvisi e' ancora quello di coordina
    assert s.misura(reg)["pagine_avvisi"] == 40 and s.misura(reg)["pagine_ricontrolli"] == 0
    assert s.misura(corri(5)[0])["pagine_ricontrolli"] == 0


def test_annidate_il_conteggio_degli_span_su_una_run_guasta_allo_strato_5():
    reg, _ = corri_annidato(annidate=True)
    base = len(corri(5)[0]["span"])
    print(f"   span strato 5 guasto: {len(reg['span'])} con le chiamate annidate, {base} senza")
    assert len(reg["span"]) == 44 and base == 23


def test_dialogo_avvisi_chiede_a_programma():
    reg, _ = corri_annidato(correzione=3, dialogo=True)
    assert reg["correzione"] == 3
    # la correzione 3 e' un'alternativa: coordina e leggi_avvisi come nel guasto
    try:
        s.CORREZIONE = 3
        assert s.istruzioni_coordina() == s.ISTRUZIONI["coordina"]
        assert s.schemi()["leggi_avvisi"]["input_schema"].get("required") is None
        _, istr, strumenti = s.agenti_strumento()["avvisi"]
        assert istr == s.ISTRUZIONI["avvisi"] + s.CORREZIONE_DIALOGO and strumenti == ["leggi_avvisi", "programma"]
        assert "Nessun avviso" not in s.leggi_dato("leggi_avvisi", {}, {"piena": True})
    finally:
        s.CORREZIONE = 0
    assert s.CORREZIONE_DIALOGO.count(".") == 1  # una frase sola
    assert s.agenti_strumento()["avvisi"][2] == ["leggi_avvisi"] and s.agenti_strumento()["avvisi"][1] == s.ISTRUZIONI["avvisi"]
    assert any(isinstance(c.get("system"), str) and c["system"].endswith("all'agente programma.") for c in CORPI)
    m = s.misura(reg)
    assert m["avvisi_chiede_programma"] is True and m["avvisi_poi_riporta"] is True and m["avvisi_riporta"] is True
    x = arcs(reg, "programma", da="avvisi")[0]
    assert percorso(reg, x)[:3] == ["execute_tool programma", "invoke_agent avvisi", "execute_tool avvisi"]
    assert s.attr(x, "gen_ai.transfer.target.name") == "programma"
    assert m["grafo"] == FORMA_DIALOGO
    assert m["esito"] in s.ESITI
    # senza la correzione, nella stessa run, avvisi non chiede a programma
    assert s.misura(corri(5)[0])["avvisi_chiede_programma"] is False
    # il dialogo non c'e' se lo strumento non e' dato: il modello finto che vorrebbe farlo non puo'
    reg0, _ = corri_annidato(dialogo=True)
    assert s.misura(reg0)["avvisi_chiede_programma"] is False


def test_dialogo_nelle_misure_stampate():
    cartella = Path(tempfile.mkdtemp()) / "strato-5-correzione-dialogo"
    cartella.mkdir(parents=True)
    for i in range(2):
        reg, _ = corri_annidato(correzione=3, dialogo=True, annidate=True)
        (cartella / f"{i}.json").write_text(json.dumps(reg))
    with contextlib.redirect_stdout(io.StringIO()) as fuori:
        s.misure([cartella])
    testo = fuori.getvalue()
    for riga in ("avvisi chiede a programma", "...e poi avvisi riporta l'avviso", "sale chiamato da due chiamanti diversi",
                 "valida richiede ad avvisi", "valida richiede a programma", "guardia dei cicli scattata", "massimi: profondità"):
        assert riga in testo, riga
    assert " 2 su 2" in testo
    assert "guardia mai scattata" in testo  # le run finte non la fanno scattare: il conteggio e' zero e la riga lo dice
    # e quando scatta, la riga non lo dice
    scatta = Path(tempfile.mkdtemp()) / "strato-5-correzione-dialogo"
    scatta.mkdir(parents=True)
    reg_ciclo, _ = corri_annidato(correzione=3, dialogo=True, annidate=True, ciclo="avvisi")
    (scatta / "0.json").write_text(json.dumps(reg_ciclo))
    with contextlib.redirect_stdout(io.StringIO()) as fuori_ciclo:
        s.misure([scatta])
    assert "guardia dei cicli scattata" in fuori_ciclo.getvalue() and "mai scattata" not in fuori_ciclo.getvalue()
    altra = Path(tempfile.mkdtemp()) / "strato-5"  # fuori dal dialogo le righe del dialogo non ci sono
    altra.mkdir(parents=True)
    (altra / "a.json").write_text(json.dumps(corri(5)[0]))
    with contextlib.redirect_stdout(io.StringIO()) as fuori:
        s.misure([altra])
    assert "avvisi chiede a programma" not in fuori.getvalue() and "guardia dei cicli" in fuori.getvalue()


def test_guardia_contro_i_cicli_unita():
    assert s.controlla_catena("sale", ("coordina", "programma")) is None
    assert s.controlla_catena("programma", ("coordina", "programma")) == (
        "programma è già nella catena di chiamata (coordina > programma): non puoi richiamarlo.")
    assert "avvisi è già nella catena" in s.controlla_catena("avvisi", ("coordina", "avvisi", "programma"))
    assert s.controlla_catena("sale", ("coordina", "valida", "avvisi", "programma")) is None  # il ramo piu' lungo che serve
    assert "troppo profonda" in s.controlla_catena("sale", ("coordina", "valida", "avvisi", "programma", "x"))
    assert s.CATENA.get() == ()  # la catena si scioglie: nessuna eredita' fra una run e l'altra


def test_guardia_un_agente_non_richiama_se_stesso():
    reg, _ = corri_annidato(ciclo="programma")  # programma prova a richiamare programma
    ciclo_ = next(x for x in reg["span"] if x["nome"] == "execute_tool programma" and x["errore"])
    assert percorso(reg, ciclo_)[1] == "invoke_agent programma" and ciclo_["attributi"]["error.type"] == "ciclo"
    assert "programma è già nella catena di chiamata" in ciclo_["attributi"]["gen_ai.tool.call.result"]
    assert not any(x["padre"] == ciclo_["id"] for x in reg["span"])  # nessun invoke_agent sotto: la chiamata non e' partita
    assert reg["risposta"] and s.misura(reg)["cicli"] == 1 and "programma!" in s.misura(reg)["grafo"]
    # il modello vede l'errore come risultato dello strumento, marcato is_error
    tool_result = [b for c in CORPI if isinstance(c["messages"][-1]["content"], list) for b in c["messages"][-1]["content"]
                   if b.get("is_error")]
    assert tool_result and "già nella catena di chiamata" in str(tool_result[-1]["content"])
    # lo span di errore ha lo stato di errore e il colore rosso nella stampa
    assert all(not x["errore"] for x in reg["span"] if x is not ciclo_)
    reg0, _ = corri_annidato(strato=0, ciclo="programma")  # la guardia c'e' anche senza OpenTelemetry
    assert reg0["span"] == [] and reg0["risposta"]
    reg3, _ = corri_annidato(strato=3, ciclo="programma")
    assert "già nella catena" in next(x for x in reg3["span"] if x["errore"])["attributi"]["gen_ai.tool.call.result"]


def test_guardia_nel_dialogo_programma_non_richiama_avvisi():
    reg, _ = corri_annidato(correzione=3, dialogo=True, ciclo="avvisi")  # coordina>avvisi>programma>avvisi
    m = s.misura(reg)
    assert m["cicli"] == 1 and "avvisi({leggi_avvisi,programma({avvisi!,leggi_programma})})" in m["grafo"]
    ciclo_ = next(x for x in reg["span"] if x["errore"])
    assert percorso(reg, ciclo_)[:3] == ["execute_tool avvisi", "invoke_agent programma", "execute_tool programma"]
    assert reg["risposta"]  # la run finisce lo stesso


def test_codice_2_resta_pulito_con_la_guardia():
    assert "CATENA" not in s.codice(2)  # la guardia e' codice applicativo, non si marca
    assert 'span.set_attribute("error.type", "ciclo")' in s.codice(2)


def cartella_finta(n_guasto=2, n_sana=0, correzione=0, strato=5, **scelte):
    """Una cartella temporanea di registrazioni finte: n_guasto run in modo guasto, n_sana in modo sana."""
    cartella = Path(tempfile.mkdtemp()) / f"strato-{strato}"
    cartella.mkdir(parents=True)
    for i in range(n_guasto + n_sana):
        reg, _ = corri_annidato(strato=strato, correzione=correzione, guasto=i < n_guasto, **scelte)
        (cartella / f"{i}.json").write_text(json.dumps(reg))
    return cartella


def schema_di(cartella, **opzioni):
    with contextlib.redirect_stdout(io.StringIO()) as fuori:
        s.mostra_schema(cartella, **opzioni)
    return fuori.getvalue()


def test_schema_conteggi_e_rimpalli():
    cartella = cartella_finta(3, annidate=True, valida_sala=True)
    testo = schema_di(cartella)
    assert "3 run, strato 5" in testo
    assert "utente → coordina" in testo
    for riga in ("coordina → programma", "coordina → avvisi", "coordina → valida", "programma → sale", "valida → avvisi"):
        assert re.search(rf"{riga}\s+3 su 3 · +\d+ volte", testo), riga
    assert re.search(r"coordina → sale\s+3 su 3", testo)
    assert "sale chiamato da 2 chiamanti (coordina, programma): 3 run su 3" in testo
    assert "valida richiama avvisi: 3 run su 3" in testo and "valida richiama programma: 3 run su 3" in testo
    assert "riporta l'avviso sulla sala B: 3 run su 3" in testo  # valida_sala: il ricontrollo nomina la sala
    assert "avvisi chiede a programma (dialogo): 0 run su 3" in testo
    assert "guardia dei cicli scattata: 0 run su 3 · 0 volte" in testo
    assert re.search(r"coordina → leggi_\w+", testo) is None and "avvisi → leggi_avvisi" in testo  # gli strumenti sono foglie dell'agente
    assert "strumenti dei dati" in testo and "strumenti dei dati" not in schema_di(cartella, senza_strumenti=True)
    assert "leggi_avvisi" not in schema_di(cartella, senza_strumenti=True)
    # senza chiamate annidate: nessun rimpallo
    semplice = schema_di(cartella_finta(2))
    assert "nessun agente chiamato da piu' chiamanti" in semplice and "valida richiama avvisi: 0 run su 2" in semplice


def test_schema_dialogo_e_guardia():
    testo = schema_di(cartella_finta(2, correzione=3, dialogo=True, ciclo="avvisi"))
    assert "avvisi chiede a programma (dialogo): 2 run su 2" in testo
    assert "guardia dei cicli scattata: 2 run su 2 · 2 volte" in testo
    assert re.search(r"\*programma → avvisi\s+2 su 2", testo)  # l'arco respinto dalla guardia e' un rimpallo
    mermaid = testo.split("```mermaid\n")[1]
    assert "avvisi -.->|2/2| programma" in mermaid and "programma -.->|2/2| avvisi" in mermaid


def test_schema_mermaid_stabile_e_valido():
    cartella = cartella_finta(2, annidate=True, valida_sala=True)
    uno = schema_di(cartella)
    assert uno == schema_di(cartella)  # stabile
    blocco = uno.split("```mermaid\n")[1].split("```")[0].rstrip("\n").splitlines()
    assert blocco[0] == "flowchart LR" and sum(r.strip().startswith("%%") for r in blocco) == 2
    archi_ = [r.strip() for r in blocco if "-->" in r or "-.->" in r]
    for r in archi_:
        assert re.fullmatch(r"\w+ (-->|-\.->)\|[^|]+\| \w+", r), r
    assert "utente -->|2/2| coordina" in archi_
    assert "coordina -->|2/2| avvisi" in archi_
    assert "programma -->|2/2 ×2.0| sale" in archi_  # la strada normale di sale resta piena...
    assert "valida -.->|2/2| avvisi" in archi_  # ...i controlli di valida sono tratteggiati
    assert "coordina -->|2/2| sale" in archi_  # coordina → sale resta un arco pieno, ma in rosso (sotto)
    # linkStyle: tratteggiati in grigio, la strada in piu' coordina → sale in rosso (indici numerati dal primo arco scritto)
    scritti = [r for r in blocco if "-->" in r or "-.->" in r]
    grigi = next(r for r in blocco if r.strip().startswith("linkStyle") and "#7f8c8d" in r).split()[1].split(",")
    rossi = next(r for r in blocco if r.strip().startswith("linkStyle") and "#c0392b" in r).split()[1].split(",")
    assert [i for i, r in enumerate(scritti) if "-.->" in r] == [int(i) for i in grigi]
    assert [scritti[int(i)].strip() for i in rossi] == ["coordina -->|2/2| sale"]
    assert sum(r.strip().startswith("linkStyle") for r in blocco) == 2
    leggenda = " ".join(r for r in blocco if r.strip().startswith("%%"))
    assert "tratteggiato = chi controlla o chiede a una fonte fuori dal giro di coordina" in leggenda
    assert "rosso = coordina → sale quando sale e' chiamato anche da programma" in leggenda
    nodi = [r.strip() for r in blocco if re.fullmatch(r"\s+\w+(\[\w+\]|\(\[\w+\]\))", r)]
    assert nodi == ["utente([utente])", "coordina[coordina]", "programma[programma]", "sale[sale]", "avvisi[avvisi]", "valida[valida]"]


def test_schema_volte_per_run_nell_etichetta():
    regs = [json.loads(f.read_text()) for f in sorted(cartella_finta(1).glob("*.json"))]
    sdoppiato = json.loads(json.dumps(regs[0]))
    # una chiamata in piu' coordina → sale nella stessa run: 2 volte, in 1 run
    x = next(y for y in sdoppiato["span"] if s.attr(y, "gen_ai.transfer.target.name") == "sale")
    y = json.loads(json.dumps(x))
    y["id"] = "duplicato"
    sdoppiato["span"].append(y)
    _, mermaid = s.schema([sdoppiato])
    assert "coordina -->|1/1 ×2.0| sale" in mermaid and "coordina -->|1/1| programma" in mermaid
    assert "#c0392b" not in mermaid  # sale e' chiamato solo da coordina: nessuna strada in piu'
    # la media si arrotonda a un decimale: 3 volte in 2 run = ×1.5, 7 in 3 = ×2.3, e 1.04 non e' piu' di 1
    base = json.loads(json.dumps(regs[0]))
    due = [json.loads(json.dumps(base)), sdoppiato]  # 1 chiamata in una run, 2 nell'altra
    _, m3 = s.schema(due)
    assert "coordina -->|2/2 ×1.5| sale" in m3


def test_schema_filtra_per_modo():
    cartella = cartella_finta(n_guasto=2, n_sana=1, annidate=True)
    assert "3 run" in schema_di(cartella)
    assert "2 run, strato 5" in schema_di(cartella, modo="guasto")
    assert "1 run, strato 5" in schema_di(cartella, modo="sana")
    assert "nessuna registrazione in modo sana" in schema_di(cartella_finta(2), modo="sana")


def test_schema_sotto_lo_strato_2_e_sotto_il_3():
    assert "serve lo strato 2" in schema_di(cartella_finta(1, strato=1))
    testo = schema_di(cartella_finta(1, strato=2, annidate=True))
    assert "2 run" not in testo and "strato 2" in testo and "```mermaid" in testo
    assert "riporta l'avviso sulla sala B: serve lo strato 3" in testo
    assert "serve lo strato 2" not in testo

# Gli hash del testo che il modello legge, per modalita' di correzione, fissati sul banco del 5/11 (tag banco-2026-11-05):
# le istruzioni non sono cambiate dopo il banco, e tempo.py ricava da qui la versione delle registrazioni che non l'hanno.
# Se questo test fallisce hai cambiato un'istruzione o una descrizione: le registrazioni del banco non sono piu' di questa
# versione, e va aggiornata la tabella in docs/banco-rami-paralleli.md.
HASH_BANCO = {0: "8909d44b", 1: "1d2a1b7e", 2: "ead55ac1", 3: "d8d06c33"}


def test_versione_prompt_stabile_e_per_modalita():
    assert {m: s.versione_prompt(m) for m in range(4)} == HASH_BANCO
    assert len(set(HASH_BANCO.values())) == 4  # quattro modalita', quattro testi diversi
    assert s.versione_prompt(1) == s.versione_prompt(1)
    s.CORREZIONE = 2
    try:
        assert s.versione_prompt() == HASH_BANCO[2]  # senza argomento, la modalita' in corso
    finally:
        s.CORREZIONE = 0


def test_versione_prompt_cambia_se_cambia_un_testo():
    base = s.versione_prompt(0)
    for chiave, dove in (("coordina", s.ISTRUZIONI), ("avvisi", s.ISTRUZIONI), ("avvisi", s.DESCRIZIONI)):
        prima = dove[chiave]
        dove[chiave] = prima + " "
        try:
            assert s.versione_prompt(0) != base, (chiave, dove is s.ISTRUZIONI)
        finally:
            dove[chiave] = prima
    prima = s.CORREZIONE_COORDINA  # una frase di correzione cambia solo le modalita' che la usano
    s.CORREZIONE_COORDINA = prima + "!"
    try:
        assert s.versione_prompt(0) == base and s.versione_prompt(1) != HASH_BANCO[1] and s.versione_prompt(3) == HASH_BANCO[3]
    finally:
        s.CORREZIONE_COORDINA = prima
    assert s.versione_prompt(0) == base


def test_versione_nella_trace_nella_resource_e_nella_registrazione():
    reg, _ = corri(5)
    radice = next(x for x in reg["span"] if x["padre"] is None)
    assert radice["attributi"]["richiesta.correzione"] == "nessuna"
    assert radice["attributi"]["richiesta.versione_prompt"] == HASH_BANCO[0]
    assert reg["versione"] == {"codice": s.VERSIONE, "correzione": "nessuna", "prompt": HASH_BANCO[0]}
    for x in s.memoria.get_finished_spans():
        assert x.resource.attributes["service.name"] == "osservare-a-strati"
        assert x.resource.attributes["service.version"] == s.VERSIONE
    assert s._provider_log.resource.attributes["service.version"] == s.VERSIONE  # anche i log
    s.CORREZIONE = 2
    try:
        reg, _ = corri(5)
    finally:
        s.CORREZIONE = 0
    assert reg["versione"]["correzione"] == "filtro" and reg["versione"]["prompt"] == HASH_BANCO[2]


def test_maschera_niente_email_negli_span_ne_nei_log():
    try:
        s.MASCHERA = True
        reg, _ = corri(5)
    finally:
        s.MASCHERA = False
    assert reg["log_otel"]  # i log ci sono...
    assert not any(s.EMAIL.search(str(l["testo"])) for l in reg["log_otel"])  # ...e senza email
    assert not any(s.EMAIL.search(json.dumps(x["attributi"], ensure_ascii=False)) for x in reg["span"])
    assert not any(s.EMAIL.search(json.dumps(x.attributes.get("gen_ai.input.messages", ""), ensure_ascii=False))
                   for x in s.memoria.get_finished_spans())
    assert reg["versione"]["codice"] == s.VERSIONE and reg["maschera"] is True


def test_classe_della_domanda_ad_avvisi():
    for testo in ('Workshop "Kubernetes da zero" orario, sala o variazioni', "workshop Kubernetes da zero: variazioni di orario o sala",
                  "sala B chiusura manutenzione pomeriggio oggi", "Kubernetes da zero: cambi o annullamenti"):
        assert s.classe_domanda(testo) == "variazioni", testo
    for testo in ("Workshop Kubernetes da zero", 'Workshop "Kubernetes da zero"', "workshop Kubernetes da zero", ""):
        assert s.classe_domanda(testo) == "sessione", testo


def test_tabella_domande_sul_server_finto():
    reg, _ = corri(5)
    assert s.domande_ad_avvisi(reg["span"]) == ["Ci sono avvisi sul workshop Kubernetes da zero?"]
    m = s.misura(reg)
    assert m["classe_domanda"] == "sessione" and m["avvisi_riporta_primo"] is False
    assert s.misura({**reg, "strato": 2})["classe_domanda"] is None  # sotto lo strato 3 non si misura
    cartella = Path(tempfile.mkdtemp()) / "strato-5"
    cartella.mkdir(parents=True)
    (cartella / "a.json").write_text(json.dumps(reg))
    with contextlib.redirect_stdout(io.StringIO()) as fuori:
        s.misure([cartella])
    testo = fuori.getvalue()
    assert "domanda di coordina ad avvisi × esito" in testo and "nomina solo la sessione" in testo
    assert "nomina orario, sala, variazioni" not in testo  # classe vuota: non si stampa


def test_classe_domanda_sulle_richieste_vere_del_banco():
    """Le domande di coordina ad avvisi del banco del 5/11 (strato-5, guasto): 8 nominano variazioni, 22 solo la sessione."""
    cartella = s.QUI / "registrazioni" / "strato-5"
    if not cartella.is_dir():
        return  # repo senza banco
    classi = {}
    for f in sorted(cartella.glob("*.json")):
        r = json.loads(f.read_text())
        if r["modo"] == "guasto":
            for q in s.domande_ad_avvisi(r["span"])[:1]:
                classi.setdefault(s.classe_domanda(q), []).append((q, s.valuta(r["risposta"], "guasto")))
    assert {k: len(v) for k, v in classi.items()} == {"variazioni": 8, "sessione": 22}
    assert all("variazioni" in q or "orario" in q for q, _ in classi["variazioni"])
    assert sum(e == "avvisata" for _, e in classi["variazioni"]) == 7


if __name__ == "__main__":
    for nome, prova in list(globals().items()):
        if nome.startswith("test_"):
            prova()
            print("ok", nome)
