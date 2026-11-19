# Le interazioni piu' comuni con la demo. `make` da solo elenca i comandi.
# I comandi usano il venv in .venv: non serve attivarlo.

PYTHON  ?= python3.14
VENV    := .venv
STRATI  := $(VENV)/bin/strati
GIULIA  := registrazioni/strato-5/20261105-202614-guasto.json
OTLP    ?= http://localhost:4418/v1/traces
CARTELLE ?= registrazioni/strato-5 registrazioni/strato-5-correzione
N       ?= 5
F       ?= $(GIULIA)

.DEFAULT_GOAL := aiuto
.PHONY: aiuto installa replay giulia riepilogo misure schema segnali righe codice test lint \
        cruscotto-su cruscotto-giu invia verifica run stima pulisci

aiuto: ## questo elenco
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-14s %s\n", $$1, $$2}'

$(STRATI):
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -r requirements.txt -e '.[dev]'

installa: $(STRATI) ## crea .venv con le versioni bloccate e il comando strati

# --- senza chiave: tutto sulle registrazioni ---

giulia: $(STRATI) ## rigioca la richiesta di Giulia mostrata nel talk
	$(STRATI) replay $(GIULIA)

replay: $(STRATI) ## rigioca una registrazione: make replay F=registrazioni/strato-3/<file>.json
	$(STRATI) replay $(F)

riepilogo: $(STRATI) ## una riga per strato e modo: esiti, tempi, token, costo
	$(STRATI) riepilogo

misure: $(STRATI) ## le misure di uno strato: make misure N=5
	$(STRATI) misure $(N)

schema: $(STRATI) ## il grafo di chi chiama chi, in testo e Mermaid, sulle run dello strato 5
	$(STRATI) schema registrazioni/strato-5

segnali: $(STRATI) ## i segnali da cruscotto, dai soli span: make segnali CARTELLE="..."
	$(STRATI) segnali $(CARTELLE)

righe: $(STRATI) ## quante righe aggiunge ogni strato
	$(STRATI) righe

codice: $(STRATI) ## le righe di uno strato, pulite per le slide: make codice N=2
	$(STRATI) codice $(N)

# --- sviluppo ---

test: $(STRATI) ## i test, senza rete, sul server finto
	$(VENV)/bin/pytest -q

lint: $(STRATI) ## ruff check (il formatter non si usa: spezzerebbe le righe # sN)
	$(VENV)/bin/ruff check .

# --- cruscotto: serve Docker ---

cruscotto-su: ## accende Grafana, Tempo, Loki, Prometheus e il collector
	docker compose -f cruscotto/compose.yaml up -d

cruscotto-giu: ## spegne il cruscotto
	docker compose -f cruscotto/compose.yaml down

invia: $(STRATI) ## rimanda le registrazioni al cruscotto, con gli orari di adesso
	$(STRATI) cruscotto invia $(CARTELLE)

verifica: $(STRATI) ## confronta i numeri del cruscotto con quelli di strati segnali
	$(STRATI) cruscotto verifica $(CARTELLE)

# --- dal vivo: servono la chiave in .env e un po' di spesa ---

run: $(STRATI) ## una run dal vivo nella giornata piena: make run N=3
	$(STRATI) run --strato $(N) --guasto

stima: $(STRATI) ## cosa lancerebbe il controllo della settimana e quanto costa, senza chiamare l'API
	$(STRATI) controllo stima

pulisci: ## toglie le cache di Python, pytest e ruff (non tocca .venv ne' registrazioni)
	find . -name __pycache__ -not -path './$(VENV)/*' -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache
