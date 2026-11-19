"""I testi che il modello legge: istruzioni, descrizioni, schemi e la loro versione."""
import hashlib
import json

from ..impostazioni import NOMI_CORREZIONE, attuali
from ..osservabilita.tracce import VERSIONE

# Istruzioni come le scriverebbe un team: dicono cosa fa ciascuno, non come evitare la trappola.
ISTRUZIONI = {
    "coordina": ("Sei l'assistente di DevFest Immaginario 2026 e coordini quattro agenti: programma legge il programma "
                 "pubblicato, sale le informazioni sulle sale (anche il piano), avvisi le comunicazioni di oggi, valida controlla una "
                 "risposta prima che arrivi all'utente. Per rispondere consulta programma, sale e avvisi; prima di "
                 "rispondere conviene far controllare la risposta da valida. Rispondi in una riga con giorno, ora, sala e piano."),
    "programma": ("Sei l'assistente del programma di DevFest Immaginario 2026. Per giorno, ora e sala di una sessione "
                  "usa sempre lo strumento leggi_programma; per il piano della sala chiedi all'agente sale. "
                  "Rispondi in una riga con giorno, ora, sala e piano."),
    "sale": ("Sei l'assistente delle sale di DevFest Immaginario 2026. Per sala, piano e capienza usa sempre lo strumento "
             "leggi_sale. Rispondi in una riga."),
    "avvisi": ("Sei l'assistente delle comunicazioni di DevFest Immaginario 2026. Gli avvisi di oggi li leggi con lo "
               "strumento leggi_avvisi. Riporta solo gli avvisi che riguardano ciò che ti è stato chiesto, al "
               "massimo tre righe, senza supposizioni; se non ce ne sono, rispondi «Nessun avviso.»."),
    "valida": ("Controlli le risposte dell'assistente di DevFest Immaginario 2026 prima che arrivino all'utente. "
               "Ricevi la domanda, la risposta e, se c'è, il contesto su cui si basa. Verifica che l'orario sia valido, "
               "che la sala esista (le sale sono A, B e C) e che la risposta sia pertinente alla domanda e coerente "
               "con il contesto. Se hai un dubbio sul contesto, puoi ricontrollarlo alla fonte prima di approvare: "
               "programma ti dice giorno, ora e sala di una sessione, avvisi le comunicazioni di oggi che la riguardano. "
               "Se va tutto bene, restituisci la risposta com'è aggiungendo in fondo «Verificato.». "
               "Altrimenti spiega cosa non va."),
}
DESCRIZIONI = {
    "programma": ("Agente che trova giorno, ora e sala di una sessione leggendo il programma pubblicato, e il piano "
                  "chiedendolo a sale. Risponde in una riga."),
    "sale": "Agente che trova sala, piano e capienza di una sessione leggendo il database delle sale. Risponde in una riga.",
    "avvisi": "Agente che riporta gli avvisi di oggi che riguardano la richiesta, al massimo tre righe.",
    "valida": ("Agente che controlla una risposta prima che arrivi all'utente. Restituisce la risposta verificata "
               "oppure cosa non va."),
}

# La correzione: 1 solo istruzioni a coordina (chiedi gli avvisi della sala dopo averla saputa);
# 2 in piu' leggi_avvisi vuole la sala e restituisce solo gli avvisi di quella sala (include la 1);
# 3 (dialogo) e' un'alternativa, non include la 1 ne' la 2: coordina e leggi_avvisi restano come nel guasto, ma
# avvisi puo' chiedere a programma giorno, ora e sala di una sessione.
CORREZIONE_COORDINA = " Quando conosci la sala della sessione, chiedi ad avvisi le comunicazioni su quella sala."
CORREZIONE_AVVISI = " Lo strumento leggi_avvisi vuole la sala: usa quella indicata nella richiesta."
CORREZIONE_DIALOGO = (" Se per capire quali avvisi riguardano la richiesta ti servono giorno, ora e sala di una sessione, "
                      "puoi chiederli all'agente programma.")

