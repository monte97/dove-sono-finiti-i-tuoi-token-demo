"""Test di misure. Nati da test_strati.py e test_segnali.py, divisi per argomento."""
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
from opentelemetry.sdk.trace import TracerProvider
from server_finto import *  # noqa: F401,F403
from osservare_a_strati.impostazioni import con

def test_replay_registrazione_dello_spike():
    reg, _ = corri(3)
    vecchia = {**json.loads(json.dumps(reg)), "variante": "A"}  # come le registrazioni nel tag spike-a-b
    with contextlib.redirect_stdout(io.StringIO()) as fuori:
        s.mostra(vecchia, registrata=True)
    assert "variante A" in fuori.getvalue().splitlines()[0]


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

    with con(strato=2):
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


def test_pagine_di_coordina_e_dei_ricontrolli():
    reg, _ = corri_annidato(annidate=True)  # valida rilegge gli avvisi
    m = s.misura(reg)
    assert m["pagine_avvisi"] == 40 and m["pagine_ricontrolli"] == 40
    assert sg.segnali(reg)["pagine"] == 40  # il cruscotto usa il numero di coordina
    reg, _ = corri_annidato(correzione=3, dialogo=True)  # nel dialogo avvisi e' ancora quello di coordina
    assert s.misura(reg)["pagine_avvisi"] == 40 and s.misura(reg)["pagine_ricontrolli"] == 0
    assert s.misura(corri(5)[0])["pagine_ricontrolli"] == 0


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


def test_misure_di_una_run_finta():
    m = s.misura(run())
    assert m["grafo"] == FORMA and m["stesso_giro"] is True and m["avvisi_dopo_sala"] is False
    assert m["pagine_avvisi"] == 40 and m["tool_ha_avviso"] is True and m["avvisi_riporta"] is False
    assert m["valida_chiamate"] == 1 and m["valida_approva"] == 1 and m["email_a_valida"] is True
    assert m["token_agente"] == {"coordina": 1050, "programma": 1050, "sale": 1050, "avvisi": 8100, "valida": 2100}
    assert abs(m["quota_avvisi"] - 8100 / TOTALE) < 1e-12
    dopo = s.misura(run((("programma", 3.0), ("sale", 3.01), ("avvisi", 6.5))))
    assert dopo["stesso_giro"] is False and dopo["avvisi_dopo_sala"] is True
    assert s.misura(run(**{"gen_ai.tool.call.result": "Sala B chiusa dalle 15:00: le sessioni anticipano di un'ora."}))["avvisi_riporta"]
    assert s.misura({**run(), "strato": 2})["pagine_avvisi"] is None and s.misura({**run(), "strato": 2})["tool_ha_avviso"] is None
    assert s.misura({**run(), "strato": 2})["stesso_giro"] is True


def test_coerenza_fra_segnali_e_misura_sul_server_finto():
    for strato in (2, 3, 4, 5):
        reg, _ = sf.corri(strato)
        g, m = sg.segnali(reg), s.misura(reg)
        assert g["forma"] == m["grafo"] and g["pagine"] == m["pagine_avvisi"] and g["quota_avvisi"] == m["quota_avvisi"]
        assert (g["verdetti"] is None) == (m["valida_chiamate"] is None)
        if strato >= 3:
            assert sum(g["verdetti"]) == m["valida_approva"] and len(g["verdetti"]) == m["valida_chiamate"]
        assert abs(g["costo"] - s.costo(reg["fattura"]["in"], reg["fattura"]["cache"], reg["fattura"]["out"])) < 1e-9
    assert m["grafo"] == FORMA and m["pagine_avvisi"] == 40 and m["stesso_giro"] and not m["avvisi_dopo_sala"]
    assert m["tool_ha_avviso"] and not m["avvisi_riporta"]  # lo sbaglio che la demo osserva
    reg, _ = sf.corri(5, guasto=False)
    m = s.misura(reg)
    assert m["pagine_avvisi"] == 3 and not m["tool_ha_avviso"] and sg.segnali(reg)["pagine"] == 3


def test_costo_per_agente_e_riletture():
    reg = run()
    reg["span"] += [chat("m-avvisi-2", "g-avvisi", 5.0, 9000, 0, 100), chat("m-co-2", "co", 6.0, 1500, 500, 20)]
    assert round(s.costo_per_agente(reg["span"])["avvisi"] * 1e6) == round(s.costo(8000, 0, 100) * 1e6 + s.costo(9000, 0, 100) * 1e6)
    assert round(s.costo_per_agente(reg["span"])["coordina"] * 1e6) == round((s.costo(1000, 0, 50) + s.costo(1500, 500, 20)) * 1e6)
    # riletti: avvisi rilegge gli 8000 della prima chiamata, coordina i 1000 della sua; ingresso totale = 14000 + 9000 + 1500
    assert s.quota_riletture(reg["span"]) == (8000 + 1000) / (1000 + 1000 + 1000 + 8000 + 2000 + 9000 + 1500)
    assert s.quota_riletture([x for x in run()["span"]]) == 0  # una chiamata per invoke_agent: niente da rileggere
    assert s.quota_riletture([]) is None
    m = s.misura(reg)
    assert m["riletture"] == s.quota_riletture(reg["span"]) and set(m["costo_agente"]) >= {"coordina", "avvisi", "valida"}
    assert s.misura({**reg, "strato": 1})["riletture"] is None and s.misura({**reg, "strato": 1})["costo_agente"] is None
