"""Il formato della registrazione: da span e log a dict, lettura e cartelle delle run."""
import json
from pathlib import Path

from opentelemetry.trace import StatusCode

from .impostazioni import Impostazioni
from .osservabilita.log import CAMPI_RIGA

RADICE = Path(__file__).resolve().parent.parent / "registrazioni"
ID_ACCOUNT = ("anthropic.organization.id", "anthropic.workspace.id", "anthropic.request.id")


def in_dict(s) -> dict:
    attributi = {k: list(v) if isinstance(v, tuple) else v for k, v in s.attributes.items()}
    for k in ID_ACCOUNT:  # gli id dell'account non finiscono ne' a schermo ne' nelle registrazioni
        if k in attributi:
            attributi[k] = "oscurato"
    return {"nome": s.name, "id": format(s.context.span_id, "016x"),
            "padre": format(s.parent.span_id, "016x") if s.parent else None,
            "trace": format(s.context.trace_id, "032x"),
            "inizio": s.start_time / 1e9, "fine": s.end_time / 1e9,
            "errore": s.status.status_code == StatusCode.ERROR, "attributi": attributi}


def log_in_dict(r) -> dict:
    """Un record di log con il contesto che l'handler gli ha messo: trace e span dello span corrente, e i campi della
    riga per chiamata se ci sono."""
    lr = r.log_record
    campi = {k: v for k, v in (lr.attributes or {}).items() if k in CAMPI_RIGA}
    return {"trace": format(lr.trace_id, "032x"), "span": format(lr.span_id, "016x"),
            "livello": lr.severity_text, "testo": lr.body, "tempo": lr.timestamp / 1e9,  # epoch in secondi, come inizio e fine degli span
            **({"campi": campi} if campi else {})}


def leggi(percorso: Path) -> dict:
    return json.loads(Path(percorso).read_text())


def cartella_della_run(i: Impostazioni) -> Path:
    coda = ["", "-correzione", "-correzione-completa", "-correzione-dialogo"][i.correzione]
    coda += "-maschera" if i.maschera else ""
    coda += "-produzione" if i.produzione else ""
    return RADICE / f"strato-{i.strato}{coda}"
