"""Il server finto e gli aiutanti condivisi dai test: modello, run, alberi finti, spazio temporaneo."""
import contextlib
import io
import json
import re
import tempfile
import time
from pathlib import Path

import httpx2 as httpx

from osservare_a_strati import esecuzione as _esecuzione
from osservare_a_strati import modello as _modello
from osservare_a_strati import stampa as _stampa
from osservare_a_strati.analisi import schema as _schema
from osservare_a_strati.analisi import span as _span
from osservare_a_strati.evento import avvisi as _avvisi
from osservare_a_strati.evento import dati as _dati
from osservare_a_strati.impostazioni import con
from osservare_a_strati.osservabilita import client as _client

QUI = Path(__file__).resolve().parent.parent

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

# coordina: 3 giri (i tre agenti insieme, valida, risposta); programma, sale e avvisi 2 ciascuno; valida 1
CHIAMATE = 10
AGENTI = ("programma", "sale", "avvisi", "valida")

# Gli hash del testo che il modello legge, per modalita' di correzione, fissati sul banco del 5/11 (tag banco-2026-11-05):
# le istruzioni non sono cambiate dopo il banco, e tempo.py ricava da qui la versione delle registrazioni che non l'hanno.
# Se questo test fallisce hai cambiato un'istruzione o una descrizione: le registrazioni del banco non sono piu' di questa
# versione, e va aggiornata la tabella in docs/banco-rami-paralleli.md.
HASH_BANCO = {0: "8909d44b", 1: "1d2a1b7e", 2: "ead55ac1", 3: "d8d06c33"}

TOKEN = {"programma": (1000, 50), "sale": (1000, 50), "avvisi": (8000, 100)}
STRUMENTO = {"programma": ("leggi_programma", {}), "sale": ("leggi_sale", {}),
             "avvisi": ("leggi_avvisi", {"avvisi.pagine": 40, "gen_ai.tool.call.result": "- " + _avvisi.AVVISO_CHIAVE})}
RISPOSTA = {"programma": "Oggi alle 15:00, sala B.", "sale": "Sala B, primo piano.", "avvisi": "Nessun avviso sul workshop."}

FORMA = "codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma),sale(leggi_sale)} coordina>valida"
SENZA_STRUMENTI = "codice>coordina coordina>{avvisi,programma,sale} coordina>valida"
TOTALE_IN, TOTALE_OUT = 1000 + 1000 + 1000 + 8000 + 2000, 50 + 50 + 50 + 100 + 100
TOTALE = 1000 + 50 + 1000 + 50 + 8000 + 100 + 1000 + 50 + 2000 + 100

FORMA_ANNIDATA = ("codice>coordina "
                  "coordina>{avvisi(leggi_avvisi),programma({leggi_programma,sale(leggi_sale)}),sale(leggi_sale)} "
                  "coordina>valida({avvisi(leggi_avvisi),programma({leggi_programma,sale(leggi_sale)})})")
