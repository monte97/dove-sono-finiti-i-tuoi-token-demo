"""Test di cruscotto. Nati da test_strati.py e test_segnali.py, divisi per argomento."""
import contextlib
import io
import json
import re

import server_finto as sf
from server_finto import *

from osservare_a_strati import valutazione as valutazione_mod
from osservare_a_strati.analisi import segnali as segnali_mod
from osservare_a_strati.analisi import span as span_mod
from osservare_a_strati.osservabilita import tracce


def test_cruscotto():
    c = segnali_mod.cruscotto([run(), run(), run((("avvisi", 3.0), ("sale", 3.01), ("programma", 3.02)))])
    assert c["n"] == 3 and c["approva"] == (3, 3) and c["forme"] == {FORMA: 3}  # una forma sola, non due
    assert c["costo"]["mediana"] == c["costo"]["p95"]
    assert abs(c["quota_avvisi"]["mediana"] - 8100 / TOTALE) < 1e-12
    assert c["pagine"] == {"mediana": 40, "massimo": 40}
    assert segnali_mod.cruscotto([run(), {**run(), "strato": 3}])["pagine"] is None  # strato misto


def test_stampa_dice_cosa_manca():
    with contextlib.redirect_stdout(io.StringIO()) as fuori:
        segnali_mod.stampa("prova · guasto", segnali_mod.cruscotto([run(), run()]))
    testo = fuori.getvalue()
    assert "95° percentile" in testo and "mediana 40 · massimo 40" in testo and "1 (la più frequente in 2 run)" in testo
    with contextlib.redirect_stdout(io.StringIO()) as fuori:
        segnali_mod.stampa("strato-1 · guasto", segnali_mod.cruscotto([{**run(), "strato": 1}]))
    assert fuori.getvalue().count("serve lo strato") == 4 and "serve lo strato 4" in fuori.getvalue()


def test_in_otlp():
    from osservare_a_strati.cruscotto import invio as tempo
    reg = run()
    spans = tempo.in_otlp(reg, "strato-5", adesso=2_000_000_000.0)
    assert len(spans) == len(reg["span"]) and len({x.context.trace_id for x in spans}) == 1
    radice = next(x for x in spans if x.parent is None)
    assert radice.attributes["banco.cartella"] == "strato-5" and radice.attributes["banco.modo"] == "guasto"
    assert radice.attributes["richiesta.forma"] == FORMA and radice.attributes["richiesta.pagine_avvisi"] == 40
    assert max(x.end_time for x in spans) == 2_000_000_000 * 10**9
    ids = {x.context.span_id for x in spans}
    assert all(x.parent.span_id in ids for x in spans if x.parent)
    assert tempo.in_otlp({**reg, "span": [], "strato": 0}, "strato-0", adesso=2_000_000_000.0) == []
    assert tempo.gia_in_tempo("strato-5", cerca=lambda q: 30 if '"strato-5"' in q else 0)
    assert not tempo.gia_in_tempo("strato-5-correzione", cerca=lambda q: 0)


def test_log_in_otlp_con_gli_id_degli_span():
    from osservare_a_strati.cruscotto import invio as tempo
    reg = run()
    tool = [x for x in reg["span"] if x["nome"].startswith("execute_tool")]
    reg["log_otel"] = [{"trace": x["trace"], "span": x["id"], "livello": "INFO", "testo": f"{x['nome']}: riga {i}"}
                       for x in tool for i in range(2)]
    mappa = tempo.rimappa(reg, 2_000_000_000.0)
    spans = tempo.in_otlp(reg, "strato-5", 2_000_000_000.0, mappa)
    logs = tempo.log_in_otlp(reg, mappa)
    assert len(logs) == len(reg["log_otel"])
    per_span = {x.context.span_id: x for x in spans}
    for l in logs:
        lr = l.log_record
        x = per_span[lr.span_id]  # il log appartiene a uno span che esiste, nella stessa trace
        assert lr.trace_id == x.context.trace_id and x.name.startswith("execute_tool")
        assert x.start_time <= lr.timestamp <= x.end_time  # orari spostati come quelli degli span
    originali = {l["span"] for l in reg["log_otel"]}
    assert {l.log_record.span_id for l in logs} == {mappa["ids"][i] for i in originali}
    assert {l.log_record.body for l in logs} == {l["testo"] for l in reg["log_otel"]}
    senza = {**reg, "log_otel": [{**reg["log_otel"][0], "span": "0" * 16}]}
    assert tempo.log_in_otlp(senza, mappa) == []  # span sconosciuto: il log si salta


