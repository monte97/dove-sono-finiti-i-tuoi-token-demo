"""La stessa risposta sbagliata, osservata uno strato alla volta.

Due agenti: `cerca` legge il programma con lo strumento `leggi_programma`, `valida` controlla
la risposta senza vedere la fonte. Il servizio del programma e' simulato e il difetto e' messo
apposta: dopo un timeout lo strumento serve per 120 s la copia di ieri (15:00 invece di 14:00).

Strati (ognuno contiene i precedenti):
  0  oggi: una riga di log e la fattura, niente OpenTelemetry
  1  l'SDK: la strumentazione nativa di anthropic, nient'altro
  2  la radice: span invoke_workflow e invoke_agent scritti a mano
  3  lo strumento: span execute_tool con argomenti, risultato, timeout
  4  la provenienza: span cache.read con eta' e motivo della copia
  5  il contenuto: content_mode "content" (messaggi e ragionamento riassunto)

  python strati.py --strato 3 --guasto             una run
  python strati.py --strato 3 --guasto --banco 5   cinque run, una riga ciascuna
  python strati.py --strato 1 --runner --guasto    strato 1 con il tool runner dell'SDK
  python strati.py --replay registrazioni/strato-3/<file>.json
  python strati.py --riepilogo                     una riga per strato e modo
  python strati.py --righe                         righe di codice di ogni strato

Le righe che esistono solo per osservare finiscono con il marcatore dello strato (s0 ... s5 dopo il cancelletto).
"""

import argparse
import datetime as dt
import json
import re
import statistics
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Status, StatusCode

QUI = Path(__file__).parent
load_dotenv(QUI / ".env")

TITOLI = {0: "oggi: un log e una fattura", 1: "l'SDK", 2: "la radice", 3: "lo strumento",
          4: "la provenienza", 5: "il contenuto"}
STRATO = 0

memoria = InMemorySpanExporter()  # s1  ponytail: in memoria; dal vivo un exporter OTLP verso un backend
provider = TracerProvider()  # s1
provider.add_span_processor(SimpleSpanProcessor(memoria))  # s1
_vero, _spento = provider.get_tracer("osservare-a-strati"), trace.NoOpTracer()


def tracer(n: int):
    """Il tracer dello strato n: vero da quello strato in su, muto sotto. Impalcatura della demo, non strumentazione."""
    return _vero if STRATO >= n else _spento


MODEL = "claude-haiku-5-5"
LISTINO = (0.10, 0.01, 0.50)  # USD per milione: ingresso, letto dalla cache, uscita (ragionamento compreso); letto il 23/10/2026
MAX_GIRI = 6

DOMANDA = ("Ciao, sono Giulia Rossi (giulia.rossi@example.com). "
           "A che ora è il workshop Kubernetes da zero?")
PROGRAMMA = {"Kubernetes da zero": {"giorno": "oggi", "ora": "14:00", "sala": "B"},  # spostato stamattina
             "OpenTelemetry in un'ora": {"giorno": "oggi", "ora": "11:00", "sala": "A"},
             "Rust per chi scrive Go": {"giorno": "domani", "ora": "16:30", "sala": "C"}}
COPIA_DI_IERI = {**PROGRAMMA, "Kubernetes da zero": {"giorno": "oggi", "ora": "15:00", "sala": "B"}}
ETA_COPIA_ORE = 26
TIMEOUT_S = 2.0
FINESTRA_S = 120

CERCA = ("Sei l'assistente di DevFest Immaginario 2026. Per gli orari usa sempre lo strumento "
         "leggi_programma. Rispondi in una riga con giorno, ora e sala.")
VALIDA = ("Controlli le risposte dell'assistente di DevFest Immaginario 2026 prima che arrivino "
          "all'utente. Ricevi la domanda e la risposta. Verifica che l'orario sia valido, che la sala "
          "esista (le sale sono A, B e C) e che la risposta sia pertinente alla domanda. Se va tutto "
          "bene, restituisci la risposta com'è aggiungendo in fondo «Verificato.». Altrimenti spiega "
          "cosa non va.")
SCHEMA = {"name": "leggi_programma",
          "description": "Legge dal servizio del programma giorno, ora e sala di una sessione dell'evento.",
          "input_schema": {"type": "object", "required": ["sessione"],
                           "properties": {"sessione": {"type": "string", "description": "titolo della sessione"}}}}
PENSIERO = {"type": "adaptive", "display": "summarized"}  # il riassunto del ragionamento torna solo se lo chiedi


