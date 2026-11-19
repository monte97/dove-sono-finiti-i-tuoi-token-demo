"""La stessa risposta sbagliata, osservata uno strato alla volta.

Cinque agenti. `coordina` e' l'orchestratore: ha come strumenti gli agenti `programma`, `sale`, `avvisi` e
`valida` e decide lui chi chiamare, in che ordine, cosa passare e quando rispondere. `programma`, `sale` e
`avvisi` leggono ciascuno una fonte con uno strumento (`leggi_programma`, `leggi_sale`, `leggi_avvisi`),
`valida` controlla una risposta prima che arrivi all'utente. Nessun componente e' rotto: il programma di
ieri sera dice 15:00 sala B, e solo un avviso di stamattina sulla sala B dice che la sessione e' un'ora prima.

`--guasto` (modo "guasto" nelle registrazioni) e' la giornata piena: 40 pagine di avvisi, quello sulla sala B a
meta'. Senza `--guasto` (modo "sana") e' la giornata tranquilla: 3 pagine, niente sulla sala B.

Strati (ognuno contiene i precedenti):
  0  oggi: una riga di log per ogni chiamata al modello (agente e token) e la fattura, niente OpenTelemetry
  1  le metriche dei token e l'SDK: contatori per chiamata, un istogramma per agente in ogni richiesta, e la
     strumentazione nativa di anthropic
  2  gli agenti: span invoke_workflow, invoke_agent e gli archi fra agenti, scritti a mano
  3  lo strumento: span execute_tool con argomenti e risultato
  4  i dati letti: da dove viene il dato e quanto
  5  il contenuto: content_mode "content" (messaggi e ragionamento riassunto)

  python strati.py --strato 3 --guasto             una run
  python strati.py --strato 3 --guasto --banco 5   cinque run, una riga ciascuna
  python strati.py --strato 5 --correzione-dialogo avvisi puo' chiedere a programma (ricalcola la sala da solo)
  python strati.py --replay registrazioni/strato-3/<file>.json
  python strati.py --riepilogo                     una riga per strato e modo
  python strati.py --misure 5                      come ha deciso il grafo, cosa ha letto e riportato avvisi, token per agente
  python strati.py --righe                         righe di codice di ogni strato

Le righe che esistono solo per osservare finiscono con il marcatore dello strato (s0 ... s5 dopo il cancelletto).
La pipeline fissa, la variante A (agente come strumento) e il tool runner sono nel tag git spike-a-b.
"""

import argparse
import datetime as dt
import json
import re
import statistics
import textwrap
from pathlib import Path

from dotenv import load_dotenv
from osservare_a_strati import esecuzione as esecuzione_mod, registrazioni as registrazioni_mod
from osservare_a_strati.agenti import ciclo as ciclo_mod, prompt as prompt_mod, strumenti as strumenti_mod
from osservare_a_strati.agenti.ciclo import (CATENA, PROFONDITA_MAX, agente, chiama_agente, ciclo, controlla_catena,
                                             esegui_chiamate, esegui_strumento, richiesta_di_verifica)
from osservare_a_strati.agenti.prompt import (CORREZIONE_AVVISI, CORREZIONE_COORDINA, CORREZIONE_DIALOGO,
                                              DESCRIZIONI, ISTRUZIONI, agenti_strumento, istruzioni_coordina, schemi,
                                              versione, versione_prompt)
from osservare_a_strati.agenti.strumenti import leggi_dato
from osservare_a_strati.esecuzione import concludi_banco, esegui, esegui_banco
from osservare_a_strati.evento.avvisi import (AVVISO_ALLARME, AVVISO_CHIAVE, AVVISI_PER_PAGINA, PAGINA_AVVISO,
                                              PAGINE_PIENA, PAGINE_TRANQUILLA, SEME_AVVISI, _MODELLI, _ORE, _voce, avvisi)
from osservare_a_strati.evento.dati import (AVVISI_AGGIORNATI, DOMANDA, PROGRAMMA, PUBBLICATO, SALE, SESSIONE_SALA,
                                            _trova, sala_normale)
from osservare_a_strati.modello import LISTINO, MAX_GIRI, MODEL, PENSIERO, costo
from osservare_a_strati.valutazione import (APPROVA, AVVISI_CAUSA, AVVISI_NEGA, AVVISI_SALA_B, CHIEDE_VARIAZIONI,
                                            CLASSI_DOMANDA, ESITI, _CONFINE_CLAUSOLA, _QUATTORDICI_POSSIBILE,
                                            _QUINDICI_SUPERATO, _avverte, _clausole, approva, classe_domanda,
                                            riporta_avviso, valuta)
from osservare_a_strati.impostazioni import NOMI_CORREZIONE, TITOLI, Impostazioni, attuali, con, imposta
from osservare_a_strati.osservabilita import client as osservabilita_client
from osservare_a_strati.osservabilita import log as osservabilita_log
from osservare_a_strati.osservabilita import metriche, tracce
from osservare_a_strati.osservabilita.client import cliente
from osservare_a_strati.osservabilita.log import (CAMPI_RIGA, LOG, Righe, fai_log, logfmt, processore_otlp_log,
                                                  url_log)
from osservare_a_strati.osservabilita.metriche import (CONFINI_TOKEN, fai_metriche, leggi_metriche, memoria_metriche,
                                                       metriche_in_dict, url_metriche)
from osservare_a_strati.osservabilita.tracce import (EMAIL, VERSIONE, MascheraEmail, fai_provider, processore_otlp,
                                                     senza_email)
from osservare_a_strati.registrazioni import (ID_ACCOUNT, RADICE, cartella_della_run, in_dict, leggi, log_in_dict)  # noqa: F401

QUI = Path(__file__).parent
load_dotenv(QUI / ".env")

_MODULI_DINAMICI = {
    "memoria": (tracce, "memoria"),
    "RISORSA": (tracce, "RISORSA"),
    "memoria_log": (osservabilita_log, "memoria_log"),
    "_handler": (osservabilita_log, "_handler"),
    "_provider_log": (osservabilita_log, "_provider_log"),
    "TOKEN_IN": (metriche, "TOKEN_IN"),
    "TOKEN_OUT": (metriche, "TOKEN_OUT"),
    "TOKEN_AGENTE": (metriche, "TOKEN_AGENTE"),
    "provider": (metriche, "provider"),
    "_provider_metriche": (metriche, "provider"),
}


def __getattr__(nome):
    """I nomi spostati restano leggibili da qui, sempre dal modulo che li possiede."""
    if nome in _MODULI_DINAMICI:
        modulo, campo = _MODULI_DINAMICI[nome]
        return getattr(modulo, campo)
    raise AttributeError(f"module {__name__!r} has no attribute {nome!r}")


# --- stampa: la stessa per le run dal vivo e per quelle registrate, e mostra solo cio' che c'e' ---

COLORI = {"rosso": 31, "verde": 32, "giallo": 33, "ciano": 36, "grigio": 90, "inverso": 7}


