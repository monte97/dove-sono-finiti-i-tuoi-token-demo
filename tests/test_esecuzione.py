"""Test di esecuzione. Nati dal riordino: produzione e impostazioni fra due run."""
import server_finto as sf
from server_finto import *

from osservare_a_strati.esecuzione import concludi_banco, esegui, esegui_banco  # noqa: F401
from osservare_a_strati.impostazioni import con


def test_produzione_mette_il_riassunto_sulla_radice():
    with con(strato=5, produzione=True):
        reg, _ = sf.corri(5)
    radice = sf.span_di(reg, "invoke_workflow assistente-evento")
    a = radice["attributi"]
    assert (a["banco.cartella"], a["banco.modo"]) == (sf.CARTELLA.name, "guasto")
    assert a["richiesta.forma"] and a["richiesta.costo_microusd"] > 0


def test_due_run_di_fila_con_strati_diversi():
    with con(strato=0):
        prima, _ = sf.corri(0)
    with con(strato=5):
        seconda, _ = sf.corri(5)
    assert prima["span"] == []
    assert "invoke_workflow assistente-evento" in sf.nomi(seconda)
