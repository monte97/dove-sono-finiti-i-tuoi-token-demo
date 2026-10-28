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


def risposta_finta(richiesta):
    """Simula Claude. Con leggi_programma lo chiama finche' non ha un risultato buono; con chiedi_verifica
    (variante A) poi chiede la verifica passando il risultato; con cerca e valida (variante B) chiama
    cerca, poi valida, poi risponde. Senza strumenti risponde come valida."""
    VISTE.append(dict(richiesta.headers))
    corpo = json.loads(richiesta.content)
    messaggi = corpo["messages"]
    ultimo = messaggi[-1]["content"]
    strumenti = {x["name"] for x in corpo.get("tools", [])}
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

    domanda = "A che ora è il workshop Kubernetes da zero?"
    if "cerca" in strumenti:  # coordina
        if precedente is None:
            return chiama("cerca", {"richiesta": "Kubernetes da zero"})
        if precedente == "cerca":
            return chiama("valida", {"domanda": domanda, "risposta": risultato})
        return rispondi(risultato)
    if "leggi_programma" in strumenti and not buono:
        return chiama("leggi_programma", {"sessione": "Kubernetes da zero"})
    if "chiedi_verifica" in strumenti and precedente == "leggi_programma":
        bozza = f"Oggi alle {json.loads(risultato)['ora']}, sala B."
        return chiama("chiedi_verifica", {"domanda": domanda, "risposta": bozza, "contesto": risultato})
    if precedente == "chiedi_verifica":
        return rispondi(risultato.replace("\n\nVerificato.", ""))
    if buono:
        return rispondi(json.loads(risultato)["ora"])
    return rispondi("Oggi alle 15:00, sala B.\n\nVerificato.")


def corri(strato, guasto=True, runner=False, variante="fissa"):
    s.STRATO = strato
    http = httpx.Client(transport=httpx.MockTransport(risposta_finta))
    client = s.cliente(api_key="finta", http_client=http)
    with contextlib.redirect_stdout(io.StringIO()) as fuori:
        reg = s.esegui(guasto, runner, CARTELLA, client=client, variante=variante)
        s.mostra(reg)
    return reg, re.sub(r"\033\[\d+m", "", fuori.getvalue())  # senza colori


def nomi(reg):
    return [x["nome"] for x in reg["span"]]


def test_strato_0_solo_log_e_fattura():
    reg, fuori = corri(0)
    assert reg["span"] == [] and reg["fattura"]["chiamate"] == 4  # cerca: timeout, ritenta, risponde; valida: 1
    assert "200 in" in fuori and "fattura:" in fuori and "trace" not in fuori
    assert not any("traceparent" in h for h in VISTE[-4:])


def test_strato_1_una_trace_per_chiamata_e_niente_contenuto():
    reg, fuori = corri(1)
    assert nomi(reg) == ["anthropic.messages.create"] * 4
    assert s.esito(reg)["tracce"] == 4
    a = reg["span"][0]["attributi"]
    assert a["gen_ai.operation.name"] == "chat" and a["anthropic.message.stop_reason"] == "tool_use"
    assert "gen_ai.response.finish_reasons" not in a and "gen_ai.input.messages" not in a
    assert all(a[k] == "oscurato" for k in s.ID_ACCOUNT)
    assert "org-finta" not in fuori and "chat ?" in fuori  # di chi sia la chiamata non si sa
    assert all("traceparent" in h for h in VISTE[-4:])  # l'SDK manda il contesto della trace al provider


def test_strato_2_una_trace_sola():
    reg, _ = corri(2)
    assert s.esito(reg)["tracce"] == 1
    assert nomi(reg)[-1] == "invoke_workflow assistente-evento"
    assert "execute_tool leggi_programma" not in nomi(reg)


def test_strato_3_lo_strumento_ma_non_la_copia():
    reg, fuori = corri(3)
    strumenti = [x for x in reg["span"] if x["nome"] == "execute_tool leggi_programma"]
    assert [x["errore"] for x in strumenti] == [True, False]
    assert "15:00" in strumenti[1]["attributi"]["gen_ai.tool.call.result"]
    assert "cache.read" not in nomi(reg)