def c(colore: str, testo: str) -> str:
    return f"\033[{COLORI[colore]}m{testo}\033[0m"


def attr(s, chiave, altrimenti=None):
    return s["attributi"].get(chiave, altrimenti)


def token(s):
    if "gen_ai.usage.input_tokens" not in s["attributi"]:
        return None
    return {"in": attr(s, "gen_ai.usage.input_tokens"), "cache": attr(s, "gen_ai.usage.cache_read.input_tokens") or 0,
            "out": attr(s, "gen_ai.usage.output_tokens") or 0, "pensiero": attr(s, "gen_ai.usage.reasoning.output_tokens") or 0}


def in_ordine(span):
    figli, ids, fuori = {}, {s["id"] for s in span}, []
    for s in span:
        figli.setdefault(s["padre"], []).append(s)

    def giu(s, livello):
        fuori.append((s, livello))
        for f in sorted(figli.get(s["id"], []), key=lambda x: x["inizio"]):
            giu(f, livello + 1)

    for radice in sorted((s for s in span if s["padre"] not in ids), key=lambda x: x["inizio"]):
        giu(radice, 0)
    return fuori


def agente_di(s, per_id):
    while s:
        if attr(s, "gen_ai.operation.name") == "invoke_agent":
            return attr(s, "gen_ai.agent.name", "?")
        s = per_id.get(s["padre"])
    return "?"


def colore(s) -> str:
    if s["errore"]:
        return "rosso"
    if attr(s, "gen_ai.operation.name") == "execute_tool":
        return "giallo"
    return "verde" if token(s) else "ciano"


def ms(s) -> str:
    return f"{(s['fine'] - s['inizio']) * 1000:,.0f} ms".replace(",", ".")


def per_trace(span) -> dict:
    gruppi = {}
    for s in span:
        gruppi.setdefault(s["trace"], []).append(s)
    return dict(sorted(gruppi.items(), key=lambda kv: min(x["inizio"] for x in kv[1])))


def albero(span):
    for s, livello in in_ordine(span):
        t = token(s)
        extra = f" · in {t['in']} · out {t['out']}" if t else ""
        print(c(colore(s), "  " * livello + s["nome"]) + c("grigio", f"  {ms(s)}{extra}"))


def cascata(span, larghezza: int = 40):
    t0, t1 = min(s["inizio"] for s in span), max(s["fine"] for s in span)
    scala = larghezza / max(t1 - t0, 1e-9)
    for s, livello in in_ordine(span):
        a = min(int((s["inizio"] - t0) * scala), larghezza - 1)
        b = min(max(a + 1, round((s["fine"] - t0) * scala)), larghezza)
        nome = ("  " * livello + s["nome"])[:34].ljust(34)
        print(f"{nome} {' ' * a}{c(colore(s), '█' * (b - a))}{' ' * (larghezza - b)} {ms(s):>9}")


def breve(testo, massimo: int = 200) -> str:
    """Per la stampa: i risultati lunghi (le 400 righe di avvisi) si accorciano; lo span e la registrazione restano interi."""
    testo = str(testo)
    if len(testo) <= massimo:
        return testo
    return testo[:massimo].rstrip().replace("\n", " ") + f"… {testo.count(chr(10)) + 1} righe"


def verbale(span):
    per_id, totale = {s["id"]: s for s in span}, 0.0
    print(c("grigio", f"{'passo':<22} {'esito':<11} {'in / out (pensiero)':>20} {'costo $':>10}"))
    for s, _ in in_ordine(span):
        t = token(s)
        if t:
            usd = costo(t["in"], t["cache"], t["out"])
            totale += usd
            numeri = f"{t['in']} / {t['out']}" + (f" ({t['pensiero']})" if t["pensiero"] else "")
            print(f"{'chat ' + agente_di(s, per_id):<22} {attr(s, 'anthropic.message.stop_reason', ''):<11} "
                  f"{numeri:>20} {usd:>10.6f}")
        elif attr(s, "gen_ai.operation.name") == "execute_tool":
            print(c(colore(s), f"{attr(s, 'gen_ai.tool.name', '?'):<22} {'errore' if s['errore'] else 'ok':<11}"))
            argomenti = attr(s, "gen_ai.tool.call.arguments")
            risultato = attr(s, "gen_ai.tool.call.result", attr(s, "anthropic.tool_result.content"))
            if argomenti or risultato:
                print(c("grigio", f"  {argomenti} -> {breve(risultato)}"))
    print(f"{'totale dagli span':<22} {'':<11} {'':>20} {totale:>10.6f}")


def contenuto(span):
    """Strato 5: cosa ha pensato ogni agente, dal riassunto del ragionamento negli span."""
    per_id = {s["id"]: s for s in span}
    for s, _ in in_ordine(span):
        for messaggio in json.loads(attr(s, "gen_ai.output.messages") or "[]"):
            for parte in messaggio.get("parts", []):
                if parte.get("type") == "reasoning":
                    print(c("giallo", f"pensiero di {agente_di(s, per_id)}: ") + " ".join(parte.get("content", "").split()))


def mostra_metriche(metriche: list):
    """Dallo strato 1: cosa hanno misurato le metriche in questa richiesta."""
    per_agente = {m["attributi"].get("gen_ai.agent.name", "?"): m["somma"] for m in metriche
                  if m["nome"] == "assistente.agente.token"}
    somma = lambda nome: round(sum(m["valore"] for m in metriche if m["nome"] == nome))
    print(c("grigio", "metriche: ") + "assistente.agente.token · " + " · ".join(
        f"{a} {round(n)}" for a, n in sorted(per_agente.items(), key=lambda kv: -kv[1])))
    print(c("grigio", "          ") + f"gen_ai.client.inference.usage · input_tokens "
          f"{somma('gen_ai.client.inference.usage.input_tokens')} · output_tokens {somma('gen_ai.client.inference.usage.output_tokens')}")


def con_email(span) -> int:
    return sum(1 for s in span for v in s["attributi"].values() if isinstance(v, str) and EMAIL.search(v))


