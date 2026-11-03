"""Il banco breve della settimana del talk: poche run per caso, confrontate con il banco del 3/11.

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

import segnali as sg
import strati as s

QUI = Path(__file__).parent
BANCO = QUI / "registrazioni"

# (cartella, dominio, correzione, guasto): i casi che il discorso usa
CASI = [
    ("strato-5", "orario", 0, True), ("strato-5", "orario", 0, False),
    ("strato-5-freeze", "freeze", 0, True), ("strato-5-freeze", "freeze", 0, False),
    ("strato-5-correzione", "orario", 1, True), ("strato-5-correzione-completa", "orario", 2, True),
]
SDK = ("strato-1", "orario", 0, True)  # due run bastano per vedere come l'SDK scrive gli span


def esegui(cartella: Path, dominio: str, correzione: int, guasto: bool, strato: int) -> dict:
    s.STRATO, s.DOMINIO, s.CORREZIONE, s.MASCHERA, s.PRODUZIONE, s.OTLP = strato, s.DOMINI[dominio], correzione, False, False, None
    return s.esegui(guasto, cartella)


def leggi(cartella: Path, modo: str) -> list[dict]:
    regs = [json.loads(f.read_text()) for f in sorted(cartella.glob("*.json"))] if cartella.is_dir() else []
    return [r for r in regs if r["modo"] == modo]


def costo(r: dict) -> float:
    f = r["fattura"]
    return s.costo(f["in"], f["cache"], f["out"])


def numeri(regs: list[dict], dominio: str) -> dict:
    s.DOMINIO = s.DOMINI[dominio]
    mm = [s.misura(r) for r in regs]
    forme = collections.Counter(m["grafo"] for m in mm)
    c = sg.cruscotto(regs)
    return {
        "n": len(regs),
        "sbagliate": sum(m["esito"] == "sbagliata" for m in mm) / len(mm),
        "riprovano": sum(m["riprove"] > 0 for m in mm) / len(mm),
        "valida approva": c["approva"][0] / c["approva"][1] if c["approva"][1] else 0.0,
        "avvisa l'utente": sum(m["avvisa"] for m in mm) / len(mm),
        "albero più comune": forme.most_common(1)[0][1] / len(mm),
        "forme dell'albero": len(forme),
        "costo mediana $": statistics.median(map(costo, regs)),
        "secondi mediana": statistics.median(r["secondi"] for r in regs),
    }


def confronta(cartella: Path):
    print(f"{'caso':<36} {'numero':<20} {'banco 3/11':>11} {'controllo':>11}")
    for nome, dominio, _, guasto in CASI:
        modo = "guasto" if guasto else "sana"
        b, k = leggi(BANCO / nome, modo), leggi(cartella / nome, modo)
        if not k:
            print(f"{nome + ' ' + modo:<36} nessuna run di controllo")
            continue
        nb, nk = numeri(b, dominio), numeri(k, dominio)
        for chiave in nb:
            vb, vk = nb[chiave], nk[chiave]
            if isinstance(vb, float) and chiave not in ("costo mediana $", "secondi mediana"):
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
          "Contano i cambi di verso (riprova sempre -> a volte, approva -> obietta) e i nomi degli span.")


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
    med = statistics.median(costo(r) for c, _ in casi for r in leggi(BANCO / c[0], "guasto" if c[3] else "sana"))
    print(f"{quante} run ({n} per caso su {len(CASI)} casi, piu' 2 allo strato 1): circa $ {quante * med:.2f} "
          f"e {quante * 15 / 60:.0f} minuti, in sequenza")
    if a.stima:
        raise SystemExit
    cartella = QUI / "controllo" / f"{dt.date.today():%Y-%m-%d}"
    for (nome, dominio, correzione, guasto), strato in casi:
        for _ in range(n if strato == 5 else 2):
            esegui(cartella / nome, dominio, correzione, guasto, strato)
        print("fatto:", nome, "guasto" if guasto else "sana")
    confronta(cartella)