_VERIFICA = {"type": "object", "required": ["domanda", "risposta"],
             "properties": {"domanda": {"type": "string", "description": "la domanda dell'utente"},
                            "risposta": {"type": "string", "description": "la risposta da controllare"},
                            "contesto": {"type": "string", "description": "informazioni utili alla verifica (facoltativo)"}}}


def _un_campo(campo: str, descrizione: str) -> dict:
    return {"type": "object", "required": [campo], "properties": {campo: {"type": "string", "description": descrizione}}}


def _sala_schema() -> dict:
    s = _un_campo("sala", "la sala: A, B o C")
    s["properties"]["sala"]["enum"] = ["A", "B", "C"]
    return s


def schemi(correzione: int | None = None) -> dict:
    sala = (attuali().correzione if correzione is None else correzione) == 2
    avvisi_tool = {"name": "leggi_avvisi", "input_schema": {"type": "object", "properties": {}},
                   "description": "Legge tutte le comunicazioni di oggi, tutte le pagine in una sola chiamata."}
    if sala:
        avvisi_tool = {"name": "leggi_avvisi", "input_schema": _sala_schema(),
                       "description": "Legge le comunicazioni di oggi che riguardano una sala."}
    return {
        "leggi_programma": {"name": "leggi_programma", "input_schema": _un_campo("sessione", "titolo della sessione"),
                            "description": "Legge dal programma pubblicato giorno, ora e sala di una sessione."},
        "leggi_sale": {"name": "leggi_sale", "input_schema": _un_campo("sessione", "titolo della sessione"),
                       "description": "Legge dal database delle sale sala, piano e capienza di una sessione."},
        "leggi_avvisi": avvisi_tool,
        **{n: {"name": n, "description": DESCRIZIONI[n], "input_schema": _un_campo("richiesta", "cosa cercare")}
           for n in ("programma", "sale", "avvisi")},
        "valida": {"name": "valida", "input_schema": _VERIFICA, "description": DESCRIZIONI["valida"]},
    }


def agenti_strumento(correzione: int | None = None) -> dict:
    """strumento -> (agente invocato, sue istruzioni, suoi strumenti)"""
    corr = attuali().correzione if correzione is None else correzione
    return {"programma": ("programma", ISTRUZIONI["programma"], ["leggi_programma", "sale"]),
            "sale": ("sale", ISTRUZIONI["sale"], ["leggi_sale"]),
            "avvisi": ("avvisi", ISTRUZIONI["avvisi"] + (CORREZIONE_AVVISI if corr == 2 else CORREZIONE_DIALOGO if corr == 3 else ""),
                       ["leggi_avvisi"] + (["programma"] if corr == 3 else [])),
            "valida": ("valida", ISTRUZIONI["valida"], ["programma", "avvisi"])}


def istruzioni_coordina(correzione: int | None = None) -> str:
    correzione = attuali().correzione if correzione is None else correzione
    return ISTRUZIONI["coordina"] + (CORREZIONE_COORDINA if correzione in (1, 2) else "")


# Che versione del comportamento sta girando: la modalita' di correzione e un hash corto del testo che il modello legge
# davvero (le istruzioni di ogni agente e le descrizioni e gli schemi degli strumenti, con la correzione applicata).
# Stesso testo, stesso hash: cambia solo se cambia una parola di un'istruzione o di una descrizione.
def versione_prompt(correzione: int | None = None) -> str:
    testo = json.dumps({"coordina": istruzioni_coordina(correzione), "agenti": agenti_strumento(correzione),
                        "strumenti": schemi(correzione)}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(testo.encode()).hexdigest()[:8]


def versione(correzione: int | None = None) -> dict:
    """Quello che la registrazione e lo span radice dicono sulla versione, per una modalita' di correzione."""
    correzione = attuali().correzione if correzione is None else correzione
    return {"codice": VERSIONE, "correzione": NOMI_CORREZIONE[correzione], "prompt": versione_prompt(correzione)}
