"""Esegue su Tempo le query del cruscotto e confronta ogni numero con segnali.py.

Le query si leggono da cruscotto/grafana/segnali.json, per refId: cosi' si verifica il cruscotto che si mostra,
non una sua copia. Serve lo stack acceso (docker compose -f cruscotto/compose.yaml up -d) e i dati di invio.
"""
import json
import statistics
import time
import urllib.parse
import urllib.request
from pathlib import Path

from ..analisi import segnali as sg
from . import invio as tempo

TEMPO = "http://localhost:3210"
RADICE = Path(__file__).resolve().parents[2]
CRUSCOTTO = RADICE / "cruscotto" / "grafana" / "segnali.json"


def query_del_cruscotto() -> dict[str, str]:
    pannelli = json.loads(CRUSCOTTO.read_text()).get("panels", [])
    return {t["refId"]: t["query"] for p in pannelli for t in p.get("targets", [])}


def chiedi(percorso: str, **parametri) -> dict:
    fine = int(time.time())
    parametri = {"start": fine - 3600, "end": fine, **parametri}
    with urllib.request.urlopen(f"{TEMPO}{percorso}?{urllib.parse.urlencode(parametri)}", timeout=30) as r:
        return json.load(r)


def serie(q: str) -> dict[str, float]:
    """Una metrica TraceQL: per serie, la somma dei campioni a passo 60 s (con passi larghi Tempo ne perde)."""
    d = chiedi("/api/metrics/query_range", q=q, step="60s")
    return {s.get("promLabels", ""): sum(x.get("value", 0) for x in s.get("samples", [])) for s in d.get("series", [])}


def valori(q: str, attributo: str) -> list[int]:
    d = chiedi("/api/search", q=q, limit=500, spss=1)
    return [int(next(iter(a["value"].values()))) for t in d.get("traces", []) for ss in t.get("spanSets", [])
            for x in ss.get("spans", []) for a in x.get("attributes", []) if a["key"] == attributo]


def righe_versioni(q: str) -> dict[str, dict]:
    """Il pannello «Versioni a confronto»: per ogni richiesta gli attributi richiesta.* della radice, raggruppati per
    richiesta.correzione come fa la trasformazione groupBy di Grafana."""
    d = chiedi("/api/search", q=q, limit=500, spss=1)
    gruppi = {}
    for t in d.get("traces", []):
        for ss in t.get("spanSets", []):
            for x in ss.get("spans", []):
                a = {k["key"]: next(iter(k["value"].values())) for k in x.get("attributes", []) if k["key"].startswith("richiesta.")}
                gruppi.setdefault(a["richiesta.correzione"], []).append(a)
    return {c: confronto([{k: v if k in ("richiesta.correzione", "richiesta.versione_prompt") else int(v) for k, v in a.items()}
                          for a in aa]) for c, aa in gruppi.items()}


def confronto(righe: list[dict]) -> dict:
    """Le colonne del pannello per una modalita' di correzione: richieste, hash, costo e quota mediani, valida approva su verdetti."""
    return {"richieste": len(righe), "prompt": righe[0]["richiesta.versione_prompt"],
            "costo": statistics.median(r["richiesta.costo_microusd"] for r in righe),
            "quota": statistics.median(r["richiesta.quota_avvisi_pct"] for r in righe),
            "approva": (sum(r["richiesta.valida_approva"] for r in righe), sum(r["richiesta.valida_verdetti"] for r in righe))}


