"""Il riassunto della richiesta sullo span radice, per il cruscotto."""
import threading

from opentelemetry.sdk.trace import SpanProcessor
from opentelemetry.trace import StatusCode

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


class RiassuntoSullaRadice(SpanProcessor):
    """In produzione: a ogni span che si chiude, il riassunto della richiesta si riscrive sulla radice ancora aperta.
    I rami paralleli chiudono i loro span da thread diversi: il lock tiene coerenti radici e span chiusi."""

    def __init__(self, strato: int):
        self.strato, self.radici, self.chiusi = strato, {}, {}
        self.lock = threading.Lock()

    def on_start(self, span, parent_context=None):
        if span.parent is None or span.parent.is_remote:
            with self.lock:
                self.radici[span.context.trace_id] = span

    def on_end(self, span):
        from segnali import riassunto  # segnali importa strati, che importa questo modulo: solo qui, a run avviata
        tid = span.context.trace_id
        with self.lock:
            radice = self.radici.get(tid)
            if radice is not None and radice.context.span_id == span.context.span_id:  # la richiesta e' finita
                del self.radici[tid]
                self.chiusi.pop(tid, None)
                return
            if radice is not None:
                self.chiusi.setdefault(tid, []).append(in_dict(span))
                radice.set_attributes(riassunto({"strato": self.strato, "span": self.chiusi[tid]}))
