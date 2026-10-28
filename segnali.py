"""Lunedi', in produzione: cinque segnali da cruscotto, calcolati solo dagli span delle registrazioni.

Uso: python segnali.py [CARTELLA ...]   (senza argomenti, tutte le cartelle in registrazioni/)
"""
import collections
import statistics

from opentelemetry.sdk.trace import SpanProcessor

import strati as s

# lo strato da cui ogni segnale si puo' misurare: sotto, gli span che servono non esistono
# (gli archi fra agenti ci sono dallo strato 2, ma gli strumenti di dati solo dal 3)
MINIMO = {"ritenta": 3, "forma": 2, "approva": 3, "copia": 4, "costo": 1}


def p95(costi: list[float]) -> float:
    """Come il calcolo p95 di Grafana: il valore ordinato di posto round((n-1)*0.95), senza interpolare."""
    return sorted(costi)[round((len(costi) - 1) * 0.95)]


def segnali(r: dict) -> dict:
    span, strato = r["span"], r["strato"]
    se = lambda segnale, valore: valore() if strato >= MINIMO[segnale] else None
    archi_a_valida = [x for x in span if s.attr(x, "gen_ai.transfer.target.name") == "valida"
                      and s.attr(x, "gen_ai.tool.call.result") is not None]
    return {
        "chiamate": se("ritenta", lambda: collections.Counter(
            s.attr(x, "gen_ai.tool.name") for x in span if s.attr(x, "gen_ai.operation.name") == "execute_tool")),
        "forma": se("forma", lambda: " ".join(s.grafo(span))),
        "verdetti": se("approva", lambda: [s.approva(s.attr(x, "gen_ai.tool.call.result")) for x in archi_a_valida]),
        "copia": se("copia", lambda: any(x["nome"] == "cache.read" for x in span)),
        "costo": se("costo", lambda: sum(s.costo(t["in"], t["cache"], t["out"]) for x in span if (t := s.token(x)))),
    }


def riassunto(r: dict) -> dict:
    """I fatti per richiesta da scrivere sullo span radice: TraceQL conta span, non trace."""
    g, fuori = segnali(r), {}
    if g["forma"] is not None:
        fuori["richiesta.forma"] = g["forma"]
    if g["costo"] is not None:
        fuori["richiesta.costo_microusd"] = round(g["costo"] * 1e6)
    if g["chiamate"] is not None:
        fuori["richiesta.richiamati"] = " ".join(sorted(nome for nome, n in g["chiamate"].items() if n >= 2))
    if g["copia"] is not None:
        fuori["richiesta.copia_vecchia"] = g["copia"]
    return fuori


class RiassuntoSullaRadice(SpanProcessor):
    """In produzione: a ogni span che si chiude, il riassunto della richiesta si riscrive sulla radice ancora aperta."""

    def __init__(self, strato: int):
        self.strato, self.radici, self.chiusi = strato, {}, {}

    def on_start(self, span, parent_context=None):
        if span.parent is None or span.parent.is_remote:
            self.radici[span.context.trace_id] = span

    def on_end(self, span):
        tid = span.context.trace_id
        radice = self.radici.get(tid)
        if radice is not None and radice.context.span_id == span.context.span_id:  # la richiesta e' finita
            del self.radici[tid]
            self.chiusi.pop(tid, None)
            return
        if tid in self.radici:
            self.chiusi.setdefault(tid, []).append(s.in_dict(span))
            self.radici[tid].set_attributes(riassunto({"strato": self.strato, "span": self.chiusi[tid]}))


def cruscotto(regs: list[dict]) -> dict:
    gg = [segnali(r) for r in regs]
    tutti = lambda k: all(g[k] is not None for g in gg)
    ritenta = collections.Counter(nome for g in gg for nome, n in (g["chiamate"] or {}).items() if n >= 2)
    costi = [g["costo"] for g in gg]
    return {
        "n": len(gg),
        "ritenta": dict(ritenta) if tutti("chiamate") else None,
        "forme": collections.Counter(g["forma"] for g in gg) if tutti("forma") else None,
        "approva": (sum(sum(g["verdetti"]) for g in gg), sum(len(g["verdetti"]) for g in gg)) if tutti("verdetti") else None,
        "copia": sum(g["copia"] for g in gg) if tutti("copia") else None,
        "costo": {"mediana": statistics.median(costi), "p95": p95(costi)} if tutti("costo") else None,
    }


def stampa(titolo: str, c: dict):
    manca = lambda segnale: f"— serve lo strato {MINIMO[segnale]}"
    print(f"{titolo} · {c['n']} richieste")
    r = c["ritenta"]
    # «richiamati», non «ritentati»: conta le run in cui uno strumento e' chiamato almeno due volte, errore o no
    print(f"  {'richiamati':<18} " + (manca("ritenta") if r is None else " · ".join(
        f"{nome} in {n} run" for nome, n in sorted(r.items(), key=lambda kv: -kv[1])) or "nessuno"))
    f = c["forme"]
    print(f"  {"forme dell'albero":<18} " + (manca("forma") if f is None else
                                               f"{len(f)} (la più frequente in {f.most_common(1)[0][1]} run)"))
    a = c["approva"]
    print(f"  {'valida approva':<18} " + (manca("approva") if a is None else f"{a[0]} su {a[1]} verdetti"))
    print(f"  {'da copia vecchia':<18} " + (manca("copia") if c["copia"] is None else f"{c['copia']} run"))
    k = c["costo"]
    print(f"  {'costo a richiesta':<18} " + (manca("costo") if k is None else
                                               f"mediana $ {k['mediana']:.6f} · 95° percentile $ {k['p95']:.6f}"))


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    cartelle = [Path(a) for a in sys.argv[1:]] or sorted(p for p in (s.QUI / "registrazioni").iterdir() if p.is_dir())
    for cartella in cartelle:
        regs = [json.loads(f.read_text()) for f in sorted(cartella.glob("*.json"))]
        for modo in ("guasto", "sana"):
            if mm := [r for r in regs if r["modo"] == modo]:
                stampa(f"{cartella.name} · {modo}", cruscotto(mm))
                print()