def servizio_programma(sessione: str, guasto: bool):
    if guasto:
        time.sleep(TIMEOUT_S)
        raise TimeoutError(f"il servizio del programma non ha risposto entro {TIMEOUT_S:g} secondi")
    time.sleep(0.3)
    return PROGRAMMA[sessione]


def leggi_programma(sessione: str, stato: dict) -> dict:
    titolo = next((t for t in PROGRAMMA if t.lower() in sessione.lower() or sessione.lower() in t.lower()), None)
    if titolo is None:
        return {"errore": "sessione non trovata", "sessioni": list(PROGRAMMA)}
    if time.monotonic() < stato["aperto_fino"]:
        with tracer(4).start_as_current_span("cache.read") as span:  # s4
            span.set_attributes({"cache.hit": True, "cache.age_hours": ETA_COPIA_ORE,  # s4
                                 "cache.reason": "interruttore aperto dopo un timeout del servizio"})  # s4
            return COPIA_DI_IERI[titolo]  # l'eta' non arriva al modello
    try:
        return servizio_programma(titolo, stato["guasto"])
    except TimeoutError:
        stato["aperto_fino"] = time.monotonic() + FINESTRA_S
        raise


def esegui_strumento(id_chiamata: str, argomenti: dict, stato: dict) -> tuple[str, bool]:
    with tracer(3).start_as_current_span("execute_tool leggi_programma") as span:  # s3
        span.set_attributes({"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "leggi_programma",  # s3
                             "gen_ai.tool.type": "function", "gen_ai.tool.call.id": id_chiamata,  # s3
                             "gen_ai.tool.call.arguments": json.dumps(argomenti, ensure_ascii=False)})  # s3
        try:
            risultato, errore = json.dumps(leggi_programma(argomenti.get("sessione", ""), stato), ensure_ascii=False), False
        except TimeoutError as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))  # s3
            span.set_attribute("error.type", "timeout")  # s3
            risultato, errore = f"Errore: {e}.", True  # l'errore torna al modello: se riprovare lo decide lui
        span.set_attribute("gen_ai.tool.call.result", risultato)  # s3
        return risultato, errore


def ciclo(client, istruzioni: str, richiesta: str, stato: dict, strumenti: bool):
    messaggi = [{"role": "user", "content": richiesta}]
    extra = {"tools": [SCHEMA]} if strumenti else {}
    for _ in range(MAX_GIRI):
        r = client.messages.create(model=MODEL, max_tokens=4096, system=istruzioni, messages=messaggi,
                                   thinking=PENSIERO, **extra)
        stato["fattura"].append(r.usage)  # s0  quello che il provider conta e fattura
        chiamate = [b for b in r.content if b.type == "tool_use"]
        if not chiamate:
            return "".join(b.text for b in r.content if b.type == "text")
        messaggi.append({"role": "assistant", "content": r.content})
        risultati = []
        for c in chiamate:
            risultato, errore = esegui_strumento(c.id, c.input, stato)
            risultati.append({"type": "tool_result", "tool_use_id": c.id, "content": risultato, "is_error": errore})
        messaggi.append({"role": "user", "content": risultati})
    raise RuntimeError(f"oltre {MAX_GIRI} giri")


def ciclo_runner(client, istruzioni: str, richiesta: str, stato: dict, strumenti: bool):
    """Variante dello strato 1: il ciclo lo fa il tool runner dell'SDK, che apre da se' invoke_agent ed execute_tool."""
    @anthropic.beta_tool(name="leggi_programma", description=SCHEMA["description"])
    def strumento(sessione: str) -> str:
        """Legge giorno, ora e sala di una sessione.

        Args:
            sessione: titolo della sessione
        """
        try:
            return json.dumps(leggi_programma(sessione, stato), ensure_ascii=False)
        except TimeoutError as e:
            raise anthropic.lib.tools.ToolError(f"Errore: {e}.") from e

    runner = client.beta.messages.tool_runner(model=MODEL, max_tokens=4096, system=istruzioni, thinking=PENSIERO,
                                              messages=[{"role": "user", "content": richiesta}],
                                              tools=[strumento] if strumenti else [], max_iterations=MAX_GIRI)
    ultimo = None
    for ultimo in runner:
        stato["fattura"].append(ultimo.usage)  # s0
    return "".join(b.text for b in ultimo.content if b.type == "text")


