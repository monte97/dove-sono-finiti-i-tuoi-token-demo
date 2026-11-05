"""Il banco breve della settimana del talk: poche run per caso, confrontate con il banco di 30 run.

claude-haiku-5-5 e' un alias senza snapshot datato: dietro lo stesso nome il modello puo' cambiare. Questo
controllo rifa' poche run per ogni caso del discorso, in una cartella sua (registrazioni/ resta intatta), e
mette accanto i numeri che il talk usa. Controlla anche che l'SDK scriva ancora gli span come allo strato 1.

Uso:
  python controllo.py --stima                      # cosa verrebbe lanciato e quanto costa, senza chiamare l'API
  python controllo.py --run 10                     # 10 run per caso in controllo/AAAA-MM-GG/, poi il confronto
  python controllo.py --confronta controllo/2026-11-24   # solo il confronto, su run gia' fatte
"""
import argparse
import collections
import datetime as dt
import json
import statistics
from pathlib import Path

import strati as s

QUI = Path(__file__).parent
BANCO = QUI / "registrazioni"

# (cartella, correzione, guasto): i casi che il discorso usa
CASI = [
    ("strato-5", 0, True), ("strato-5", 0, False),
    ("strato-5-correzione", 1, True), ("strato-5-correzione-completa", 2, True),
    ("strato-5-correzione-dialogo", 3, True),
]
SDK = ("strato-1", 0, True)  # due run bastano per vedere come l'SDK scrive gli span


def esegui(cartella: Path, correzione: int, guasto: bool, strato: int) -> dict:
    s.STRATO, s.CORREZIONE, s.MASCHERA, s.PRODUZIONE, s.OTLP = strato, correzione, False, False, None
    return s.esegui(guasto, cartella)


def leggi(cartella: Path, modo: str) -> list[dict]:
    regs = [json.loads(f.read_text()) for f in sorted(cartella.glob("*.json"))] if cartella.is_dir() else []
    return [r for r in regs if r["modo"] == modo and nuova(r)]


def nuova(r: dict) -> bool:
    """Le registrazioni del sistema vecchio (campo dominio, niente log_otel) non si leggono con le misure nuove."""
    return "dominio" not in r and "log_otel" in r


def costo(r: dict) -> float:
    f = r["fattura"]
    return s.costo(f["in"], f["cache"], f["out"])


def numeri(regs: list[dict]) -> dict:
    mm = [s.misura(r) for r in regs]
    forme = collections.Counter(m["grafo"] for m in mm)
    quota = lambda m: m["quota_avvisi"]
    return {
        "n": len(regs),
        "giuste": sum(m["esito"] == "giusta" for m in mm) / len(mm),
        "avvisate": sum(m["esito"] == "avvisata" for m in mm) / len(mm),
        "sbagliate": sum(m["esito"] == "sbagliata" for m in mm) / len(mm),
        "nello stesso giro": sum(m["stesso_giro"] for m in mm) / len(mm),
        "avvisi dopo la sala": sum(m["avvisi_dopo_sala"] for m in mm) / len(mm),
        "avvisi lo riporta": sum(m["avvisi_riporta"] for m in mm) / len(mm),
        "pagine avvisi mediana": statistics.median(m["pagine_avvisi"] for m in mm),
        "quota avvisi mediana": statistics.median(map(quota, mm)),
        "valida approva": sum(m["valida_approva"] > 0 for m in mm) / len(mm),
        "sale da due": sum(bool(m["sale_da_due"]) for m in mm) / len(mm),
        "valida ricontrolla": sum(bool(m["valida_avvisi"] or m["valida_programma"]) for m in mm) / len(mm),
        "avvisi chiede a prog.": sum(bool(m["avvisi_chiede_programma"]) for m in mm) / len(mm),
        "dialogo e riporta": sum(bool(m["avvisi_poi_riporta"]) for m in mm) / len(mm),
        "guardia scattata": sum(bool(m["cicli"]) for m in mm) / len(mm),
        "albero più comune": forme.most_common(1)[0][1] / len(mm),
        "forme dell'albero": len(forme),
        "costo mediana $": statistics.median(map(costo, regs)),
        "secondi mediana": statistics.median(r["secondi"] for r in regs),
    }


