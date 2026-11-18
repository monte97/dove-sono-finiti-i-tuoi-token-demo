"""Il client Anthropic con l'osservabilita' dello strato corrente."""
import anthropic

from ..impostazioni import attuali
from .log import fai_log
from .metriche import fai_metriche
from .tracce import fai_provider


def cliente(**prova):
    if attuali().strato == 0:
        fai_log()
        return anthropic.Anthropic(open_telemetry=False, **prova)
    fai_metriche()
    provider = fai_provider(attuali().maschera)
    fai_log()
    modo = "metadata_only"  # s1
    if attuali().strato >= 5:  # s5
        modo = "content"  # s5
    return anthropic.Anthropic(open_telemetry={"tracer_provider": provider,  # s1
                                               "traces": {"content_mode": modo}}, **prova)  # s1
