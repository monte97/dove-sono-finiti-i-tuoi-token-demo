"""Controlli senza rete: cosa cattura ogni strato contro un server finto. Uso: python test_strati.py"""
import contextlib
import io
import json
import re
import tempfile
from pathlib import Path

import httpx2 as httpx

import strati as s

s.TIMEOUT_S = 0.01
CARTELLA = Path(tempfile.mkdtemp())
INTESTAZIONI = {"request-id": "req_finto", "anthropic-organization-id": "org-finta", "anthropic-workspace-id": "wrk-finto"}
VISTE = []  # le intestazioni che il client manda al provider
CORPI = []  # i corpi delle richieste: istruzioni, messaggi, strumenti


def risposta_finta(richiesta):
    """Simula Claude. Con leggi_programma lo chiama finche' non ha un risultato buono; con chiedi_verifica
    (variante A) poi chiede la verifica passando il risultato; con cerca e valida (variante B) chiama
    cerca, poi valida, poi risponde. Senza strumenti risponde come valida."""
    VISTE.append(dict(richiesta.headers))
    corpo = json.loads(richiesta.content)
    CORPI.append(corpo)
    messaggi = corpo["messages"]
    ultimo = messaggi[-1]["content"]
    strumenti = {x["name"] for x in corpo.get("tools", [])}
    dati = next((x for x in corpo.get("tools", []) if x["name"] not in ("cerca", "valida")), None)  # lo strumento del dominio
    pensiero = {"type": "thinking", "thinking": "Devo leggere il programma.", "signature": "x"}
    uso = {"input_tokens": 1000, "output_tokens": 50, "cache_read_input_tokens": 0}
    base = {"id": "msg_finto", "type": "message", "role": "assistant", "model": s.MODEL, "usage": uso}
    precedente = next((b["name"] for b in messaggi[-2]["content"] if b.get("type") == "tool_use"), None) \
        if len(messaggi) > 1 else None
    risultato = ultimo[-1]["content"] if isinstance(ultimo, list) else None
    buono = isinstance(ultimo, list) and not ultimo[-1].get("is_error")

    def chiama(nome, argomenti):
        contenuto = [pensiero, {"type": "tool_use", "id": f"t{len(messaggi)}", "name": nome, "input": argomenti}]
        return httpx.Response(200, headers=INTESTAZIONI, json={**base, "stop_reason": "tool_use", "content": contenuto})

    def rispondi(testo):
        return httpx.Response(200, headers=INTESTAZIONI,
                              json={**base, "stop_reason": "end_turn", "content": [pensiero, {"type": "text", "text": testo}]})

    domanda = s.DOMINIO["domanda"]  # con l'email: coordina la passa a valida, come nelle run vere
    if "cerca" in strumenti:  # coordina
        if precedente is None:
            return chiama("cerca", {"richiesta": "Kubernetes da zero"})
        if precedente == "cerca":
            return chiama("valida", {"domanda": domanda, "risposta": risultato})
        return rispondi(risultato)
    if dati and not buono:
        return chiama(dati["name"], {dati["input_schema"]["required"][0]: next(iter(s.DOMINIO["oggi"]))})
    if "chiedi_verifica" in strumenti and precedente == "leggi_programma":
        bozza = f"Oggi alle {json.loads(risultato)['ora']}, sala B."
        return chiama("chiedi_verifica", {"domanda": domanda, "risposta": bozza, "contesto": risultato})
    if precedente == "chiedi_verifica":
        return rispondi(risultato.replace("\n\nVerificato.", ""))
    if buono:
        return rispondi(str(json.loads(risultato).get("ora", risultato)))
    return rispondi("Oggi alle 15:00, sala B.\n\nVerificato.")


def corri(strato, guasto=True):
    s.STRATO = strato
    http = httpx.Client(transport=httpx.MockTransport(risposta_finta))
    client = s.cliente(api_key="finta", http_client=http)
    with contextlib.redirect_stdout(io.StringIO()) as fuori:
        reg = s.esegui(guasto, CARTELLA, client=client)
        s.mostra(reg)
    return reg, re.sub(r"\033\[\d+m", "", fuori.getvalue())  # senza colori


@contextlib.contextmanager
def dominio(nome):
    s.DOMINIO = s.DOMINI[nome]
    try:
        yield
    finally:
        s.DOMINIO = s.DOMINI["orario"]


def nomi(reg):
    return [x["nome"] for x in reg["span"]]


def padre_di(reg, nome):
    per_id = {x["id"]: x for x in reg["span"]}
    return per_id[next(x for x in reg["span"] if x["nome"] == nome)["padre"]]["nome"]


def attributi(reg, nome):
    return next(x for x in reg["span"] if x["nome"] == nome)["attributi"]


# coordina chiama cerca; cerca: timeout, ritenta, risponde; coordina chiama valida; valida risponde; coordina risponde
CHIAMATE = 7


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
    assert "execute_tool leggi_programma" not in nomi(reg)  # lo strumento dei dati resta dello strato 3
    for arco in ("execute_tool cerca", "execute_tool valida"):  # gli archi fra agenti sono dello strato 2
        a = attributi(reg, arco)
        assert "gen_ai.tool.call.arguments" not in a and a["gen_ai.transfer.target.name"] == arco.split()[-1]


