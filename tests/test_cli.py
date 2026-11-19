"""Test del comando unico `strati`: sottocomandi, controlli e messaggi di oggi."""
from pathlib import Path

import pytest

from osservare_a_strati import cli, esecuzione
from osservare_a_strati.impostazioni import attuali, con


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
    assert "7923fcc3" in capsys.readouterr().out
