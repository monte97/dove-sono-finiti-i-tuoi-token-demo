"""Gli strumenti che leggono i dati della demo."""
import json

from opentelemetry import trace

from ..evento.avvisi import AVVISI_PER_PAGINA, avvisi
from ..evento.dati import AVVISI_AGGIORNATI, PROGRAMMA, PUBBLICATO, SALE, SESSIONE_SALA, _trova, sala_normale
from ..impostazioni import attuali
from ..osservabilita.log import LOG


# Attributi inventati, con prefisso proprio (le convenzioni semantiche non li coprono):
#   programma.pubblicato_il   quando e' stato pubblicato il programma letto
#   sale.fonte                da dove viene il dato sulle sale
#   avvisi.pagine             pagine di avvisi restituite al modello
#   avvisi.letti              avvisi restituiti al modello
#   avvisi.filtro             "nessuno" oppure la sala richiesta
#   avvisi.aggiornati_alle    ora dell'ultimo aggiornamento della bacheca
#   richiesta.correzione      sulla radice: nessuna | istruzioni | filtro | dialogo
#   richiesta.versione_prompt sulla radice: hash corto delle istruzioni e delle descrizioni degli strumenti in uso
# (gli altri richiesta.*, i riassunti per richiesta del cruscotto, sono dichiarati nel modulo analisi.segnali)
def leggi_dato(nome: str, argomenti: dict, stato: dict) -> str:
    """Lo strumento che legge un dato. Niente e' rotto: ognuno risponde correttamente a cio' che gli si chiede."""
    if nome == "leggi_programma":
        sessione = argomenti.get("sessione", "")
        LOG.info("leggi_programma: %s dal programma pubblicato il %s", sessione, PUBBLICATO)
        if attuali().strato >= 4:  # s4
            trace.get_current_span().set_attribute("programma.pubblicato_il", PUBBLICATO)  # s4
        return json.dumps(_trova(PROGRAMMA, sessione)[1], ensure_ascii=False)
    if nome == "leggi_sale":
        sessione = argomenti.get("sessione", "")
        LOG.info("leggi_sale: %s dal database delle sale", sessione)
        if attuali().strato >= 4:  # s4
            trace.get_current_span().set_attribute("sale.fonte", "database delle sale")  # s4
        k, dato = _trova(SESSIONE_SALA, sessione)
        return json.dumps(SALE[dato] if k else dato, ensure_ascii=False)
    if nome != "leggi_avvisi":  # un nome inventato dal modello e' un errore suo, non un caso dei dati
        return json.dumps({"errore": f"strumento sconosciuto: {nome}"}, ensure_ascii=False)
    voci = [v for pagina in avvisi(stato["piena"]) for v in pagina]  # tutte le pagine, in una sola chiamata
    filtro = "nessuno"
    if attuali().correzione == 2:
        sala = sala_normale(argomenti.get("sala", ""))
        voci = [v for v in voci if v.startswith(f"Sala {sala}:")]
        filtro = f"sala {sala}"
    pagine = -(-len(voci) // AVVISI_PER_PAGINA)
    LOG.info("leggi_avvisi: %d pagine, %d avvisi, filtro %s", pagine, len(voci), filtro)
    if attuali().strato >= 4:  # s4
        trace.get_current_span().set_attributes({"avvisi.pagine": pagine, "avvisi.letti": len(voci),  # s4
                                                 "avvisi.filtro": filtro,  # s4
                                                 "avvisi.aggiornati_alle": AVVISI_AGGIORNATI})  # s4
    return "\n".join(f"- {v}" for v in voci) or "Nessun avviso."
