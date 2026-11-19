"""Lunedi', in produzione: cinque segnali da cruscotto, calcolati solo dagli span delle registrazioni.

Uso: python segnali.py [CARTELLA ...]   (senza argomenti, tutte le cartelle in registrazioni/)
"""
import collections
import statistics

from ..modello import costo
from .span import grafo, pagine_avvisi, quota_avvisi, token, verdetti

# lo strato da cui ogni segnale si puo' misurare: sotto, gli span che servono non esistono
# (gli archi fra agenti ci sono dallo strato 2, gli strumenti di dati dal 3, i loro attributi dal 4)
MINIMO = {"forma": 2, "costo": 1, "quota_avvisi": 2, "pagine": 4, "approva": 3}


def p95(costi: list[float]) -> float:
    """Come il calcolo p95 di Grafana: il valore ordinato di posto round((n-1)*0.95), senza interpolare."""
    return sorted(costi)[round((len(costi) - 1) * 0.95)]


def segnali(r: dict) -> dict:
    span, strato = r["span"], r["strato"]
    se = lambda segnale, valore: valore() if strato >= MINIMO[segnale] else None
    return {
        "forma": se("forma", lambda: " ".join(grafo(span))),
        "costo": se("costo", lambda: sum(costo(t["in"], t["cache"], t["out"]) for x in span if (t := token(x)))),
        "quota_avvisi": se("quota_avvisi", lambda: quota_avvisi(span)),
        "pagine": se("pagine", lambda: pagine_avvisi(span)),
        "verdetti": se("approva", lambda: verdetti(span)),
    }


def riassunto(r: dict) -> dict:
    """I fatti per richiesta da scrivere sullo span radice: TraceQL conta span, non trace.
    Attributi richiesta.* (oltre a correzione e versione_prompt, dichiarati in strati.py): forma, costo_microusd,
    quota_avvisi_pct, pagine_avvisi, valida_approva (verdetti che approvano), valida_verdetti (tutti i verdetti)."""
    g, fuori = segnali(r), {}
    if g["forma"] is not None:
        fuori["richiesta.forma"] = g["forma"]
    if g["costo"] is not None:
        fuori["richiesta.costo_microusd"] = round(g["costo"] * 1e6)
    if g["quota_avvisi"] is not None:
        fuori["richiesta.quota_avvisi_pct"] = round(g["quota_avvisi"] * 100)
    if g["pagine"] is not None:
        fuori["richiesta.pagine_avvisi"] = g["pagine"]
    if g["verdetti"] is not None:  # per il confronto fra versioni: a quante richieste valida ha detto di si
        fuori["richiesta.valida_approva"] = sum(g["verdetti"])
        fuori["richiesta.valida_verdetti"] = len(g["verdetti"])
    return fuori


def cruscotto(regs: list[dict]) -> dict:
    gg = [segnali(r) for r in regs]
    tutti = lambda k: all(g[k] is not None for g in gg)
    costi = [g["costo"] for g in gg]
    quote = [g["quota_avvisi"] for g in gg if g["quota_avvisi"] is not None]
    pagine = [g["pagine"] for g in gg]
    return {
        "n": len(gg),
        "forme": collections.Counter(g["forma"] for g in gg) if tutti("forma") else None,
        "approva": (sum(sum(g["verdetti"]) for g in gg), sum(len(g["verdetti"]) for g in gg)) if tutti("verdetti") else None,
        "costo": {"mediana": statistics.median(costi), "p95": p95(costi)} if tutti("costo") else None,
        "quota_avvisi": {"mediana": statistics.median(quote), "p95": p95(quote)} if quote and tutti("quota_avvisi") else None,
        "pagine": {"mediana": statistics.median(pagine), "massimo": max(pagine)} if tutti("pagine") else None,
    }


def stampa(titolo: str, c: dict):
    manca = lambda segnale: f"— serve lo strato {MINIMO[segnale]}"
    print(f"{titolo} · {c['n']} richieste")
    f = c["forme"]
    print(f"  {"forme dell'albero":<18} " + (manca("forma") if f is None else
                                               f"{len(f)} (la più frequente in {f.most_common(1)[0][1]} run)"))
    a = c["approva"]
    print(f"  {'valida approva':<18} " + (manca("approva") if a is None else f"{a[0]} su {a[1]} verdetti"))
    k = c["costo"]
    print(f"  {'costo a richiesta':<18} " + (manca("costo") if k is None else
                                               f"mediana $ {k['mediana']:.6f} · 95° percentile $ {k['p95']:.6f}"))
    q = c["quota_avvisi"]
    print(f"  {'quota di avvisi':<18} " + (manca("quota_avvisi") if q is None else
                                            f"mediana {q['mediana']:.0%} dei token · 95° percentile {q['p95']:.0%}"))
    p = c["pagine"]
    print(f"  {'pagine di avvisi':<18} " + (manca("pagine") if p is None else
                                            f"mediana {p['mediana']:.0f} · massimo {p['massimo']:.0f}"))
