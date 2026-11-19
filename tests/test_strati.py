"""Test di strati. Nati da test_strati.py e test_segnali.py, divisi per argomento."""
import contextlib
import io
import json
import re
import tempfile
import threading
import time
from pathlib import Path

import httpx2 as httpx
import server_finto as sf
from opentelemetry import trace
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.trace import TracerProvider
from server_finto import *  # noqa: F401,F403
from osservare_a_strati.agenti import prompt as p
from osservare_a_strati.impostazioni import con
from osservare_a_strati.osservabilita import log as oslog
from osservare_a_strati.osservabilita import tracce

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
    assert "TOKEN_IN.add(ingresso, attributi)" in codice1 and "if attuali" not in codice1


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


def test_maschera_email():
    with con(maschera=True):
        reg, fuori = corri(5)
    assert s.con_email(reg["span"]) == 0 and "email dell'utente" not in fuori
    assert any("[email]" in (x["attributi"].get("gen_ai.input.messages") or "") for x in reg["span"])
    assert "[email]" in attributi(reg, "execute_tool valida")["gen_ai.tool.call.arguments"]  # anche dentro il JSON
    assert all(reg["span"][0]["attributi"][k] == "oscurato" for k in s.ID_ACCOUNT)
    reg, _ = corri(5)
    assert s.con_email(reg["span"]) > 0  # senza maschera l'email resta


def test_codice_pulito():
    for n in range(6):  # niente impalcatura della demo in nessuno strato (revisione finale, I2)
        assert "fai_provider" not in s.codice(n) and not re.search(r"\bif attuali\(\)\.strato", s.codice(n)), n
    assert 'modo = "content"' in s.codice(5) and "MascheraEmail(processore)" in s.codice(5)
    assert "MascheraEmail" not in s.codice(1) and '"tracer_provider": provider' in s.codice(1)
    assert "open_telemetry=" in s.codice(1) and "**prova" not in s.codice(1)  # la slide non porta l'argomento dei test
    assert not s.codice(3).rstrip().endswith("fai_log()")  # niente chiamata orfana in fondo
    t = s.codice(3)
    assert 'span.set_attribute("gen_ai.tool.call.arguments"' in t and "if attuali" not in t
    assert "\nspan.set_attribute(\"gen_ai.tool.call.arguments\"" in t  # il corpo dell'if perde il rientro
    assert not any(b.startswith((" ", "\t")) for b in s.codice(0).split("\n...\n"))  # lo strato 0 esce a margine, senza il lock
    assert "lock" not in s.codice(0) and 'stato["fattura"].append(r.usage)' in s.codice(0)
    assert '"out": sum(x.output_tokens for x in u)},' in s.codice(0)  # il dizionario della fattura e' intero
    assert "cache.read" not in open(s.__file__).read()


def test_otlp_mascherato():
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    fuori, vero = InMemorySpanExporter(), tracce.processore_otlp
    tracce.processore_otlp = lambda url: SimpleSpanProcessor(fuori)  # al posto di Tempo
    vero_log, urls = oslog.processore_otlp_log, []
    oslog.processore_otlp_log = lambda url: (urls.append(url), SimpleLogRecordProcessor(InMemoryLogRecordExporter()))[1]
    try:
        with con(otlp="http://finto", maschera=True):
            corri(5)
    finally:
        tracce.processore_otlp, oslog.processore_otlp_log = vero, vero_log
    assert urls == ["http://finto/v1/logs"]
    span = [s.in_dict(x) for x in fuori.get_finished_spans()]
    assert span and s.con_email(span) == 0  # l'email non esce dal processo neanche verso il backend


def test_produzione_dal_vivo_porta_il_banco():
    with con(produzione=True):
        reg, _ = corri(5)
    radice = next(x for x in reg["span"] if x["padre"] is None)
    assert radice["attributi"]["banco.cartella"] == CARTELLA.name and radice["attributi"]["banco.modo"] == "guasto"


def test_annidate_il_conteggio_degli_span_su_una_run_guasta_allo_strato_5():
    reg, _ = corri_annidato(annidate=True)
    base = len(corri(5)[0]["span"])
    print(f"   span strato 5 guasto: {len(reg['span'])} con le chiamate annidate, {base} senza")
    assert len(reg["span"]) == 44 and base == 23


def test_codice_2_resta_pulito_con_la_guardia():
    assert "CATENA" not in s.codice(2)  # la guardia e' codice applicativo, non si marca
    assert 'span.set_attribute("error.type", "ciclo")' in s.codice(2)


def test_versione_prompt_stabile_e_per_modalita():
    assert {m: s.versione_prompt(m) for m in range(4)} == HASH_BANCO
    assert len(set(HASH_BANCO.values())) == 4  # quattro modalita', quattro testi diversi
    assert s.versione_prompt(1) == s.versione_prompt(1)
    with con(correzione=2):
        assert s.versione_prompt() == HASH_BANCO[2]  # senza argomento, la modalita' in corso


def test_versione_prompt_cambia_se_cambia_un_testo():
    base = s.versione_prompt(0)
    for chiave, dove in (("coordina", p.ISTRUZIONI), ("avvisi", p.ISTRUZIONI), ("avvisi", p.DESCRIZIONI)):
        prima = dove[chiave]
        dove[chiave] = prima + " "
        try:
            assert s.versione_prompt(0) != base, (chiave, dove is p.ISTRUZIONI)
        finally:
            dove[chiave] = prima
    prima = p.CORREZIONE_COORDINA  # una frase di correzione cambia solo le modalita' che la usano
    p.CORREZIONE_COORDINA = prima + "!"
    try:
        assert s.versione_prompt(0) == base and s.versione_prompt(1) != HASH_BANCO[1] and s.versione_prompt(3) == HASH_BANCO[3]
    finally:
        p.CORREZIONE_COORDINA = prima
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
    with con(correzione=2):
        reg, _ = corri(5)
    assert reg["versione"]["correzione"] == "filtro" and reg["versione"]["prompt"] == HASH_BANCO[2]


def test_maschera_niente_email_negli_span_ne_nei_log():
    with con(maschera=True):
        reg, _ = corri(5)
    assert reg["log_otel"]  # i log ci sono...
    assert not any(s.EMAIL.search(str(l["testo"])) for l in reg["log_otel"])  # ...e senza email
    assert not any(s.EMAIL.search(json.dumps(x["attributi"], ensure_ascii=False)) for x in reg["span"])
    assert not any(s.EMAIL.search(json.dumps(x.attributes.get("gen_ai.input.messages", ""), ensure_ascii=False))
                   for x in s.memoria.get_finished_spans())
    assert reg["versione"]["codice"] == s.VERSIONE and reg["maschera"] is True