def mostra(reg: dict, registrata: bool = False):
    span = reg["span"]
    v = reg.get("variante")
    titolo = f"strato {reg['strato']} · {TITOLI[reg['strato']]}" + (
        " · tool runner" if v == "runner" else f" · variante {v}" if v else "")
    if registrata:
        print(c("inverso", f" REGISTRATA il {reg['registrata'].replace('T', ' alle ')} · {titolo} · {reg['modo']} "))
    else:
        print(c("inverso", f" {titolo} · {reg['modo']} "))
    print(f"\n{c('grigio', 'utente:')} {reg['domanda']}\n{c('verde', 'assistente:')} {reg['risposta']}\n")
    f = reg["fattura"]
    con_contesto = sum("campi" in r for r in reg.get("log_otel", []))
    if con_contesto:  # dallo strato 3 le stesse righe escono anche con il contesto: si stampano li', una volta sola
        print(c("grigio", "log:     ") + f"{con_contesto} righe «chiamata al modello» (sotto, con il contesto) · "
              + reg["log"])
    elif reg.get("righe"):  # una riga per ogni chiamata al modello, con l'id della richiesta e il conto della risposta
        print(c("grigio", "log:"))
        for riga in reg["righe"]:
            print(f"  {dt.datetime.fromtimestamp(riga['tempo']):%H:%M:%S} {riga['livello']} {riga['testo']} "
                  + c("grigio", logfmt(riga["campi"])))
        print("  " + reg["log"])
    else:  # le registrazioni di prima delle righe per chiamata
        print(c("grigio", "log:     ") + reg["log"])
    print(c("grigio", "fattura: ") + f"{f['chiamate']} chiamate · {f['in']} token in · {f['out']} out · "
          f"$ {costo(f['in'], f['cache'], f['out']):.6f}")
    if reg.get("metriche"):
        mostra_metriche(reg["metriche"])
    if not span:
        return
    if reg.get("log_otel"):
        print(c("grigio", "\nlog con contesto:"))
        nomi_span = {s["id"]: s["nome"] for s in span}
        for r in reg["log_otel"]:
            campi = {k: v for k, v in r.get("campi", {}).items() if k not in ("richiesta", "gen_ai.response.model")}
            print(f"  {r['livello']:<5} {r['testo']}" + (c("grigio", " " + logfmt(campi)) if campi else "")
                  + c("grigio", f"  [{nomi_span.get(r['span'], '?')}]"))
    tracce = per_trace(span)
    print(c("grigio", f"\n{len(tracce)} trace per questa richiesta · {len(span)} span\n"))
    t0 = min(x["inizio"] for x in span)
    for tid, ss in tracce.items():
        if len(tracce) > 1:  # come la lista di un backend: id e ora d'inizio, niente che le leghi
            print(c("grigio", f"trace {tid[:8]}  inizia a +{min(x['inizio'] for x in ss) - t0:.1f} s"))
        albero(ss)
    if len(span) > 1 and len(tracce) == 1:
        print()
        cascata(span)
    print()
    verbale(span)
    if any(attr(s, "gen_ai.output.messages") for s in span):
        print()
        contenuto(span)
    if n := con_email(span):
        print(c("rosso", f"\nattenzione: l'email dell'utente compare in {n} attributi di span"))


# --- banco e riepilogo ---

def esito(r: dict) -> dict:
    span, f = r["span"], r["fattura"]
    risposta = r["risposta"] or ""
    return {"tracce": len(per_trace(span)), "span": len(span), "chiamate": f["chiamate"],
            "strumento": sum(attr(s, "gen_ai.operation.name") == "execute_tool" for s in span),
            "esito": valuta(risposta, r["modo"]),
            "secondi": r["secondi"], "token": f["in"] + f["out"], "costo": costo(f["in"], f["cache"], f["out"]),
            "email": con_email(span), "attributi": sum(len(s["attributi"]) for s in span)}


def banco(regs: list):
    print(f"{'#':>2} {'trace':>5} {'span':>4} {'chiamate':>8} {'secondi':>7} {'token':>6} {'costo $':>9}  risposta")
    for i, r in enumerate(regs, 1):
        e = esito(r)
        print(f"{i:>2} {e['tracce']:>5} {e['span']:>4} {e['chiamate']:>8} {e['secondi']:>7.1f} {e['token']:>6} "
              f"{e['costo']:>9.6f}  {' '.join(r['risposta'].split())[:70]}")


def riepilogo(cartella: Path):
    gruppi, speso = {}, 0.0
    for f in sorted(cartella.rglob("*.json")):
        r = json.loads(f.read_text())
        e = esito(r)
        speso += e["costo"]
        gruppi.setdefault((f.parent.name, r["modo"]), []).append(e)
    print(f"{'cartella':<28} {'modo':6} {'n':>3} {'trace':>5} {'span':>4} {'attr':>4} {'chiam.':>6} "
          f"{'giuste':>6} {'avvis.':>6} {'sbagl.':>6} {'email':>5} {'sec med':>7} {'token med':>9} {'$ med':>9}")
    for (cartella_, modo), ee in sorted(gruppi.items()):
        conta = lambda k: sum(e["esito"] == k for e in ee) if k in ESITI else sum(e[k] for e in ee)
        med = lambda k: statistics.median(e[k] for e in ee)
        print(f"{cartella_:<28} {modo:6} {len(ee):>3} {med('tracce'):>5.0f} {med('span'):>4.0f} "
              f"{med('attributi'):>4.0f} {med('chiamate'):>6.0f} {conta('giusta'):>6} {conta('avvisata'):>6} {conta('sbagliata'):>6} "
              f"{med('email'):>5.0f} {med('secondi'):>7.1f} {med('token'):>9.0f} {med('costo'):>9.6f}")
    print(f"\nspeso in tutto, dalle registrazioni: $ {speso:.4f}")


# --- misure del grafo: cosa ha deciso il modello, run per run ---


# I thread di uno stesso giro partono a pochi millisecondi uno dall'altro: se uno strumento istantaneo (leggi_programma)
# finisce prima che parta il fratello (un agente), sono comunque dello stesso giro. Un giro dopo, invece, parte dopo una
# chiamata al modello (secondi).
SCARTO_GIRO_S = 0.02


def grafo(span) -> list[str]:
    """Chi ha chiamato che cosa, in una forma che non dipende da chi e' partito prima nei rami paralleli.

    Le chiamate figlie dello stesso invoke_agent che partono mentre una del giro e' ancora in corso sono dello
    stesso giro (il modello le ha chieste insieme): si scrivono come insieme ordinato, `{avvisi,programma,sale}`.
    Dentro un'agente-strumento, fra parentesi, cosa ha chiamato a sua volta; `!` se lo span e' in errore."""
    figli = {}
    for x in span:
        figli.setdefault(x["padre"], []).append(x)
    e = lambda x, operazione: attr(x, "gen_ai.operation.name") == operazione

    def giri(agente_span):
        chiamate = sorted((x for x in figli.get(agente_span["id"], []) if e(x, "execute_tool")), key=lambda x: x["inizio"])
        gruppi = []
        for x in chiamate:
            if gruppi and (x["inizio"] < max(y["fine"] for y in gruppi[-1])  # parte mentre una del giro e' ancora in corso
                           or x["inizio"] - gruppi[-1][0]["inizio"] < SCARTO_GIRO_S):  # o subito dopo: uno strumento istantaneo
                gruppi[-1].append(x)
            else:
                gruppi.append([x])
        return gruppi

    def voce(gruppo):
        nomi = []
        for x in gruppo:
            dentro = " ".join(voce(g) for a in sorted((a for a in figli.get(x["id"], []) if e(a, "invoke_agent")),
                                                     key=lambda a: a["inizio"]) for g in giri(a))
            nomi.append(attr(x, "gen_ai.tool.name") + ("!" if x["errore"] else "") + (f"({dentro})" if dentro else ""))
        return nomi[0] if len(nomi) == 1 else "{" + ",".join(sorted(nomi)) + "}"

    per_id, passi = {x["id"]: x for x in span}, []
    radici = sorted((x for x in span if e(x, "invoke_agent")
                     and not (per_id.get(x["padre"]) and e(per_id[x["padre"]], "execute_tool"))), key=lambda x: x["inizio"])
    for a in radici:
        nome = attr(a, "gen_ai.agent.name")
        passi.append(f"codice>{nome}")  # un agente chiamato dal codice, non da un modello
        passi += [f"{nome}>{voce(g)}" for g in giri(a)]
    return passi


