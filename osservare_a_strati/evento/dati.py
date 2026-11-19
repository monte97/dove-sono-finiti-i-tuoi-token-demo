"""I dati del caso: la domanda di Giulia, il programma pubblicato, le sale e i loro collegamenti."""
import re

DOMANDA = ("Ciao, sono Giulia Rossi (giulia.rossi@example.com). "
           "A che ora è il workshop Kubernetes da zero?")

# Il programma pubblicato ieri sera. Stamattina la sala B e' stata chiusa dalle 15:00 e le sessioni del
# pomeriggio in sala B iniziano un'ora prima: lo dice solo un avviso, che non nomina il workshop.
PUBBLICATO = "4/11 alle 18:00"
AVVISI_AGGIORNATI = "5/11 alle 09:40"  # l'ultimo aggiornamento della bacheca avvisi
PROGRAMMA = {"Kubernetes da zero": {"giorno": "oggi", "ora": "15:00", "sala": "B"},
             "OpenTelemetry in un'ora": {"giorno": "oggi", "ora": "11:00", "sala": "A"},
             "Rust per chi scrive Go": {"giorno": "domani", "ora": "16:30", "sala": "C"}}
SALE = {"A": {"sala": "A", "piano": 0, "capienza": 120},
        "B": {"sala": "B", "piano": 1, "capienza": 80},
        "C": {"sala": "C", "piano": 2, "capienza": 60}}
SESSIONE_SALA = {"Kubernetes da zero": "B", "OpenTelemetry in un'ora": "A", "Rust per chi scrive Go": "C"}


def _trova(tabella: dict, chiave: str):
    chiave = chiave.strip()
    k = None if not chiave else next((k for k in tabella if k.lower() in chiave.lower() or chiave.lower() in k.lower()), None)
    return k, (tabella[k] if k else {"errore": "non trovato", "disponibili": list(tabella)})


def sala_normale(testo: str) -> str:
    """«B», « b », «sala B», «Sala B.» sono la stessa sala: toglie «sala» davanti, punteggiatura e spazi, e maiuscola."""
    t = re.sub(r"^\s*sala\b", "", str(testo), flags=re.IGNORECASE)
    return re.sub(r"[^\w]", "", t).upper()
