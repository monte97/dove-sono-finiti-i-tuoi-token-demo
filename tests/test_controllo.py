"""Test di controllo. Nati da test_strati.py e test_segnali.py, divisi per argomento."""
import contextlib
import io
import json
import re
import tempfile
import threading
import time
from pathlib import Path

import httpx2 as httpx
import server_finto as sf
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from server_finto import *  # noqa: F401,F403

def test_controllo_salta_il_formato_vecchio():
    import tempfile, json
    from pathlib import Path
    import controllo
    d = Path(tempfile.mkdtemp())
    (d / "vecchia.json").write_text(json.dumps({**run(), "dominio": "orario"}))
    (d / "senza-log.json").write_text(json.dumps(run()))
    (d / "nuova.json").write_text(json.dumps({**run(), "log_otel": []}))
    assert len(controllo.leggi(d, "guasto")) == 1
    (d / "nuova.json").unlink()
    assert controllo.leggi(d, "guasto") == []
    vero_banco, veri_casi = controllo.BANCO, list(controllo.CASI)
    nuovo = Path(tempfile.mkdtemp())
    (d / "k").mkdir()
    (d / "k" / "x.json").write_text(json.dumps({**run(), "dominio": "orario"}))  # il banco c'e', ma e' del sistema vecchio
    (nuovo / "k").mkdir()
    (nuovo / "k" / "x.json").write_text(json.dumps({**run(), "log_otel": []}))
    controllo.BANCO, controllo.CASI[:] = d, [("k", 0, True)]
    try:
        with contextlib.redirect_stdout(io.StringIO()) as fuori:
            controllo.confronta(nuovo)
        assert "banco da rigenerare" in fuori.getvalue()
    finally:
        controllo.BANCO, controllo.CASI[:] = vero_banco, veri_casi


def test_soglie_del_controllo():
    import controllo as k
    guasto = lambda g, sb: {"giuste": g, "sbagliate": sb}
    assert k.fuori_soglia(guasto(0.0, 22 / 30), "guasto", "banco") == []
    assert k.fuori_soglia(guasto(1 / 30, 22 / 30), "guasto", "banco")      # una giusta nel banco: fuori
    assert k.fuori_soglia(guasto(0.0, 0.6), "guasto", "banco")             # meno di due terzi sbagliate: fuori
    assert k.fuori_soglia(guasto(0.1, 0.5), "guasto", "controllo") == []   # 1 giusta e 5 sbagliate su 10: dentro
    assert k.fuori_soglia(guasto(0.2, 0.7), "guasto", "controllo")         # 2 giuste su 10: fuori
    assert k.fuori_soglia(guasto(0.0, 0.4), "guasto", "controllo")         # 4 sbagliate su 10: fuori
    assert k.fuori_soglia({"giuste": 1.0}, "sana", "controllo") == []
    assert k.fuori_soglia({"giuste": 0.9}, "sana", "controllo")


def test_il_banco_del_5_11_sta_dentro_le_soglie():
    import controllo as k
    for modo in ("guasto", "sana"):
        regs = k.leggi(k.BANCO / "strato-5", modo)
        if not regs:
            return  # repo senza banco: niente da controllare
        assert k.fuori_soglia(k.numeri(regs), modo, "banco") == [], modo