# Le misure della giornata piena. Ognuna dice da quale strato in su gli span che servono esistono: sotto, None.
MINIMO_MISURE = {"stesso_giro": 2, "dopo_sala": 2, "token": 2, "letto": 3, "riporta": 3, "verdetti": 3, "email_valida": 3,
                 "pagine": 4, "sale_due": 2, "valida_rivede": 2, "valida_riporta": 3, "dialogo": 2, "dialogo_riporta": 3,
                 "cicli": 2, "profondita_agenti": 2, "domanda_avvisi": 3}


def domande_ad_avvisi(span) -> list[str]:
    """Gli argomenti `richiesta` degli archi coordina -> avvisi, nell'ordine in cui sono partiti."""
    fuori = []
    for x in archi(span, ("avvisi",), da="coordina"):
        try:
            fuori.append(str(json.loads(attr(x, "gen_ai.tool.call.arguments", "{}")).get("richiesta", "")))
        except (ValueError, AttributeError):
            fuori.append("")
    return fuori


def archi(span, verso=None, da=None) -> list:
    """Gli archi fra agenti (execute_tool con destinazione), in ordine di inizio, magari solo verso certi agenti
    e/o solo chiamati da un certo agente."""
    return sorted((x for x in span if attr(x, "gen_ai.operation.name") == "execute_tool"
                   and attr(x, "gen_ai.transfer.target.name") and (verso is None or attr(x, "gen_ai.transfer.target.name") in verso)
                   and (da is None or attr(x, "gen_ai.agent.name") == da)),
                  key=lambda x: x["inizio"])


def strumenti(span, nome: str) -> list:
    return [x for x in span if attr(x, "gen_ai.operation.name") == "execute_tool" and attr(x, "gen_ai.tool.name") == nome
            and not attr(x, "gen_ai.transfer.target.name")]


def stesso_giro(span) -> bool:
    """programma, sale e avvisi sono partiti insieme: gli archi hanno lo stesso padre e si sovrappongono nel tempo."""
    primi = {}
    for x in archi(span, ("programma", "sale", "avvisi"), da="coordina"):  # le chiamate annidate non contano
        primi.setdefault(attr(x, "gen_ai.transfer.target.name"), x)
    tre = list(primi.values())
    return len(tre) == 3 and len({x["padre"] for x in tre}) == 1 and max(x["inizio"] for x in tre) < min(x["fine"] for x in tre)


def avvisi_dopo_sala(span) -> bool:
    """avvisi e' stato chiamato quando programma o sale avevano gia' finito: coordina sapeva gia' la sala."""
    precedenti = archi(span, ("programma", "sale"), da="coordina")
    return any(p["fine"] <= a["inizio"] for a in archi(span, ("avvisi",), da="coordina") for p in precedenti)


def sale_da_due(span) -> bool:
    """sale e' stato chiamato da due agenti diversi (coordina e programma): lo stesso dato letto per due strade."""
    return len({attr(x, "gen_ai.agent.name") for x in archi(span, ("sale",))}) >= 2


def figli_arco(span, arco):
    """Gli archi che l'agente chiamato da `arco` ha chiamato a sua volta."""
    dentro = {x["id"] for x in span if x["padre"] == arco["id"] and attr(x, "gen_ai.operation.name") == "invoke_agent"}
    return [x for x in archi(span) if x["padre"] in dentro]


def dialogo(span) -> bool:
    """avvisi ha chiesto a programma (la correzione dialogo)."""
    return bool(archi(span, ("programma",), da="avvisi"))


def dialogo_riporta(span) -> bool:
    """...e poi la sua risposta riporta l'avviso sulla sala B."""
    return any(riporta_avviso(attr(a, "gen_ai.tool.call.result", "")) for a in archi(span, ("avvisi",))
               if any(attr(f, "gen_ai.transfer.target.name") == "programma" for f in figli_arco(span, a)))


def cicli(span) -> int:
    """Quante volte la guardia ha rifiutato una chiamata (archi in errore con error.type ciclo)."""
    return sum(attr(x, "error.type") == "ciclo" for x in archi(span))


def profondita_agenti(span) -> int:
    """Quanti agenti uno dentro l'altro, contando gli archi da coordina in giu': il ramo piu' lungo."""
    per_id, fondo = {x["id"]: x for x in span}, 0
    for a in archi(span):
        n, y = 0, a
        while y:
            n += attr(y, "gen_ai.transfer.target.name") is not None and attr(y, "gen_ai.operation.name") == "execute_tool"
            y = per_id.get(y["padre"])
        fondo = max(fondo, n)
    return fondo


def _letture_avvisi(span, di_coordina: bool) -> int:
    """Pagine lette da leggi_avvisi: quelle sotto l'arco di avvisi chiamato da coordina, oppure tutte le altre."""
    per_id, tot = {x["id"]: x for x in span}, 0
    for x in strumenti(span, "leggi_avvisi"):
        y = per_id.get(x["padre"])
        while y and not (attr(y, "gen_ai.operation.name") == "execute_tool" and attr(y, "gen_ai.transfer.target.name")):
            y = per_id.get(y["padre"])
        if (y is not None and attr(y, "gen_ai.agent.name") == "coordina") == di_coordina:
            tot += attr(x, "avvisi.pagine", 0)
    return tot


def pagine_avvisi(span) -> int:
    """Le pagine che legge l'avvisi chiamato da coordina: il numero della slide."""
    return _letture_avvisi(span, True)


def pagine_ricontrolli(span) -> int:
    """Le pagine lette da leggi_avvisi sotto qualunque altro chiamante (i ricontrolli di valida, il dialogo)."""
    return _letture_avvisi(span, False)


def verdetti(span) -> list[bool]:
    return [approva(attr(x, "gen_ai.tool.call.result")) for x in archi(span, ("valida",))
            if attr(x, "gen_ai.tool.call.result") is not None]


def token_per_agente(span) -> dict:
    """Token (ingresso e uscita) delle chiamate al modello, per agente che le ha fatte."""
    per_id, fuori = {x["id"]: x for x in span}, {}
    for x in span:
        if t := token(x):
            nome = agente_di(x, per_id)
            fuori[nome] = fuori.get(nome, 0) + t["in"] + t["out"]
    return fuori