def test_strato_4_la_copia_ha_un_eta():
    reg, fuori = corri(4)
    cache = [x for x in reg["span"] if x["nome"] == "cache.read"]
    assert cache[0]["attributi"]["cache.age_hours"] == 26 and "età 26 ore" in fuori
    assert s.con_email(reg["span"]) == 0


def test_strato_5_il_contenuto_e_l_email():
    reg, fuori = corri(5)
    assert any("gen_ai.input.messages" in x["attributi"] for x in reg["span"])
    assert "pensiero di cerca: Devo leggere il programma." in fuori
    assert s.con_email(reg["span"]) > 0 and "email dell'utente" in fuori


def test_strato_1_con_il_tool_runner():
    reg, _ = corri(1, runner=True)
    n = nomi(reg)
    assert n.count("anthropic.messages.tool_runner") == 2 and n.count("anthropic.custom_tool_use leggi_programma") == 2
    assert s.esito(reg)["tracce"] == 2  # una per agente: il runner fa da radice, ma il workflow manca
    strumento = next(x for x in reg["span"] if x["nome"].startswith("anthropic.custom_tool_use"))
    assert strumento["errore"] and strumento["attributi"]["error.type"] == "tool_error"
    assert "gen_ai.tool.call.arguments" not in strumento["attributi"]  # senza content_mode niente argomenti


def test_sana_niente_copia():
    reg, _ = corri(4, guasto=False)
    strumenti = [x for x in reg["span"] if x["nome"] == "execute_tool leggi_programma"]
    assert len(strumenti) == 1 and not strumenti[0]["errore"] and "cache.read" not in nomi(reg)


def padre_di(reg, nome):
    per_id = {x["id"]: x for x in reg["span"]}
    return per_id[next(x for x in reg["span"] if x["nome"] == nome)["padre"]]["nome"]


def test_variante_a_agente_come_strumento():
    reg, fuori = corri(5, variante="A")
    assert padre_di(reg, "invoke_agent valida") == "execute_tool chiedi_verifica"
    assert padre_di(reg, "execute_tool chiedi_verifica") == "invoke_agent cerca"
    passaggio = next(x for x in reg["span"] if x["nome"] == "execute_tool chiedi_verifica")["attributi"]
    assert passaggio["gen_ai.agent.name"] == "cerca" and passaggio["gen_ai.transfer.target.name"] == "valida"
    assert passaggio["gen_ai.transfer.mode"] == "return_to_caller"
    m = s.misura(reg)
    assert m["grafo"] == ("codice>cerca cerca>leggi_programma! cerca>leggi_programma cerca>chiedi_verifica")
    assert m["riprove"] == 1 and m["valida"] == 1 and m["contesto"] == 1 and m["ora"] == "15:00"
    assert m["valida_vede_dato"] == 1 and m["valida_vede_eta"] == 0
    assert not m["verificato"] and "variante A" in fuori  # l'approvazione resta nella trace


def test_variante_b_orchestratore():
    reg, _ = corri(5, variante="B")
    assert padre_di(reg, "invoke_agent cerca") == "execute_tool cerca"
    assert padre_di(reg, "invoke_agent valida") == "execute_tool valida"
    assert padre_di(reg, "execute_tool leggi_programma") == "invoke_agent cerca"
    m = s.misura(reg)
    assert m["grafo"] == ("codice>coordina coordina>cerca cerca>leggi_programma! cerca>leggi_programma "
                          "coordina>valida")
    assert m["profondita"] == 6 and m["contesto"] == 0 and m["verificato"]


def test_strato_2_le_varianti_mostrano_il_grafo_senza_argomenti():
    for variante, passaggio in (("A", "execute_tool chiedi_verifica"), ("B", "execute_tool valida")):
        reg, _ = corri(2, variante=variante)
        assert s.esito(reg)["tracce"] == 1 and passaggio in nomi(reg)
        assert "execute_tool leggi_programma" not in nomi(reg)  # lo strumento dei dati resta dello strato 3
        a = next(x for x in reg["span"] if x["nome"] == passaggio)["attributi"]
        assert "gen_ai.tool.call.arguments" not in a and a["gen_ai.transfer.target.name"] == "valida"


def test_strato_4_varianti_la_copia_ha_un_eta():
    for variante in ("A", "B"):
        reg, fuori = corri(4, variante=variante)
        assert "cache.read" in nomi(reg) and "età 26 ore" in fuori


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