def confronta(cartella: Path):
    print(f"{'caso':<36} {'numero':<20} {'banco':>11} {'controllo':>11}")
    for nome, _, guasto in CASI:
        modo = "guasto" if guasto else "sana"
        b, k = leggi(BANCO / nome, modo), leggi(cartella / nome, modo)
        if not k:
            print(f"{nome + ' ' + modo:<36} nessuna run di controllo")
            continue
        if not b:
            print(f"{nome + ' ' + modo:<36} banco da rigenerare: nessuna registrazione nel formato nuovo")
            continue
        nb, nk = numeri(b), numeri(k)
        for chiave in nb:
            vb, vk = nb[chiave], nk[chiave]
            if chiave == "pagine avvisi mediana":
                vb, vk = f"{vb:.0f}", f"{vk:.0f}"
            elif isinstance(vb, float) and chiave not in ("costo mediana $", "secondi mediana"):
                vb, vk = f"{vb:.0%}", f"{vk:.0%}"
            elif chiave == "costo mediana $":
                vb, vk = f"{vb:.6f}", f"{vk:.6f}"
            elif chiave == "secondi mediana":
                vb, vk = f"{vb:.1f}", f"{vk:.1f}"
            print(f"{nome + ' ' + modo:<36} {chiave:<20} {vb:>11} {vk:>11}")
        print()
    sdk = leggi(cartella / SDK[0], "guasto")
    if sdk:
        span = [x for r in sdk for x in r["span"]]
        nomi = collections.Counter(x["nome"] for x in span)
        attributi = set().union(*(x["attributi"] for x in span))
        print("SDK, strato 1:", dict(nomi))
        for a in ("gen_ai.operation.name", "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens",
                  "gen_ai.usage.reasoning.output_tokens", "anthropic.message.stop_reason", "gen_ai.response.model"):
            print(f"  {a:<40} {"c'è" if a in attributi else 'MANCA'}")
        print("  modello che risponde:", {s.attr(x, "gen_ai.response.model") for x in span} - {None})
    print("\nIl banco ha 30 run per caso, il controllo poche: una differenza di una run su dieci e' rumore. "
          "Contano i cambi di verso (avvisi lo riporta sempre -> a volte, valida che ricontrolla o avvisi che chiede a programma dove prima non succedeva, valida approva -> obietta, i rami non piu' nello stesso giro) e i nomi degli span.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--stima", action="store_true")
    g.add_argument("--run", type=int, metavar="N")
    g.add_argument("--confronta", type=Path, metavar="CARTELLA")
    a = p.parse_args()
    if a.confronta:
        confronta(a.confronta)
        raise SystemExit
    n = a.run or 10
    casi = [(c, 5) for c in CASI] + [(SDK, 1)]
    quante = n * len(CASI) + 2
    costi = [costo(r) for c, _ in casi for r in leggi(BANCO / c[0], "guasto" if c[2] else "sana")]
    if not costi:
        raise SystemExit("banco da rigenerare: nessuna registrazione nel formato nuovo, la stima del costo non si puo' fare")
    med = statistics.median(costi)
    print(f"{quante} run ({n} per caso su {len(CASI)} casi, piu' 2 allo strato 1): circa $ {quante * med:.2f} "
          f"e {quante * 15 / 60:.0f} minuti, in sequenza")
    if a.stima:
        raise SystemExit
    cartella = QUI / "controllo" / f"{dt.date.today():%Y-%m-%d}"
    for (nome, correzione, guasto), strato in casi:
        for _ in range(n if strato == 5 else 2):
            esegui(cartella / nome, correzione, guasto, strato)
        print("fatto:", nome, "guasto" if guasto else "sana")
    confronta(cartella)