def agente(client, nome: str, istruzioni: str, richiesta: str, stato: dict, strumenti: bool) -> str:
    with tracer(2).start_as_current_span(f"invoke_agent {nome}") as span:  # s2
        span.set_attributes({"gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": nome,  # s2
                             "gen_ai.request.model": MODEL})  # s2
        giro = ciclo_runner if stato["runner"] else ciclo
        return giro(client, istruzioni, richiesta, stato, strumenti)


def cliente(**prova):
    if STRATO == 0:
        return anthropic.Anthropic(open_telemetry=False, **prova)
    modo = "content" if STRATO >= 5 else "metadata_only"  # s5
    return anthropic.Anthropic(open_telemetry={"tracer_provider": provider,  # s1
                                               "traces": {"content_mode": modo}}, **prova)  # s1


ID_ACCOUNT = ("anthropic.organization.id", "anthropic.workspace.id", "anthropic.request.id")


def in_dict(s) -> dict:
    attributi = {k: list(v) if isinstance(v, tuple) else v for k, v in s.attributes.items()}
    for k in ID_ACCOUNT:  # gli id dell'account non finiscono ne' a schermo ne' nelle registrazioni
        if k in attributi:
            attributi[k] = "oscurato"
    return {"nome": s.name, "id": format(s.context.span_id, "016x"),
            "padre": format(s.parent.span_id, "016x") if s.parent else None,
            "trace": format(s.context.trace_id, "032x"),
            "inizio": s.start_time / 1e9, "fine": s.end_time / 1e9,
            "errore": s.status.status_code == StatusCode.ERROR, "attributi": attributi}


def esegui(guasto: bool, runner: bool, cartella: Path, client=None) -> dict:
    memoria.clear()
    client = client or cliente()
    stato = {"aperto_fino": 0.0, "guasto": guasto, "runner": runner, "fattura": []}
    inizio = time.monotonic()  # s0
    with tracer(2).start_as_current_span("invoke_workflow assistente-evento") as span:  # s2
        span.set_attribute("gen_ai.operation.name", "invoke_workflow")  # s2
        span.set_attribute("gen_ai.workflow.name", "assistente-evento")  # s2
        bozza = agente(client, "cerca", CERCA, DOMANDA, stato, strumenti=True)
        risposta = agente(client, "valida", VALIDA, f"Domanda: {DOMANDA}\nRisposta dell'assistente: {bozza}",
                          stato, strumenti=False)
    secondi = time.monotonic() - inizio  # s0
    ora = dt.datetime.now()
    u = stato["fattura"]
    reg = {"strato": STRATO, "variante": "runner" if runner else None, "registrata": ora.isoformat(timespec="seconds"),
           "modo": "guasto" if guasto else "sana", "modello": MODEL, "domanda": DOMANDA, "risposta": risposta,
           "log": f"{ora:%H:%M:%S} INFO POST /chiedi 200 in {secondi:.1f} s",  # s0
           "fattura": {"chiamate": len(u), "in": sum(x.input_tokens for x in u),  # s0
                       "cache": sum(x.cache_read_input_tokens or 0 for x in u),
                       "out": sum(x.output_tokens for x in u)},
           "secondi": secondi, "span": [in_dict(s) for s in memoria.get_finished_spans()]}
    cartella.mkdir(parents=True, exist_ok=True)
    (cartella / f"{ora:%Y%m%d-%H%M%S}-{reg['modo']}.json").write_text(json.dumps(reg, ensure_ascii=False, indent=1))
    return reg


# --- stampa: la stessa per le run dal vivo e per quelle registrate, e mostra solo cio' che c'e' ---

COLORI = {"rosso": 31, "verde": 32, "giallo": 33, "ciano": 36, "grigio": 90, "inverso": 7}
EMAIL = re.compile(r"[\w.]+@[\w.]+\.\w+")


def c(colore: str, testo: str) -> str:
    return f"\033[{COLORI[colore]}m{testo}\033[0m"


def costo(ingresso: int, cache: int, uscita: int) -> float:
    p_in, p_cache, p_out = LISTINO
    return ((ingresso - cache) * p_in + cache * p_cache + uscita * p_out) / 1e6


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
    if s["nome"] == "cache.read" or attr(s, "gen_ai.operation.name") == "execute_tool":
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
                print(c("grigio", f"  {argomenti} -> {risultato}"))
        elif s["nome"] == "cache.read":
            print(c("giallo", f"{'  cache.read':<22} {'copia':<11}"))
            print(c("grigio", f"  età {attr(s, 'cache.age_hours')} ore · {attr(s, 'cache.reason')}"))
    print(f"{'totale dagli span':<22} {'':<11} {'':>20} {totale:>10.6f}")