def test_strato_3_lo_strumento_ma_non_la_copia():
    reg, fuori = corri(3)
    strumenti = [x for x in reg["span"] if x["nome"] == "execute_tool leggi_programma"]
    assert [x["errore"] for x in strumenti] == [True, False]
    assert "15:00" in strumenti[1]["attributi"]["gen_ai.tool.call.result"]
    assert "gen_ai.tool.call.arguments" in attributi(reg, "execute_tool valida")  # gli argomenti fra agenti sono un prompt
    assert "cache.read" not in nomi(reg)


def test_strato_4_la_copia_ha_un_eta():
    reg, fuori = corri(4)
    cache = [x for x in reg["span"] if x["nome"] == "cache.read"]
    assert cache[0]["attributi"]["cache.age_hours"] == 26 and "età 26 ore" in fuori


def test_strato_5_il_contenuto_e_l_email():
    reg, fuori = corri(5)
    assert any("gen_ai.input.messages" in x["attributi"] for x in reg["span"])
    assert "pensiero di coordina: Devo leggere il programma." in fuori
    assert s.con_email(reg["span"]) > 0 and "email dell'utente" in fuori


def test_sana_niente_copia():
    reg, _ = corri(4, guasto=False)
    strumenti = [x for x in reg["span"] if x["nome"] == "execute_tool leggi_programma"]
    assert len(strumenti) == 1 and not strumenti[0]["errore"] and "cache.read" not in nomi(reg)


def test_orchestratore_grafo():
    reg, _ = corri(5)
    assert padre_di(reg, "invoke_agent cerca") == "execute_tool cerca"
    assert padre_di(reg, "invoke_agent valida") == "execute_tool valida"
    assert padre_di(reg, "execute_tool leggi_programma") == "invoke_agent cerca"
    passaggio = attributi(reg, "execute_tool valida")
    assert passaggio["gen_ai.agent.name"] == "coordina" and passaggio["gen_ai.transfer.mode"] == "return_to_caller"
    m = s.misura(reg)
    assert m["grafo"] == ("codice>coordina coordina>cerca cerca>leggi_programma! cerca>leggi_programma "
                          "coordina>valida")
    assert m["profondita"] == 6 and m["contesto"] == 0 and m["verificato"]


def test_dominio_orario_invariato():
    reg, _ = corri(5)
    m = s.misura(reg)
    assert m["grafo"] == ("codice>coordina coordina>cerca cerca>leggi_programma! cerca>leggi_programma "
                          "coordina>valida")
    assert m["esito"] == "sbagliata"
    assert s.DOMINI["orario"]["sbagliata"]("Oggi alle 15:00, sala B.")
    assert s.DOMINI["orario"]["giusta"]("Oggi alle 14:00, sala B.")


def test_freeze_argomento_libero():
    with dominio("freeze"):
        stato = {"aperto_fino": 0.0, "guasto": False, "fattura": []}
        assert s.leggi_dato("servizio pagamenti", stato)["freeze"] is True


def test_freeze_esito():
    d = s.DOMINI["freeze"]
    assert d["sbagliata"]("Sì, puoi fare il deploy di pagamenti adesso.")
    assert d["sbagliata"]("Puoi procedere: pagamenti non è in freeze.")
    assert d["giusta"]("No, pagamenti è in freeze fino a lunedì 08:00.")
    assert d["giusta"]("Non puoi fare il deploy: c'è un freeze per il Black Friday.")
    assert not d["sbagliata"]("Non puoi fare il deploy: c'è un freeze per il Black Friday.")
    with dominio("freeze"):
        reg, _ = corri(5)
    m = s.misura({**reg, "risposta": "Non riesco a confermarlo, il calendario non ha risposto."})
    assert m["esito"] == "non conferma"


def test_freeze_grafo():
    with dominio("freeze"):
        reg, _ = corri(5)
    assert reg["dominio"] == "freeze" and "cerca>leggi_calendario!" in s.misura(reg)["grafo"]
    assert nomi(reg)[-1] == "invoke_workflow assistente-piattaforma"
    cache = [x for x in reg["span"] if x["nome"] == "cache.read"]
    assert cache[0]["attributi"]["cache.age_hours"] == 26
    assert s.DOMINIO is s.DOMINI["orario"]


def istruzioni_di(agente_istruzioni_finiscono):
    return any(isinstance(c.get("system"), str) and c["system"].endswith(agente_istruzioni_finiscono)
               for c in CORPI[-CHIAMATE:])


def test_correzione_l_eta_arriva_a_cerca():
    try:
        s.CORREZIONE = 1
        reg, _ = corri(5)
        strumenti = [x for x in reg["span"] if x["nome"] == "execute_tool leggi_programma"]
        assert '"aggiornato": "26 ore fa"' in strumenti[1]["attributi"]["gen_ai.tool.call.result"]
        m = s.misura(reg)
        assert "avvisa" in m and "valida_sa_eta" in m and reg["correzione"] == 1
        assert istruzioni_di("dillo nella risposta.") and not istruzioni_di("va confermato.")
        s.CORREZIONE = 2
        reg, _ = corri(5)
        assert istruzioni_di("va confermato.") and reg["correzione"] == 2
    finally:
        s.CORREZIONE = 0


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


if __name__ == "__main__":
    for nome, prova in list(globals().items()):
        if nome.startswith("test_"):
            prova()
            print("ok", nome)
