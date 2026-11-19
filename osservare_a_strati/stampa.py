"""La vista a terminale: la stessa per le run dal vivo e per quelle registrate, e mostra solo cio' che c'e'."""
import datetime as dt
import json

from .analisi.span import agente_di, attr, in_ordine, per_trace, token
from .impostazioni import TITOLI
from .modello import costo
from .osservabilita.log import logfmt
from .osservabilita.tracce import EMAIL

COLORI = {"rosso": 31, "verde": 32, "giallo": 33, "ciano": 36, "grigio": 90, "inverso": 7}


def c(colore: str, testo: str) -> str:
    return f"\033[{COLORI[colore]}m{testo}\033[0m"


def colore(s) -> str:
    if s["errore"]:
        return "rosso"
    if attr(s, "gen_ai.operation.name") == "execute_tool":
        return "giallo"
    return "verde" if token(s) else "ciano"


def ms(s) -> str:
    return f"{(s['fine'] - s['inizio']) * 1000:,.0f} ms".replace(",", ".")


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