def chiamate_dagli_span(span) -> list[dict]:
    """Le chiamate al modello ricostruite dagli span, dallo strato 2 in su, in ordine di fine: l'agente e il suo
    invoke_agent (lo span corrente quando la riga di log parte), la fine e il conto con i nomi del provider. Servono a
    tempo.py: le registrazioni del banco del 5/11 sono di prima delle righe per chiamata e delle metriche, e righe e
    misure si rifanno da qui, con le cifre di quella run. L'SDK scrive gen_ai.usage.input_tokens con la cache dentro."""
    per_id, fuori = {x["id"]: x for x in span}, []
    for x in sorted(span, key=lambda x: x["fine"]):
        if (t := token(x)) is None:
            continue
        y = x
        while y and attr(y, "gen_ai.operation.name") != "invoke_agent":
            y = per_id.get(y["padre"])
        if y is None:  # sotto lo strato 2 l'agente non si sa
            continue
        scritti = attr(x, "gen_ai.usage.cache_write.input_tokens") or 0
        fuori.append({"agente": attr(y, "gen_ai.agent.name"), "span": y["id"], "trace": x["trace"], "fine": x["fine"],
                      "campi": {"gen_ai.agent.name": attr(y, "gen_ai.agent.name"),
                                "gen_ai.response.model": attr(x, "gen_ai.response.model", MODEL),
                                "gen_ai.usage.input_tokens": t["in"], "gen_ai.usage.output_tokens": t["out"],
                                "gen_ai.usage.cache_read.input_tokens": t["cache"],
                                "gen_ai.usage.cache_write.input_tokens": scritti}})
    return fuori


def costo_per_agente(span) -> dict:
    """Costo in $ (a LISTINO) delle chiamate al modello, per agente che le ha fatte."""
    per_id, fuori = {x["id"]: x for x in span}, {}
    for x in span:
        if t := token(x):
            nome = agente_di(x, per_id)
            fuori[nome] = fuori.get(nome, 0) + costo(t["in"], t["cache"], t["out"])
    return fuori


def quota_riletture(span) -> float | None:
    """Quota dei token in ingresso che il modello rilegge. In ogni invoke_agent, ogni chiamata dopo la prima rilegge
    la conversazione fin li': conta i token in ingresso della chiamata precedente dello stesso invoke_agent. La quota
    e' la somma di questi sulla somma dei token in ingresso di tutte le chiamate (None se non ci sono token)."""
    per_id, per_invoke = {x["id"]: x for x in span}, {}
    for x in span:
        if token(x):
            y = x
            while y and attr(y, "gen_ai.operation.name") != "invoke_agent":
                y = per_id.get(y["padre"])
            per_invoke.setdefault(y["id"] if y else None, []).append(x)
    totale = sum(token(x)["in"] for xs in per_invoke.values() for x in xs)
    riletti = sum(token(a)["in"] for xs in per_invoke.values() for a, _ in zip(sorted(xs, key=lambda x: x["inizio"]), xs[1:]))
    return riletti / totale if totale else None


def quota_avvisi(span) -> float | None:
    """Che parte dei token della richiesta e' spesa dall'agente avvisi (None se non ci sono token)."""
    per_agente = token_per_agente(span)
    return per_agente.get("avvisi", 0) / sum(per_agente.values()) if per_agente else None


def misura(r: dict) -> dict:
    """Cosa e' successo in una run: il grafo, cosa ha letto e riportato avvisi, i verdetti di valida, i token per agente.
    None dove gli span che servono non esistono a quello strato."""
    span, risposta, strato = r["span"], r["risposta"] or "", r["strato"]
    se = lambda nome, valore: valore() if strato >= MINIMO_MISURE[nome] else None
    livelli = [lv for _, lv in in_ordine(span)]
    avvisi_tool, a_avvisi = strumenti(span, "leggi_avvisi"), archi(span, ("avvisi",), da="coordina")
    ricontrolli = archi(span, ("avvisi",), da="valida")
    verdetto = se("verdetti", lambda: verdetti(span))
    return {**esito(r), "grafo": " ".join(grafo(span)), "profondita": max(livelli) + 1 if livelli else 0,
            "stesso_giro": se("stesso_giro", lambda: stesso_giro(span)),
            "avvisi_dopo_sala": se("dopo_sala", lambda: avvisi_dopo_sala(span)),
            "pagine_avvisi": se("pagine", lambda: pagine_avvisi(span)),
            "pagine_ricontrolli": se("pagine", lambda: pagine_ricontrolli(span)),
            "tool_ha_avviso": se("letto", lambda: any(AVVISO_CHIAVE in attr(x, "gen_ai.tool.call.result", "") for x in avvisi_tool)),
            "avvisi_riporta": se("riporta", lambda: any(riporta_avviso(attr(x, "gen_ai.tool.call.result", "")) for x in a_avvisi)),
            "classe_domanda": se("domanda_avvisi", lambda: classe_domanda(domande_ad_avvisi(span)[0]) if a_avvisi else None),
            "avvisi_riporta_primo": se("domanda_avvisi", lambda: bool(a_avvisi) and riporta_avviso(attr(a_avvisi[0], "gen_ai.tool.call.result", ""))),
            "avvisi_con_sala": se("riporta", lambda: any(AVVISI_SALA_B.search(attr(x, "gen_ai.tool.call.arguments", "")) for x in a_avvisi)),
            "sale_da_due": se("sale_due", lambda: sale_da_due(span)),
            "valida_avvisi": se("valida_rivede", lambda: bool(ricontrolli)),
            "valida_avvisi_riporta": se("valida_riporta", lambda: any(riporta_avviso(attr(x, "gen_ai.tool.call.result", "")) for x in ricontrolli)),
            "valida_programma": se("valida_rivede", lambda: bool(archi(span, ("programma",), da="valida"))),
            "avvisi_chiede_programma": se("dialogo", lambda: dialogo(span)),
            "avvisi_poi_riporta": se("dialogo_riporta", lambda: dialogo_riporta(span)),
            "cicli": se("cicli", lambda: cicli(span)),
            "profondita_agenti": se("profondita_agenti", lambda: profondita_agenti(span)),
            "valida_chiamate": None if verdetto is None else len(verdetto),
            "valida_approva": None if verdetto is None else sum(verdetto),
            "email_a_valida": se("email_valida", lambda: any(EMAIL.search(attr(x, "gen_ai.tool.call.arguments", ""))
                                                             for x in archi(span, ("valida",)))),
            "token_agente": se("token", lambda: token_per_agente(span)),
            "quota_avvisi": se("token", lambda: quota_avvisi(span)),
            "costo_agente": se("token", lambda: costo_per_agente(span)),
            "riletture": se("token", lambda: quota_riletture(span))}


