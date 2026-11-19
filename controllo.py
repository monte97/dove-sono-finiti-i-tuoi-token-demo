"""Il banco breve della settimana del talk: poche run per caso, confrontate con il banco di 30 run.

claude-haiku-5-5 e' un alias senza snapshot datato: dietro lo stesso nome il modello puo' cambiare. Questo
controllo rifa' poche run per ogni caso del discorso, in una cartella sua (registrazioni/ resta intatta), e
mette accanto i numeri che il talk usa. Controlla anche che l'SDK scriva ancora gli span come allo strato 1.

Uso:
  python controllo.py --stima                      # cosa verrebbe lanciato e quanto costa, senza chiamare l'API
  python controllo.py --run 10                     # 10 run per caso in controllo/AAAA-MM-GG/, poi il confronto
  python controllo.py --confronta controllo/2026-11-24   # solo il confronto, su run gia' fatte
"""
from osservare_a_strati.analisi.controllo import (  # noqa: F401
    BANCO, CASI, QUI, SDK, SOGLIE, confronta, costo, esegui, fuori_soglia, lancia, leggi, nuova, numeri, stima)

if __name__ == "__main__":
    import argparse
    from pathlib import Path

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
    if a.stima:
        stima(n)
        raise SystemExit
    lancia(n)
