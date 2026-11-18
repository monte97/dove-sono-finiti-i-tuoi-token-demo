"""Il modello e il suo prezzo."""

MODEL = "claude-haiku-5-5"
LISTINO = (0.10, 0.01, 0.50)  # USD per milione: ingresso, letto dalla cache, uscita (ragionamento compreso); letto il 23/10/2026
MAX_GIRI = 6

PENSIERO = {"type": "adaptive", "display": "summarized"}  # il riassunto del ragionamento torna solo se lo chiedi


def costo(ingresso: int, cache: int, uscita: int) -> float:
    p_in, p_cache, p_out = LISTINO
    return ((ingresso - cache) * p_in + cache * p_cache + uscita * p_out) / 1e6
