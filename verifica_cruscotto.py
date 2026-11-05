"""Esegue su Tempo le query del cruscotto e confronta ogni numero con segnali.py. Uso: python verifica_cruscotto.py CARTELLA ...

Le query si leggono da cruscotto/grafana/segnali.json, per refId: cosi' si verifica il cruscotto che si mostra,
non una sua copia. Serve lo stack acceso (docker compose -f cruscotto/compose.yaml up -d) e i dati di tempo.py.
"""
import json
import statistics
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import segnali as sg

TEMPO = "http://localhost:3210"
CRUSCOTTO = Path(__file__).parent / "cruscotto" / "grafana" / "segnali.json"


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


def dal_cruscotto(query: dict[str, str], cartella: str, modo: str) -> dict:
    """I refId che il cruscotto deve avere: richieste, forme, approvati, verdetti, costo, quota, pagine.
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
            "pagine": (len(pagine), statistics.median(pagine) if pagine else None, max(pagine, default=None))}


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
            "pagine": (len(pagine), statistics.median(pagine), max(pagine))}


if __name__ == "__main__":
    query, sbagliati = query_del_cruscotto(), 0
    for cartella in map(Path, sys.argv[1:]):
        regs = [json.loads(f.read_text()) for f in sorted(cartella.glob("*.json"))]
        for modo in ("guasto", "sana"):
            if not (mm := [r for r in regs if r["modo"] == modo]):
                continue
            atteso, visto = da_segnali(mm), dal_cruscotto(query, cartella.name, modo)
            for k in atteso:
                ok = atteso[k] == visto[k]
                sbagliati += not ok
                print(f"{cartella.name:<28} {modo:<6} {k:<10} {'uguale' if ok else 'DIVERSO'}  segnali {atteso[k]}"
                      + ("" if ok else f"  cruscotto {visto[k]}"))
    sys.exit(1 if sbagliati else 0)