def tabella_domande(mm: list[dict]) -> list[str]:
    """La tabella incrociata «domanda di coordina ad avvisi × esito», sulla prima domanda di ogni run (quella dei rami
    paralleli, quando coordina non sa ancora la sala), e per ogni classe quante volte avvisi riporta l'avviso a coordina
    (nella prima risposta e in qualunque giro)."""
    righe = [f"  {'domanda di coordina ad avvisi × esito':<50} {'n':>3} {'giusta':>7} {'avvisata':>9} {'sbagliata':>10}"
             f" {'avvisi riporta (1° giro)':>25} {'(qualunque giro)':>17}"]
    for classe in CLASSI_DOMANDA + (None,):
        gruppo = [m for m in mm if m["classe_domanda"] == classe]
        if not gruppo:
            continue
        nome = {"variazioni": "nomina orario, sala, variazioni...", "sessione": "nomina solo la sessione",
                None: "avvisi non chiamato"}[classe]
        righe.append(f"    {nome:<48} {len(gruppo):>3} " + " ".join(
            f"{sum(m['esito'] == e for m in gruppo):>{w}}" for e, w in zip(ESITI, (7, 9, 10)))
            + f" {sum(m['avvisi_riporta_primo'] for m in gruppo):>25} {sum(bool(m['avvisi_riporta']) for m in gruppo):>17}")
    return righe


