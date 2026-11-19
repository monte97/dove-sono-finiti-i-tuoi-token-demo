"""Conteggio dei marcatori # sN su tutto il pacchetto e estrazione delle righe per le slide."""
import re
import textwrap
from pathlib import Path

from .impostazioni import TITOLI

RADICE = Path(__file__).resolve().parent

# I file con marcatori, nell'ordine in cui le loro sezioni comparivano in strati.py.
ORDINE: tuple[str, ...] = (
    "osservabilita/log.py",
    "osservabilita/tracce.py",
    "osservabilita/metriche.py",
    "agenti/strumenti.py",
    "agenti/ciclo.py",
    "osservabilita/client.py",
    "esecuzione.py",
)


def _righe_di(percorso: str) -> list[str]:
    return (RADICE / percorso).read_text().splitlines()


def righe():
    """Le righe di codice di ogni strato, contate dai marcatori sN dopo il cancelletto."""
    testo = [r for percorso in ORDINE for r in _righe_di(percorso)]
    for n in range(6):
        marcate = [r for r in testo if re.search(rf"#\s*s{n}\b", r) and not r.lstrip().startswith("#")]
        print(f"strato {n} · {TITOLI[n]:<28} {len(marcate):>3} righe")


def codice(n: int) -> str:
    """Le righe dello strato n come si scriverebbero senza l'impalcatura della demo, per le slide."""
    fuori = []
    for percorso in ORDINE:
        testo = _righe_di(percorso)
        marcate = [i for i, r in enumerate(testo) if re.search(rf"#\s*s{n}\b", r) and not r.lstrip().startswith("#")]
        blocchi = []
        for i in marcate:
            if blocchi and not "".join(testo[blocchi[-1][-1] + 1:i]).strip():  # in mezzo solo righe vuote
                blocchi[-1].extend(range(blocchi[-1][-1] + 1, i + 1))
            else:
                blocchi.append([i])
        for blocco in blocchi:
            righe_, rientro_if = [], None
            for i in blocco:
                r = (re.sub(rf"\s+#\s*s{n}\b.*$", "", testo[i]).replace(f"tracer({n}).", "tracer.")
                     .replace(", **prova)", ")").replace("metriche.", "").replace("tracce.", "")
                     .replace("attuali().correzione", "CORREZIONE"))
                if re.match(rf"\s*if attuali\(\)\.strato >= {n}:", r):
                    rientro_if = len(r) - len(r.lstrip())
                    continue
                if rientro_if is not None and len(r) - len(r.lstrip()) > rientro_if:
                    r = r[4:]
                righe_.append(r)
            fuori.append(textwrap.dedent("\n".join(righe_)))
    return "\n...\n".join(fuori)
