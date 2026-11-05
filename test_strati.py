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


def risposta_finta(richiesta):
    """Simula Claude. coordina chiama programma, sale, avvisi, poi valida, poi risponde; i tre agenti chiamano il
    loro strumento e rispondono; avvisi non riporta l'avviso sulla sala B (e' lo sbaglio che la demo osserva).
    Senza strumenti risponde come valida."""
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

    def chiama(nome, argomenti):
        contenuto = [pensiero, {"type": "tool_use", "id": f"t{len(messaggi)}-{nome}", "name": nome, "input": argomenti}]
        return httpx.Response(200, headers=INTESTAZIONI, json={**base, "stop_reason": "tool_use", "content": contenuto})

    def rispondi(testo):
        return httpx.Response(200, headers=INTESTAZIONI,
                              json={**base, "stop_reason": "end_turn", "content": [pensiero, {"type": "text", "text": testo}]})

    if "programma" in strumenti:  # coordina
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
    if dati and len(messaggi) == 1:
        argomenti = {c: ("B" if c == "sala" else "Kubernetes da zero") for c in dati["input_schema"].get("required", [])}
        time.sleep(PAUSA)  # solo nel test: i tre rami si sovrappongono sempre
        return chiama(dati["name"], argomenti)
    if dati:
        return rispondi({"leggi_programma": "Oggi alle 15:00, sala B.", "leggi_sale": "Sala B, primo piano, 80 posti.",
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
    assert len(reg["log_otel"]) == 3 and all(r["trace"] == traccia and r["livello"] == "INFO" for r in reg["log_otel"])
    per_testo = {r["testo"].split(":")[0]: r for r in reg["log_otel"]}  # scritti da thread diversi, ordine libero
    for nome, r in per_testo.items():
        assert r["span"] == id_span[nome] and len(r["span"]) == 16 and len(r["trace"]) == 32
    assert "leggi_avvisi: 40 pagine, 400 avvisi, filtro nessuno" in per_testo["leggi_avvisi"]["testo"]
    assert "leggi_programma: Kubernetes da zero dal programma pubblicato il 4/11 alle 18:00" in per_testo["leggi_programma"]["testo"]
    assert "log con contesto" in fuori and "[execute_tool leggi_avvisi]" in fuori
    assert len(s.LOG.handlers) == 1  # un solo handler, non uno per run
    corri(3)
    assert len(s.LOG.handlers) == 1 and len(corri(3)[0]["log_otel"]) == 3  # non si accumulano fra le run


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


def test_esito_per_modo():
    assert s.sbagliata("Oggi alle 15:00, sala B.", "guasto") and s.giusta("Oggi alle 14:00, sala B.", "guasto")
    assert not s.giusta("Oggi alle 15:00 (anzi, 14:00).", "guasto") and not s.sbagliata("Alle 14:00.", "guasto")
    assert s.giusta("Oggi alle 15:00, sala B.", "sana") and s.sbagliata("Oggi alle 14:00, sala B.", "sana")
    assert not s.giusta("Alle 15:00 o forse alle 14:00.", "sana")


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
    assert any("allarme" in v and "11:00" in v for v in rumore) and any("domani" in v for v in rumore)
    assert not any("sala b" in v.lower() for p in tranquilla for v in p)


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
    assert "open_telemetry=" in s.codice(1)
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


def test_replay_registrazione_dello_spike():
    reg, _ = corri(3)
    vecchia = {**json.loads(json.dumps(reg)), "variante": "A"}  # come le registrazioni nel tag spike-a-b
    with contextlib.redirect_stdout(io.StringIO()) as fuori:
        s.mostra(vecchia, registrata=True)
    assert "variante A" in fuori.getvalue().splitlines()[0]


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
    assert {k: v for k, v in radice["attributi"].items() if k.startswith("richiesta.")} == atteso


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

if __name__ == "__main__":
    for nome, prova in list(globals().items()):
        if nome.startswith("test_"):
            prova()
            print("ok", nome)
