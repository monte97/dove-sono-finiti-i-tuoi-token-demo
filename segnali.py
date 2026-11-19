"""Lunedi', in produzione: cinque segnali da cruscotto, calcolati solo dagli span delle registrazioni.

Uso: python segnali.py [CARTELLA ...]   (senza argomenti, tutte le cartelle in registrazioni/)
"""
from osservare_a_strati.analisi.segnali import MINIMO, cruscotto, p95, riassunto, segnali, stampa  # noqa: F401
from osservare_a_strati.osservabilita.riassunto import RiassuntoSullaRadice  # noqa: F401
from osservare_a_strati.registrazioni import RADICE

if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    cartelle = [Path(a) for a in sys.argv[1:]] or sorted(p for p in RADICE.iterdir() if p.is_dir())
    for cartella in cartelle:
        regs = [json.loads(f.read_text()) for f in sorted(cartella.glob("*.json"))]
        for modo in ("guasto", "sana"):
            if mm := [r for r in regs if r["modo"] == modo]:
                stampa(f"{cartella.name} · {modo}", cruscotto(mm))
                print()
