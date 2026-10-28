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
    """Simula Claude: con lo strumento lo chiama finche' non ha un risultato buono, poi risponde."""
    VISTE.append(dict(richiesta.headers))
    corpo = json.loads(richiesta.content)
    ultimo = corpo["messages"][-1]["content"]
    pensiero = {"type": "thinking", "thinking": "Devo leggere il programma.", "signature": "x"}
    uso = {"input_tokens": 1000, "output_tokens": 50, "cache_read_input_tokens": 0}
    base = {"id": "msg_finto", "type": "message", "role": "assistant", "model": s.MODEL, "usage": uso}
    buono = isinstance(ultimo, list) and not ultimo[-1].get("is_error")
    if corpo.get("tools") and not buono:
        n = len(corpo["messages"])
        contenuto = [pensiero, {"type": "tool_use", "id": f"t{n}", "name": "leggi_programma",
                                "input": {"sessione": "Kubernetes da zero"}}]
        return httpx.Response(200, headers=INTESTAZIONI, json={**base, "stop_reason": "tool_use", "content": contenuto})
    testo = json.loads(ultimo[-1]["content"])["ora"] if buono else "Oggi alle 15:00, sala B.\n\nVerificato."
    return httpx.Response(200, headers=INTESTAZIONI,
                          json={**base, "stop_reason": "end_turn", "content": [pensiero, {"type": "text", "text": testo}]})


def corri(strato, guasto=True, runner=False):
    s.STRATO = strato
    http = httpx.Client(transport=httpx.MockTransport(risposta_finta))
    client = s.cliente(api_key="finta", http_client=http)
    with contextlib.redirect_stdout(io.StringIO()) as fuori:
        reg = s.esegui(guasto, runner, CARTELLA, client=client)
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