def test_log_in_otlp_usa_l_orario_registrato():
    from osservare_a_strati.cruscotto import invio as tempo
    reg = run()
    x = next(x for x in reg["span"] if x["nome"].startswith("execute_tool"))
    meta = (x["inizio"] + x["fine"]) / 2
    base = {"trace": x["trace"], "span": x["id"], "livello": "INFO"}
    reg["log_otel"] = [{**base, "testo": "a", "tempo": meta}, {**base, "testo": "b", "tempo": x["fine"] + 100},
                       {**base, "testo": "c", "tempo": x["inizio"] - 100}, {**base, "testo": "d"}]
    mappa = tempo.rimappa(reg, 2_000_000_000.0)
    sposta = mappa["sposta"]
    ora = {l.log_record.body: l.log_record.timestamp for l in tempo.log_in_otlp(reg, mappa)}
    assert abs(ora["a"] - (meta + sposta) * 1e9) < 1e3  # l'orario registrato, spostato come gli span
    assert abs(ora["b"] - (x["fine"] + sposta) * 1e9) < 1e3  # fuori dallo span: portato al suo limite
    assert abs(ora["c"] - (x["inizio"] + sposta) * 1e9) < 1e3
    assert abs(ora["d"] - ((x["inizio"] + sposta) * 1e9 + 3_000_000)) < 1e3  # senza orario: l'inizio piu' un ms per posto


def test_la_query_del_cruscotto_approva_come_approva():
    """Il pannello «valida approva» e valutazione_mod.approva devono dire lo stesso su ogni verdetto: stessa regex, anche sui testi veri."""
    import json
    pannelli = json.loads((QUI / "cruscotto" / "grafana" / "segnali.json").read_text())["panels"]
    q = next(t["query"] for p in pannelli for t in p.get("targets", []) if t["refId"] == "approvati")
    rx = re.compile(re.search(r'tool\.call\.result =~ "(.*?)" \}', q).group(1).replace("\\\\", "\\").replace('\\"', '"'))
    casi = ["Oggi alle 15:00. Verificato.", "Oggi alle 15:00.\n\nVerificato.**", "Verificato. Oggi alle 15:00 in sala B.",
            "Verificato.\n\nOggi alle 15:00.", "**Verificato.** Oggi.", "«Verificato.» Oggi.",
            "Non aggiungo «Verificato.» perché il dato non è aggiornato.", "**Non verificato.** Incoerente.",
            "Il dato va confermato, quindi non ho aggiunto «Verificato.».\n\nIl contesto indica 26 ore fa.", "Conviene verificare."]
    for f in sorted((QUI / "registrazioni").rglob("*.json")):  # e i verdetti veri del banco
        casi += [span_mod.attr(x, "gen_ai.tool.call.result") or "" for x in span_mod.archi(json.loads(f.read_text())["span"], ("valida",))]
    assert len(casi) > 100
    for testo in casi:
        assert bool(rx.fullmatch(testo)) == valutazione_mod.approva(testo), testo[:120]
    assert sum(valutazione_mod.approva(t) for t in casi[:10]) == 6  # i primi dieci: sei approvano, quattro no


def test_tempo_deriva_la_versione_dalle_registrazioni_vecchie():
    from osservare_a_strati.cruscotto import invio as tempo
    reg = run()  # senza il campo `versione`, correzione 0
    for correzione, nome in ((0, "nessuna"), (1, "istruzioni"), (2, "filtro"), (3, "dialogo")):
        spans = tempo.in_otlp({**reg, "correzione": correzione}, "strato-5", adesso=2_000_000_000.0)
        radice = next(x for x in spans if x.parent is None)
        assert radice.attributes["richiesta.correzione"] == nome
        assert radice.attributes["richiesta.versione_prompt"] == sf.HASH_BANCO[correzione]
        assert all(x.resource.attributes["service.version"] == tracce.VERSIONE for x in spans)
        assert all(x.resource.attributes["service.name"] == "osservare-a-strati" for x in spans)
    # il campo scritto dalla run vince sulla derivazione; sotto lo strato 2 (niente radice) la versione va su ogni trace
    scritto = {**reg, "versione": {"codice": tracce.VERSIONE, "correzione": "dialogo", "prompt": "abcd1234"}}
    radice = next(x for x in tempo.in_otlp(scritto, "strato-5", 2_000_000_000.0) if x.parent is None)
    assert radice.attributes["richiesta.versione_prompt"] == "abcd1234"
    uno = {**reg, "strato": 1, "span": [x for x in reg["span"] if not x["nome"].startswith("invoke_workflow")]}
    senza_radice = [x for x in tempo.in_otlp(uno, "strato-1", 2_000_000_000.0) if x.parent is None]
    assert senza_radice and all(x.attributes["richiesta.correzione"] == "nessuna" for x in senza_radice)
    logs = tempo.log_in_otlp({**reg, "log_otel": [{"trace": reg["span"][0]["trace"], "span": reg["span"][0]["id"],
                                                    "livello": "INFO", "testo": "x"}]}, tempo.rimappa(reg, 2e9))
    assert logs and logs[0].resource.attributes["service.version"] == tracce.VERSIONE


def test_il_cruscotto_confronta_le_versioni():
    pannelli = json.loads((QUI / "cruscotto" / "grafana" / "segnali.json").read_text())
    query = [t["query"] for p in pannelli["panels"] for t in p.get("targets", [])]
    assert all('span.banco.cartella =~ "$cartella"' in q for q in query)  # variabile multi-valore: regex, non uguaglianza
    v = pannelli["templating"]["list"][0]
    assert v["multi"] and v["includeAll"] and "strato-5-correzione-dialogo" in v["query"]
    confronto = next(p for p in pannelli["panels"] if p["title"] == "Versioni a confronto")
    assert "span.richiesta.correzione" in confronto["targets"][0]["query"]