def misure(cartelle: list[Path]):
    for cartella in cartelle:
        regs = [json.loads(f.read_text()) for f in sorted(cartella.glob("*.json"))]
        if not regs:
            continue
        print(c("inverso", f" {cartella.name} "))
        for modo in ("guasto", "sana"):
            mm = [misura(r) for r in regs if r["modo"] == modo]
            if not mm:
                continue
            n, strato = len(mm), regs[0]["strato"]
            med = lambda k: statistics.median(m[k] for m in mm)

            def conta(k, minimo, etichetta):  # quante run su n; se lo strato non basta lo dice
                if any(m[k] is None for m in mm):
                    return f"  {etichetta:<52} serve lo strato {minimo}"
                return f"  {etichetta:<52} {sum(bool(m[k]) for m in mm):>2} su {n}"
            print(f"{modo}: n {n} · " + " · ".join(
                f"{e} {sum(1 for m in mm if m['esito'] == e)}" for e in ESITI))
            print(conta("stesso_giro", 2, "programma, sale, avvisi nello stesso giro"))
            print(conta("avvisi_dopo_sala", 2, "avvisi chiamato dopo che si sapeva la sala"))
            print(conta("avvisi_con_sala", 3, "la richiesta ad avvisi nomina la sala B"))
            print(conta("tool_ha_avviso", 3, "leggi_avvisi ha restituito l'avviso sulla sala B"))
            print(conta("avvisi_riporta", 3, "avvisi lo riporta a coordina"))
            if strato >= MINIMO_MISURE["domanda_avvisi"] and modo == "guasto":
                print("\n".join(tabella_domande(mm)))
            print(conta("sale_da_due", 2, "sale chiamato da due chiamanti diversi"))
            print(conta("valida_avvisi", 2, "valida richiede ad avvisi"))
            print(conta("valida_avvisi_riporta", 3, "...e la risposta di avvisi riporta l'avviso"))
            print(conta("valida_programma", 2, "valida richiede a programma"))
            if regs[0].get("correzione") == 3:  # solo la correzione dialogo
                print(conta("avvisi_chiede_programma", 2, "avvisi chiede a programma"))
                print(conta("avvisi_poi_riporta", 3, "...e poi avvisi riporta l'avviso"))
            if strato < MINIMO_MISURE["pagine"]:
                print(f"  {'pagine di avvisi lette':<52} serve lo strato 4")
            else:
                print(f"  {'pagine di avvisi lette da coordina':<52} mediana {med('pagine_avvisi'):.0f} (da {min(m['pagine_avvisi'] for m in mm)} "
                      f"a {max(m['pagine_avvisi'] for m in mm)})")
                print(f"  {'pagine di avvisi nei ricontrolli':<52} mediana {med('pagine_ricontrolli'):.0f} (da {min(m['pagine_ricontrolli'] for m in mm)} "
                      f"a {max(m['pagine_ricontrolli'] for m in mm)})")
            if any(m["valida_approva"] is None for m in mm):
                print(f"  {'valida approva':<52} serve lo strato 3")
            else:
                print(f"  {'valida approva':<52} {sum(m['valida_approva'] > 0 for m in mm):>2} su {n} · "
                      f"mai chiamata in {sum(m['valida_chiamate'] == 0 for m in mm)}")
            print(conta("email_a_valida", 3, "l'email arriva a valida"))
            if strato < MINIMO_MISURE["token"]:
                print(f"  {'token per agente':<52} serve lo strato 2")
            else:
                agenti = sorted({a for m in mm for a in m["token_agente"]})
                print(f"  {'token per agente (mediana)':<52} " + " · ".join(
                    f"{a} {statistics.median(m['token_agente'].get(a, 0) for m in mm):.0f}" for a in agenti))
                print(f"  {'costo per agente, $ (mediana)':<52} " + " · ".join(
                    f"{a} {statistics.median(m['costo_agente'].get(a, 0) for m in mm):.6f}" for a in agenti))
                print(f"  {'quota di avvisi sui token della richiesta':<52} mediana {med('quota_avvisi'):.0%}")
                print(f"  {'quota delle riletture (token in ingresso)':<52} mediana {med('riletture'):.0%}")
            if strato < MINIMO_MISURE["cicli"]:
                print(f"  {'guardia dei cicli scattata':<52} serve lo strato 2")
            else:
                print(f"  {'guardia dei cicli scattata':<52} {sum(m['cicli'] > 0 for m in mm):>2} su {n} · {sum(m['cicli'] for m in mm)} volte"
                      + (" · guardia mai scattata" if not any(m['cicli'] for m in mm) else ""))
                print(f"  massimi: profondità {max(m['profondita'] for m in mm)} (agenti uno dentro l'altro "
                      f"{max(m['profondita_agenti'] for m in mm)}) · span {max(m['span'] for m in mm)}")
            print(f"  mediane: profondità {med('profondita'):.0f} · span {med('span'):.0f} · chiamate al modello "
                  f"{med('chiamate'):.0f} · token {med('token'):.0f} · secondi {med('secondi'):.1f} · $ {med('costo'):.6f}")
            grafi = {}
            for m in mm:
                grafi[m["grafo"]] = grafi.get(m["grafo"], 0) + 1
            if strato < 2:  # senza invoke_agent non c'e' un albero da confrontare
                print(f"  {"forme dell'albero":<52} serve lo strato 2")
            else:
                print(f"  {len(grafi)} forme dell'albero:")
                for g, k in sorted(grafi.items(), key=lambda kv: -kv[1]):
                    print(f"    {k:>2} × {g}")
        print()


# --- lo schema del sistema: il grafo delle chiamate fra agenti, aggregato sulle run ---

ORDINE_NODI = ("utente", "coordina", "programma", "sale", "avvisi", "valida")  # l'ordine in cui si disegnano


def _ordine(nome: str):
    return (ORDINE_NODI.index(nome), nome) if nome in ORDINE_NODI else (len(ORDINE_NODI), nome)


def archi_della_run(span) -> dict:
    """Per una run: {(chiamante, chiamato): quante volte}, con gli strumenti dei dati (leggi_*) come foglie.
    Il chiamante di uno strumento dei dati e' l'agente dell'invoke_agent che lo contiene."""
    per_id, fuori = {x["id"]: x for x in span}, {}
    for x in span:
        if attr(x, "gen_ai.operation.name") != "execute_tool":
            continue
        if attr(x, "gen_ai.transfer.target.name"):
            chiave = (attr(x, "gen_ai.agent.name"), attr(x, "gen_ai.transfer.target.name"))
        else:
            padre = per_id.get(x["padre"])
            chiave = (attr(padre, "gen_ai.agent.name") if padre else None, attr(x, "gen_ai.tool.name"))
        if chiave[0] and chiave[1]:
            fuori[chiave] = fuori.get(chiave, 0) + 1
    return fuori


def _agenti(span) -> set:
    return {attr(x, "gen_ai.agent.name") for x in span if attr(x, "gen_ai.operation.name") == "invoke_agent"}


def schema(regs: list[dict], senza_strumenti: bool = False) -> tuple[str, str]:
    """(testo, mermaid) dello schema delle chiamate, sulle registrazioni date (tutte dallo strato 2 in su)."""
    n = len(regs)
    strato = min(r["strato"] for r in regs)
    archi_run = [archi_della_run(r["span"]) for r in regs]
    agenti = set().union(*(_agenti(r["span"]) for r in regs)) | {"coordina"}
    arco = {}  # (da, a) -> [run in cui compare, volte in totale]
    for ar in archi_run:
        for k, v in ar.items():
            e = arco.setdefault(k, [0, 0])
            e[0] += 1
            e[1] += v
    # rimpalli: chi e' chiamato da due chiamanti diversi nella stessa run
    due_chiamanti, doppia_strada = {}, False
    for ar in archi_run:
        chiamanti = {}
        for (da, a) in ar:
            if a in agenti:
                chiamanti.setdefault(a, set()).add(da)
        for a, ds in chiamanti.items():
            if len(ds) >= 2:
                due_chiamanti.setdefault(a, [0, set()])
                due_chiamanti[a][0] += 1
                due_chiamanti[a][1] |= ds
        doppia_strada |= {"coordina", "programma"} <= chiamanti.get("sale", set())
    guardie = [(r, [x for x in archi(r["span"]) if attr(x, "error.type") == "ciclo"]) for r in regs]
    arco_guardia = {(attr(x, "gen_ai.agent.name"), attr(x, "gen_ai.transfer.target.name")) for _, g in guardie for x in g}
    # tratteggiati: chi controlla o chiede a una fonte fuori dal giro di coordina (valida che richiama, avvisi che chiede a
    # programma) e gli archi respinti dalla guardia. In rosso, pieno: la strada in piu' coordina → sale, quando sale e'
    # chiamato anche da programma nella stessa run (programma → sale e' la strada normale, resta piena).
    tratteggiati = {k for k in arco if k[0] == "valida" or k == ("avvisi", "programma")} | arco_guardia
    tratteggiati = {k for k in tratteggiati if k in arco}
    in_rosso = {("coordina", "sale")} if doppia_strada and ("coordina", "sale") in arco else set()
    rimpalli = tratteggiati | in_rosso

    # --- il testo ---
    righe = [f"schema del sistema: {n} run, strato {strato}", "", "chi chiama chi (in quante run · volte in totale)"]
    righe.append(f"   {'utente → coordina':<28} {n:>3} su {n} · {n:>3} volte")
    ordinati = sorted((k for k in arco if k[1] in agenti), key=lambda k: (_ordine(k[0]), _ordine(k[1])))
    for k in ordinati:
        segno = "  *" if k in rimpalli else "   "
        righe.append(f"{segno}{k[0] + ' → ' + k[1]:<28} {arco[k][0]:>3} su {n} · {arco[k][1]:>3} volte")
    foglie = sorted((k for k in arco if k[1] not in agenti), key=lambda k: (_ordine(k[0]), k[1]))
    if foglie and not senza_strumenti:
        righe.append("  strumenti dei dati")
        for k in foglie:
            righe.append(f"     {k[0] + ' → ' + k[1]:<28} {arco[k][0]:>3} su {n} · {arco[k][1]:>3} volte")
    righe += ["", "rimpalli (* nell'elenco sopra)"]
    for a in sorted(due_chiamanti, key=_ordine):
        righe.append(f"  {a} chiamato da {len(due_chiamanti[a][1])} chiamanti ({', '.join(sorted(due_chiamanti[a][1], key=_ordine))}): "
                     f"{due_chiamanti[a][0]} run su {n}")
    if not due_chiamanti:
        righe.append(f"  nessun agente chiamato da piu' chiamanti nella stessa run: 0 run su {n}")
    for fonte in ("avvisi", "programma"):
        k = ("valida", fonte)
        righe.append(f"  valida richiama {fonte}: {arco[k][0] if k in arco else 0} run su {n}")
        if fonte == "avvisi":
            if strato < MINIMO_MISURE["valida_riporta"]:
                righe.append("    ...e la risposta riporta l'avviso sulla sala B: serve lo strato 3")
            else:
                riportano = sum(any(riporta_avviso(attr(x, "gen_ai.tool.call.result", "")) for x in archi(r["span"], ("avvisi",), da="valida"))
                                for r in regs)
                righe.append(f"    ...e la risposta riporta l'avviso sulla sala B: {riportano} run su {n}")
    k = ("avvisi", "programma")
    righe.append(f"  avvisi chiede a programma (dialogo): {arco[k][0] if k in arco else 0} run su {n}")
    righe.append(f"  guardia dei cicli scattata: {sum(bool(g) for _, g in guardie)} run su {n} · {sum(len(g) for _, g in guardie)} volte")

    # --- Mermaid ---
    def etichetta(k):
        run, volte = arco[k]
        media = round(volte / run, 1)
        return f"{run}/{n}" + (f" ×{media:.1f}" if media > 1 else "")
    mm = ["flowchart LR", "  %% legenda: ogni arco e' «in quante run su quante» (×N = volte per run, in media);",
          "  %% tratteggiato = chi controlla o chiede a una fonte fuori dal giro di coordina (valida che richiama, avvisi che "
          "chiede a programma, arco respinto dalla guardia); rosso = coordina → sale quando sale e' chiamato anche da programma"]
    nodi = sorted(agenti, key=_ordine)
    mm.append("  utente([utente])")
    mm += [f"  {a}[{a}]" for a in nodi]
    mm.append(f"  utente -->|{n}/{n}| coordina")
    tratti, rossi = [], []
    for i, k in enumerate(ordinati, start=1):
        mm.append(f"  {k[0]} {'-.->' if k in tratteggiati else '-->'}|{etichetta(k)}| {k[1]}")
        if k in tratteggiati:
            tratti.append(i)
        if k in in_rosso:
            rossi.append(i)
    if tratti:
        mm.append(f"  linkStyle {','.join(map(str, tratti))} stroke:#7f8c8d,stroke-width:2px,color:#7f8c8d")
    if rossi:
        mm.append(f"  linkStyle {','.join(map(str, rossi))} stroke:#c0392b,stroke-width:3px,color:#c0392b")
    return "\n".join(righe), "\n".join(mm)


def mostra_schema(cartella: Path, modo: str | None = None, senza_strumenti: bool = False):
    if not cartella.is_dir():
        raise SystemExit(f"{cartella}: non e' una cartella di registrazioni")
    regs = [json.loads(f.read_text()) for f in sorted(cartella.glob("*.json"))]
    if not regs:
        raise SystemExit(f"{cartella}: nessuna registrazione")
    if min(r["strato"] for r in regs) < 2:
        print("lo schema delle chiamate serve lo strato 2: sotto non ci sono gli span degli agenti")
        return
    regs = [r for r in regs if modo is None or r["modo"] == modo]
    if not regs:
        print(f"nessuna registrazione in modo {modo}")
        return
    testo, mermaid = schema(regs, senza_strumenti)
    print(testo)
    print("\n```mermaid\n" + mermaid + "\n```")


FILE_CON_MARCATORI = (tracce.__file__, osservabilita_log.__file__, metriche.__file__, osservabilita_client.__file__,
                      strumenti_mod.__file__, ciclo_mod.__file__, esecuzione_mod.__file__, prompt_mod.__file__,
                      registrazioni_mod.__file__, __file__)


def _righe_di(percorso: str) -> list[str]:
    return Path(percorso).read_text().splitlines()


def righe():
    """Le righe di codice di ogni strato, contate dai marcatori sN dopo il cancelletto."""
    testo = [r for percorso in FILE_CON_MARCATORI for r in _righe_di(percorso)]
    for n in range(6):
        marcate = [r for r in testo if re.search(rf"#\s*s{n}\b", r) and not r.lstrip().startswith("#")]
        print(f"strato {n} · {TITOLI[n]:<28} {len(marcate):>3} righe")


def codice(n: int) -> str:
    """Le righe dello strato n come si scriverebbero senza l'impalcatura della demo, per le slide."""
    fuori = []
    for percorso in FILE_CON_MARCATORI:
        testo = _righe_di(percorso)
        marcate = [i for i, r in enumerate(testo) if re.search(rf"#\s*s{n}\b", r) and not r.lstrip().startswith("#")]
        blocchi = []
        for i in marcate:
            if blocchi and not "".join(testo[blocchi[-1][-1] + 1:i]).strip():  # in mezzo solo righe vuote
                blocchi[-1].extend(range(blocchi[-1][-1] + 1, i + 1))
            else:
                blocchi.append([i])
        for blocco in blocchi:
            righe_, rientro_if = [], None
            for i in blocco:
                r = re.sub(rf"\s+#\s*s{n}\b.*$", "", testo[i]).replace(f"tracer({n}).", "tracer.").replace(", **prova)", ")")
                if re.match(rf"\s*if attuali\(\)\.strato >= {n}:", r):
                    rientro_if = len(r) - len(r.lstrip())
                    continue
                if rientro_if is not None and len(r) - len(r.lstrip()) > rientro_if:
                    r = r[4:]
                righe_.append(r)
            fuori.append(textwrap.dedent("\n".join(righe_)))
    return "\n...\n".join(fuori)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--strato", type=int, choices=range(6), default=0)
    p.add_argument("--guasto", action="store_true")
    p.add_argument("--correzione", action="store_true", help="coordina chiede ad avvisi la sala della sessione")
    p.add_argument("--correzione-completa", action="store_true", help="...e leggi_avvisi restituisce solo gli avvisi di quella sala")
    p.add_argument("--correzione-dialogo", action="store_true", help="avvisi puo' chiedere a programma giorno, ora e sala (alternativa alle altre due)")
    p.add_argument("--maschera", action="store_true", help="solo con --strato 5: l'email non esce dagli span")
    p.add_argument("--produzione", action="store_true", help="dallo strato 2: il riassunto della richiesta sulla radice")
    p.add_argument("--otlp", metavar="URL", help="esporta gli span via HTTP (implica --produzione)")
    p.add_argument("--banco", type=int, default=0)
    p.add_argument("--replay")
    p.add_argument("--riepilogo", action="store_true")
    p.add_argument("--misure", type=int, metavar="N", help="le misure della giornata piena e della tranquilla in uno strato")
    p.add_argument("--schema", metavar="CARTELLA", help="il grafo delle chiamate fra agenti sulle registrazioni (strato 2+), in testo e Mermaid")
    p.add_argument("--modo", choices=("guasto", "sana"), help="con --schema: solo le run di quel modo")
    p.add_argument("--senza-strumenti", action="store_true", help="con --schema: nascondi gli strumenti dei dati (leggi_*)")
    p.add_argument("--righe", action="store_true")
    p.add_argument("--codice", type=int, choices=range(6), metavar="N", help="le righe di uno strato, pulite per le slide")
    a = p.parse_args()
    if a.schema:
        mostra_schema(Path(a.schema), a.modo, a.senza_strumenti)
    elif a.righe:
        righe()
    elif a.codice is not None:
        print(codice(a.codice))
    elif a.misure is not None:
        misure(sorted(QUI.glob(f"registrazioni/strato-{a.misure}*")))
    elif a.riepilogo:
        riepilogo(QUI / "registrazioni")
    elif a.replay:
        mostra(registrazioni_mod.leggi(Path(a.replay)), registrata=True)
    else:
        if a.maschera and a.strato != 5:
            raise SystemExit("--maschera serve allo strato 5, dove il contenuto entra negli span")
        produzione, otlp = a.produzione or bool(a.otlp), a.otlp
        if produzione and a.strato < 2:
            raise SystemExit("--produzione serve dallo strato 2, dove c'e' la radice della richiesta")
        maschera = a.maschera
        correzione = 3 if a.correzione_dialogo else 2 if a.correzione_completa else 1 if a.correzione else 0
        a.guasto = a.guasto or correzione > 0  # la correzione ha senso solo nella giornata piena
        i = Impostazioni(strato=a.strato, correzione=correzione, maschera=maschera, produzione=produzione, otlp=otlp)
        imposta(i)
        cartella = registrazioni_mod.cartella_della_run(i)
        if a.banco:
            esecuzione_mod.concludi_banco(a.banco, *esecuzione_mod.esegui_banco(a.banco, a.guasto, cartella))
        else:
            mostra(esecuzione_mod.esegui(a.guasto, cartella))