FORMA_DIALOGO = ("codice>coordina coordina>{avvisi({leggi_avvisi,programma(leggi_programma)}),programma(leggi_programma),"
                 "sale(leggi_sale)} coordina>valida")


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
    base = {"id": "msg_finto", "type": "message", "role": "assistant", "model": _modello.MODEL, "usage": uso}
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
            return chiama("valida", {"domanda": _dati.DOMANDA, "risposta": "Oggi alle 15:00, sala B.",
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
            return rispondi("- " + _avvisi.AVVISO_CHIAVE)  # sa che e' la sala B: non lascia l'avviso fra i 400
        return rispondi({"leggi_programma": "Oggi alle 15:00, sala B" + (", piano 1." if FINTO["annidate"] else "."),
                         "leggi_sale": "Sala B, primo piano, 80 posti.",
                         "leggi_avvisi": "Nessun avviso sul workshop."}[dati["name"]])
    return rispondi("Oggi alle 15:00, sala B.\n\nVerificato.")


def corri(strato, guasto=True):
    with con(strato=strato):
        http = httpx.Client(transport=httpx.MockTransport(risposta_finta))
        client = _client.cliente(api_key="finta", http_client=http)
        with contextlib.redirect_stdout(io.StringIO()) as fuori:
            reg = _esecuzione.esegui(guasto, CARTELLA, client=client)
            _stampa.mostra(reg)
    return reg, re.sub(r"\033\[\d+m", "", fuori.getvalue())  # senza colori


def nomi(reg):
    return [x["nome"] for x in reg["span"]]


def padre_di(reg, nome):
    per_id = {x["id"]: x for x in reg["span"]}
    return per_id[next(x for x in reg["span"] if x["nome"] == nome)["padre"]]["nome"]


def attributi(reg, nome):
    return next(x for x in reg["span"] if x["nome"] == nome)["attributi"]


def span_di(reg, nome):
    return next(x for x in reg["span"] if x["nome"] == nome)


def tipo_di(voce: str) -> str:
    return voce.split(":")[0]


def istruzioni_di(agente_istruzioni_finiscono):
    return any(isinstance(c.get("system"), str) and c["system"].endswith(agente_istruzioni_finiscono)
               for c in CORPI[-CHIAMATE:])


def corri_annidato(strato=5, correzione=0, guasto=True, **scelte):
    """Una run con il modello finto che si fa chiamare fra agenti (vedi FINTO) e la correzione scelta."""
    with con(correzione=correzione), finto(**scelte):
        return corri(strato, guasto)


def percorso(reg, x):
    """I nomi degli span da x alla radice, per verificare la parentela a piu' livelli."""
    per_id, fuori = {y["id"]: y for y in reg["span"]}, []
    while x:
        fuori.append(x["nome"])
        x = per_id.get(x["padre"])
    return fuori


def arcs(reg, verso, da=None):
    return _span.archi(reg["span"], (verso,), da=da)


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
        _schema.mostra_schema(cartella, **opzioni)
    return fuori.getvalue()


def sp(nome, id, padre=None, errore=False, inizio=0.0, durata=1.0, attributi=None):
    return {"nome": nome, "id": id, "padre": padre, "trace": "t", "inizio": inizio, "fine": inizio + durata,
            "errore": errore, "attributi": attributi or {}}


def arco(id, padre, chi, verso, inizio, durata=1.0, **altri):
    return sp(f"execute_tool {verso}", id, padre, inizio=inizio, durata=durata, attributi={
        "gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": verso, "gen_ai.agent.name": chi,
        "gen_ai.transfer.target.name": verso, **altri})


def agente(id, padre, nome, inizio, durata=1.0):
    return sp(f"invoke_agent {nome}", id, padre, inizio=inizio, durata=durata,
              attributi={"gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": nome})


def chat(id, padre, inizio, entrata, cache, uscita):
    return sp("anthropic.messages.create", id, padre, inizio=inizio, attributi={
        "gen_ai.usage.input_tokens": entrata, "gen_ai.usage.cache_read.input_tokens": cache,
        "gen_ai.usage.output_tokens": uscita})


def strumento(id, padre, nome, inizio, errore=False, **altri):
    return sp(f"execute_tool {nome}", id, padre, errore=errore, inizio=inizio, attributi={
        "gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": nome, **altri})


def ramo(verso, inizio, durata, **risultato):
    """Un arco di coordina verso un agente, con l'agente, la sua chiamata al modello e il suo strumento."""
    nome, attr_tool = STRUMENTO[verso]
    ing, usc = TOKEN[verso]
    return [arco(f"a-{verso}", "co", "coordina", verso, inizio, durata, **{"gen_ai.tool.call.result": RISPOSTA[verso], **risultato}),
            agente(f"g-{verso}", f"a-{verso}", verso, inizio, durata),
            chat(f"m-{verso}", f"g-{verso}", inizio, ing, 0, usc),
            strumento(f"l-{verso}", f"g-{verso}", nome, inizio, **attr_tool)]


def run(partenze=(("programma", 3.0), ("sale", 3.01), ("avvisi", 3.02)), strato=5, **risultato_avvisi):
    """coordina chiama i tre rami (insieme, se le partenze si sovrappongono), poi valida, che approva."""
    rami = [x for verso, inizio in partenze for x in ramo(verso, inizio, 3.0, **(risultato_avvisi if verso == "avvisi" else {}))]
    va = max(x["fine"] for x in rami if x["nome"].startswith("execute_tool ")) + 0.5  # valida dopo i rami
    return {"strato": strato, "modo": "guasto", "risposta": "Oggi alle 15:00, sala B.", "secondi": 12.0,
            "fattura": {"chiamate": 6, "in": TOTALE_IN, "cache": 1000, "out": TOTALE_OUT}, "span": [
        sp("invoke_workflow assistente", "w", durata=12, attributi={"gen_ai.operation.name": "invoke_workflow"}),
        agente("co", "w", "coordina", 1, 11),
        chat("m1", "co", 2, 1000, 0, 50),
        *rami,
        arco("a-valida", "co", "coordina", "valida", va, **{
            "gen_ai.tool.call.arguments": '{"domanda": "ciao giulia.rossi@example.com"}',
            "gen_ai.tool.call.result": "Il workshop è alle 15:00. Verificato."}),
        agente("g-valida", "a-valida", "valida", va),
        chat("m-valida", "g-valida", va + 1, 2000, 1000, 100),
    ]}
