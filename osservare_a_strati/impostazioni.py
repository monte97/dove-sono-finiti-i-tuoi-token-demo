"""Le scelte di una run in un oggetto solo: strato, correzione, maschera, produzione, otlp."""
from contextlib import contextmanager
from dataclasses import dataclass, replace

TITOLI = {0: "oggi: un log e una fattura", 1: "le metriche e l'SDK", 2: "gli agenti", 3: "lo strumento",
          4: "i dati letti", 5: "il contenuto"}

# Le modalita' di correzione, come le dicono la registrazione e lo span radice.
NOMI_CORREZIONE = ("nessuna", "istruzioni", "filtro", "dialogo")


@dataclass(frozen=True)
class Impostazioni:
    strato: int = 0
    correzione: int = 0
    maschera: bool = False
    produzione: bool = False
    otlp: str | None = None


_attuali = Impostazioni()


def attuali() -> Impostazioni:
    """Le impostazioni della run in corso."""
    return _attuali


def imposta(i: Impostazioni) -> None:
    global _attuali
    _attuali = i


@contextmanager
def con(**campi):
    """Impostazioni diverse per il blocco, poi di nuovo quelle di prima."""
    global _attuali
    prima = _attuali
    _attuali = replace(prima, **campi)
    try:
        yield _attuali
    finally:
        _attuali = prima
