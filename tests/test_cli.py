"""Test del comando unico `strati`: sottocomandi, controlli e messaggi di oggi."""
import re
from pathlib import Path

import pytest

from osservare_a_strati import cli, esecuzione
from osservare_a_strati.impostazioni import attuali, con

RIFERIMENTO = Path(__file__).resolve().parents[2] / "riordino-riferimento" / "prima" / "replay"


def _senza_ansi(testo):
    return re.sub(r"\033\[\d+m", "", testo)


def test_maschera_senza_strato_5_rifiutata():
    with pytest.raises(SystemExit) as errore:
        cli.main(["run", "--strato", "3", "--maschera"])
    assert str(errore.value) == "--maschera serve allo strato 5, dove il contenuto entra negli span"


def test_produzione_sotto_lo_strato_2_rifiutata():
    with pytest.raises(SystemExit) as errore:
        cli.main(["run", "--strato", "1", "--produzione"])
    assert str(errore.value) == "--produzione serve dallo strato 2, dove c'e' la radice della richiesta"


def test_correzione_implica_guasto(monkeypatch):
    visti = {}

    def finta(guasto, cartella, client=None):
        visti["guasto"] = guasto
        return {"span": [], "fattura": {"chiamate": 0, "in": 0, "cache": 0, "out": 0}, "risposta": ""}

    monkeypatch.setattr(esecuzione, "esegui", finta)
    monkeypatch.setattr(cli, "mostra", lambda reg: None)
    with con():
        cli.main(["run", "--strato", "5", "--correzione", "istruzioni"])
        assert visti["guasto"] is True
        assert attuali().correzione == 1


def test_replay_stampa_la_run_di_giulia(monkeypatch, capsys):
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    cli.main(["replay", "registrazioni/strato-5/20261105-202614-guasto.json"])
    uscita = capsys.readouterr().out
    assert _senza_ansi(uscita).startswith(" REGISTRATA il 2026-11-05 alle 20:26:14 · strato 5")
    assert "19 chiamate" in uscita
    riferimento = RIFERIMENTO / "strato-5" / "20261105-202614-guasto.txt"
    if riferimento.is_file():
        assert uscita.encode() == riferimento.read_bytes()


def test_replay_cli_uguale_al_riferimento(monkeypatch, capsys):
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    cartella_riferimento = RIFERIMENTO / "strato-5"
    if not cartella_riferimento.is_dir():
        pytest.skip("riferimento non disponibile")
    for registrazione in sorted(Path("registrazioni/strato-5").glob("*.json")):
        atteso = cartella_riferimento / f"{registrazione.stem}.txt"
        if not atteso.is_file():
            continue
        cli.main(["replay", str(registrazione)])
        assert capsys.readouterr().out.encode() == atteso.read_bytes(), registrazione.name
