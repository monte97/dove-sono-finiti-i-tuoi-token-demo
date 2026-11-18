"""Test di strumenti. Nati da test_strati.py e test_segnali.py, divisi per argomento."""
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


def test_il_piano_e_nelle_istruzioni_di_coordina():
    assert "piano" in s.istruzioni_coordina() and "ora, sala e piano" in s.istruzioni_coordina()


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


def test_strumento_sconosciuto_e_un_errore():
    r = json.loads(s.leggi_dato("leggi_meteo", {}, {"piena": True}))
    assert r == {"errore": "strumento sconosciuto: leggi_meteo"}


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


def test_annidate_valida_chiede_la_sala_e_avvisi_riporta():
    reg, _ = corri_annidato(annidate=True, valida_sala=True)
    m = s.misura(reg)
    assert m["valida_avvisi"] and m["valida_avvisi_riporta"] is True
    assert m["valida_approva"] == 0 and m["valida_chiamate"] == 1  # valida, informata, non approva
    assert m["avvisi_riporta"] is False  # coordina non l'ha chiesto con la sala: il suo avvisi non riporta


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
