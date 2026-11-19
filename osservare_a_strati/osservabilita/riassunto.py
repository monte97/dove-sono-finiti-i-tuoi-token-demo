"""Il riassunto della richiesta sullo span radice, per il cruscotto."""
import threading

from opentelemetry.sdk.trace import SpanProcessor

from ..analisi.segnali import riassunto
from ..registrazioni import ID_ACCOUNT, in_dict  # noqa: F401


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