def contenuto(span):
    """Strato 5: cosa ha pensato ogni agente, dal riassunto del ragionamento negli span."""
    per_id = {s["id"]: s for s in span}
    for s, _ in in_ordine(span):
        for messaggio in json.loads(attr(s, "gen_ai.output.messages") or "[]"):
            for parte in messaggio.get("parts", []):
                if parte.get("type") == "reasoning":
                    print(c("giallo", f"pensiero di {agente_di(s, per_id)}: ") + " ".join(parte.get("content", "").split()))


def con_email(span) -> int:
    return sum(1 for s in span for v in s["attributi"].values() if isinstance(v, str) and EMAIL.search(v))


def mostra(reg: dict, registrata: bool = False):
    span = reg["span"]
    titolo = f"strato {reg['strato']} · {TITOLI[reg['strato']]}" + (" · tool runner" if reg.get("variante") else "")
    if registrata:
        print(c("inverso", f" REGISTRATA il {reg['registrata'].replace('T', ' alle ')} · {titolo} · {reg['modo']} "))
    else:
        print(c("inverso", f" {titolo} · {reg['modo']} "))
    print(f"\n{c('grigio', 'utente:')} {reg['domanda']}\n{c('verde', 'assistente:')} {reg['risposta']}\n")
    f = reg["fattura"]
    print(c("grigio", "log:     ") + reg["log"])
    print(c("grigio", "fattura: ") + f"{f['chiamate']} chiamate · {f['in']} token in · {f['out']} out · "
          f"$ {costo(f['in'], f['cache'], f['out']):.6f}")
    if not span:
        return
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
            "sbagliata": "15:00" in risposta, "verificato": risposta.rstrip().endswith("Verificato."),
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
        gruppi.setdefault((r["strato"], r.get("variante") or "", r["modo"]), []).append(e)
    print(f"{'strato':>6} {'variante':8} {'modo':6} {'n':>3} {'trace':>5} {'span':>4} {'attr':>4} {'chiam.':>6} "
          f"{'15:00':>5} {'verif.':>6} {'email':>5} {'sec med':>7} {'token med':>9} {'$ med':>9}")
    for (strato, variante, modo), ee in sorted(gruppi.items()):
        conta = lambda k: sum(e[k] for e in ee)
        med = lambda k: statistics.median(e[k] for e in ee)
        print(f"{strato:>6} {variante:8} {modo:6} {len(ee):>3} {med('tracce'):>5.0f} {med('span'):>4.0f} "
              f"{med('attributi'):>4.0f} {med('chiamate'):>6.0f} {conta('sbagliata'):>5} {conta('verificato'):>6} "
              f"{med('email'):>5.0f} {med('secondi'):>7.1f} {med('token'):>9.0f} {med('costo'):>9.6f}")
    print(f"\nspeso in tutto, dalle registrazioni: $ {speso:.4f}")


def righe():
    """Le righe di codice di ogni strato, contate dai marcatori sN dopo il cancelletto."""
    testo = Path(__file__).read_text().splitlines()
    for n in range(6):
        marcate = [r for r in testo if re.search(rf"#\s*s{n}\b", r) and not r.lstrip().startswith("#")]
        print(f"strato {n} · {TITOLI[n]:<28} {len(marcate):>3} righe")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--strato", type=int, choices=range(6), default=0)
    p.add_argument("--guasto", action="store_true")
    p.add_argument("--runner", action="store_true", help="solo con --strato 1: il ciclo lo fa il tool runner dell'SDK")
    p.add_argument("--banco", type=int, default=0)
    p.add_argument("--replay")
    p.add_argument("--riepilogo", action="store_true")
    p.add_argument("--righe", action="store_true")
    a = p.parse_args()
    if a.righe:
        righe()
    elif a.riepilogo:
        riepilogo(QUI / "registrazioni")
    elif a.replay:
        mostra(json.loads(Path(a.replay).read_text()), registrata=True)
    else:
        if a.runner and a.strato != 1:
            raise SystemExit("--runner si confronta con lo strato 1: usalo con --strato 1")
        STRATO = a.strato
        cartella = QUI / "registrazioni" / (f"strato-{a.strato}" + ("-runner" if a.runner else ""))
        if a.banco:
            banco([esegui(a.guasto, a.runner, cartella) for _ in range(a.banco)])
        else:
            mostra(esegui(a.guasto, a.runner, cartella))