def dal_cruscotto(query: dict[str, str], cartella: str, modo: str) -> dict:
    """I refId che il cruscotto deve avere: richieste, forme, approvati, verdetti, costo, quota, pagine, versioni.
    `cartella` e' un nome o, per piu' cartelle insieme, un'alternativa «(a|b)»: come la variabile multi-valore di Grafana.
    I valori per richiesta stanno sulla radice (richiesta.*), le forme sono una metrica per valore dell'attributo."""
    q = {k: v.replace("$cartella", cartella).replace("$modo", modo) for k, v in query.items()}
    tot = lambda k: round(sum(serie(q[k]).values()))
    forme = serie(q["forme"])
    costi = valori(q["costo"], "richiesta.costo_microusd")
    quote = valori(q["quota"], "richiesta.quota_avvisi_pct")
    pagine = valori(q["pagine"], "richiesta.pagine_avvisi")
    return {"richieste": tot("richieste"),
            "forme": (len(forme), round(max(forme.values(), default=0))),
            "approva": (tot("approvati"), tot("verdetti")),
            "costo": (len(costi), statistics.median(costi) if costi else None, sg.p95(costi) if costi else None),
            "quota": (len(quote), statistics.median(quote) if quote else None, sg.p95(quote) if quote else None),
            "pagine": (len(pagine), statistics.median(pagine) if pagine else None, max(pagine, default=None)),
            "versioni": righe_versioni(q["versioni"])}


def da_segnali(regs: list[dict]) -> dict:
    """Quello che il cruscotto deve mostrare, dai segnali: gli stessi arrotondamenti che riassunto() scrive sulla radice."""
    c = sg.cruscotto(regs)
    gg = [sg.segnali(r) for r in regs]
    costi = [round(g["costo"] * 1e6) for g in gg]
    quote = [round(g["quota_avvisi"] * 100) for g in gg]
    pagine = [g["pagine"] for g in gg]
    return {"richieste": c["n"], "forme": (len(c["forme"]), c["forme"].most_common(1)[0][1]), "approva": c["approva"],
            "costo": (len(costi), statistics.median(costi), sg.p95(costi)),
            "quota": (len(quote), statistics.median(quote), sg.p95(quote)),
            "pagine": (len(pagine), statistics.median(pagine), max(pagine)),
            "versioni": versioni_da_segnali(regs)}


def versioni_da_segnali(regs: list[dict]) -> dict:
    """Come il pannello delle versioni, dalle registrazioni: la modalita' e l'hash sono quelli che invio scrive sulla radice."""
    gruppi = {}
    for r in regs:
        v, g = tempo.versione_della_registrazione(r), sg.segnali(r)
        gruppi.setdefault(v["correzione"], []).append({
            "richiesta.versione_prompt": v["prompt"], "richiesta.costo_microusd": round(g["costo"] * 1e6),
            "richiesta.quota_avvisi_pct": round(g["quota_avvisi"] * 100),
            "richiesta.valida_approva": sum(g["verdetti"]), "richiesta.valida_verdetti": len(g["verdetti"])})
    return {c: confronto(rr) for c, rr in gruppi.items()}


def verifica(cartelle: list[Path]) -> int:
    """Confronta il cruscotto con i segnali: torna il numero di valori diversi (0 se tutto torna)."""
    query, sbagliati = query_del_cruscotto(), 0
    # ogni cartella da sola, e (se sono piu' d'una) tutte insieme: la variabile cartella del cruscotto e' multi-valore
    gruppi = [[c] for c in cartelle] + ([cartelle] if len(cartelle) > 1 else [])
    for gruppo in gruppi:
        nome = "+".join(c.name for c in gruppo)
        espressione = gruppo[0].name if len(gruppo) == 1 else "(" + "|".join(c.name for c in gruppo) + ")"
        for modo in ("guasto", "sana"):
            regs = [json.loads(f.read_text()) for c in gruppo for f in sorted(c.glob("*.json"))]
            if not (mm := [r for r in regs if r["modo"] == modo]):
                continue
            atteso, visto = da_segnali(mm), dal_cruscotto(query, espressione, modo)
            for k in atteso:
                ok = atteso[k] == visto[k]
                sbagliati += not ok
                print(f"{nome:<28} {modo:<6} {k:<10} {'uguale' if ok else 'DIVERSO'}  segnali {atteso[k]}"
                      + ("" if ok else f"  cruscotto {visto[k]}"))
    return 1 if sbagliati else 0
