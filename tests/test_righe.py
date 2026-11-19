"""Test delle righe per strato: il codice estratto per le slide resta quello del riferimento."""
from pathlib import Path

import pytest

from osservare_a_strati.righe import codice

RIFERIMENTO = Path(__file__).resolve().parents[2] / "riordino-riferimento" / "prima"


@pytest.fixture(scope="module")
def riferimento() -> Path:
    if not RIFERIMENTO.is_dir():
        pytest.skip("riferimento del riordino non disponibile")
    return RIFERIMENTO


def _blocchi(testo: str) -> list[str]:
    return sorted(testo.split("\n...\n"))


def test_codice_strato_0_uguale_al_riferimento(riferimento: Path):
    assert codice(0) == (riferimento / "codice-0.txt").read_text().rstrip("\n")


def test_codice_strato_1_uguale_al_riferimento(riferimento: Path):
    # L'ordine dei blocchi segue ORDINE (i file, non le sezioni originali): qui metriche e tracce si scambiano.
    assert _blocchi(codice(1)) == _blocchi((riferimento / "codice-1.txt").read_text().rstrip("\n"))


def test_codice_strato_2_uguale_al_riferimento(riferimento: Path):
    assert codice(2) == (riferimento / "codice-2.txt").read_text().rstrip("\n")
