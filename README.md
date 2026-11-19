# Osservare a strati

> **Lavori in corso.** Il talk è del 28 novembre 2026: codice, registrazioni e numeri possono cambiare fino ad allora; qualche documento in `docs/` è ancora una bozza e le slide arriveranno dopo il talk.

La demo del talk «Dove sono finiti i tuoi token? Tracciare un sistema multi-agente con OpenTelemetry»
(DevFest Alps 2026, Torino). Un assistente a cinque agenti risponde a una domanda semplice con un orario
sbagliato e un `200 OK`, e lo si guarda con sei livelli di strumentazione: ogni strato aggiunge poche righe di
codice e mostra qualcosa in più della stessa risposta.

Il caso è costruito e il guasto è messo apposta. Le decisioni del modello no: quelle sono registrate da run
vere con Claude Haiku 5.5 (`claude-haiku-5-5`).

## Il caso

- DevFest Immaginario 2026. Giulia Rossi chiede a che ora è il workshop Kubernetes da zero.
- Il programma dice oggi alle 15:00 in sala B. Un avviso, che non nomina il workshop, dice che la sala B è chiusa
  dalle 15:00 e che le sessioni del pomeriggio iniziano un'ora prima.
- La risposta giusta è 14:00, il sistema risponde 15:00: nessun agente sbaglia rispetto al proprio contratto, la
  causa sta nella composizione dei rami e si vede solo guardandoli insieme nella stessa trace.

## Provalo in due minuti

Le run si rigiocano senza chiamare l'API: il replay mostra solo quello che lo strato di quella run aveva catturato.

```bash
python3.14 -m venv .venv
.venv/bin/pip install -r requirements.txt -e .    # versioni bloccate in requirements.txt
source .venv/bin/activate
strati replay registrazioni/strato-5/20261105-202614-guasto.json    # la richiesta di Giulia mostrata nel talk
```

I comandi qui e nei documenti si danno con l'ambiente attivo (`source .venv/bin/activate`).

## La mappa del repo

| percorso | cosa c'è |
|---|---|
| `osservare_a_strati/` | il pacchetto e il comando `strati` |
| `osservare_a_strati/cli.py` | i sottocomandi; `__main__.py` è `python -m osservare_a_strati` |
| `osservare_a_strati/impostazioni.py` | strato, correzione, maschera, produzione e OTLP di una run in un oggetto solo |
| `osservare_a_strati/esecuzione.py` | una run: esegue, misura il tempo, scrive la registrazione |
| `osservare_a_strati/registrazioni.py` | il formato della registrazione e la sua lettura |
| `osservare_a_strati/stampa.py` | la vista a terminale, uguale per run dal vivo e replay |
| `osservare_a_strati/valutazione.py` | esito di una risposta, approvazione, avviso riportato, classe della domanda |
| `osservare_a_strati/righe.py` | conteggio dei marcatori `# sN` e codice per le slide |
| `osservare_a_strati/evento/` | il caso: programma, sale, avvisi, domanda di Giulia |
| `osservare_a_strati/agenti/` | istruzioni, schemi, strumenti dei dati, ciclo, agente come strumento, guardia dei cicli |
| `osservare_a_strati/osservabilita/` | tracce, log, metriche, client e riassunto della richiesta |
| `osservare_a_strati/analisi/` | lettura degli span, misure, schema, segnali, controllo |
| `osservare_a_strati/cruscotto/` | rimando a Tempo, Loki e Prometheus, e verifica del cruscotto |
| `cruscotto/` | compose e configurazioni di collector, Tempo, Loki, Prometheus e Grafana |
| `registrazioni/` | il banco del 5/11, con una cartella per strato e per correzione |
| `docs/` | la documentazione; `docs/banco/` ha metodo, numeri, uscite e diciassette-alberi |
| `tests/` | pytest e il server finto |
| `pyproject.toml`, `requirements.txt` | pacchetto e dipendenze bloccate |
| `.env.esempio` | la chiave Anthropic per le run dal vivo |

## Gli strati

| strato | cosa si accende |
|---|---|
| 0 | oggi: una riga di log per ogni chiamata al modello, con l'agente e il conto della risposta nei nomi delle convenzioni GenAI (`gen_ai.agent.name`, `gen_ai.usage.input_tokens` con la cache dentro, `gen_ai.usage.output_tokens`, `gen_ai.usage.cache_read.input_tokens`, `gen_ai.usage.cache_write.input_tokens`) e un id della richiesta, nostro, e la fattura (la somma dell'usage); niente OpenTelemetry |
| 1 | le metriche dei token e l'SDK: due contatori per chiamata con i nomi delle convenzioni GenAI (`gen_ai.client.inference.usage.input_tokens` e `output_tokens`, più `gen_ai.agent.name`), un istogramma mio (`assistente.agente.token`, un valore per agente a fine richiesta) e la strumentazione nativa di Anthropic (`open_telemetry=`) |
| 2 | gli agenti: gli span `invoke_workflow`, `invoke_agent` e gli archi fra agenti, scritti a mano, con il contesto propagato ai thread dei rami paralleli |
| 3 | lo strumento: lo span `execute_tool` con argomenti e risultato, più i log correlati: le righe di `logging` dello strumento escono con `trace_id` e `span_id` |
| 4 | i dati letti: da dove viene il dato e quanto. Per `leggi_programma` la data di pubblicazione, per `leggi_avvisi` pagine e avvisi letti, filtro usato e ora dell'ultimo aggiornamento |
| 5 | il contenuto: `content_mode: "content"`, messaggi e riassunto del ragionamento negli span |

Ogni strato contiene i precedenti. Le righe che esistono solo per osservare finiscono con un marcatore (`# s3`):
`strati righe` le conta, `strati codice N` stampa quelle dello strato N.

## I comandi principali

| comando | cosa fa |
|---|---|
| `strati replay FILE` | rigioca una registrazione, come allora |
| `strati run --strato N [--guasto] [--correzione ...]` | una run dal vivo |
| `strati banco K --strato N ...` | K run, una riga ciascuna |
| `strati riepilogo` | una riga per cartella e modo |
| `strati misure N` | come ha deciso il grafo, cosa ha letto e riportato `avvisi`, token per agente |
| `strati schema CARTELLA` | il grafo delle chiamate in testo e Mermaid |
| `strati segnali [CARTELLE]` | i cinque segnali dai soli span |
| `strati righe`, `strati codice N` | conteggio e codice per le slide |
| `strati controllo stima`, `run`, `confronta` | il banco breve della settimana del talk |
| `strati cruscotto invia`, `verifica` | manda le registrazioni e controlla il cruscotto |
| `pytest -q` | i test, senza rete e sul server finto (prima `pip install -e '.[dev]'`) |

## Dove leggere il resto

- [docs/architettura.md](docs/architettura.md): come una richiesta attraversa il pacchetto, dove stanno le righe di ogni strato, lo stato condiviso.
- [docs/caso.md](docs/caso.md): il caso per esteso, il criterio, gli agenti, la correzione, il sistema precedente.
- [docs/strati.md](docs/strati.md): i marcatori, il fatto sull'SDK, log e metriche, lo schema del sistema.
- [docs/cruscotto.md](docs/cruscotto.md): il cruscotto, le misure, come rifare le run e il banco, i diciassette alberi.
- [docs/convenzioni.md](docs/convenzioni.md): le convenzioni GenAI, gli agenti che si chiamano, cosa la demo non dice, i test.
- [docs/banco/](docs/banco/README.md): i numeri del banco, le uscite grezze e i diciassette alberi.
- [registrazioni/README.md](registrazioni/README.md): cosa c'è in ogni cartella e quale run usa il talk.

## Chi l'ha scritta

Francesco Montelli. Se vuoi vedere così il tuo sistema, agenti o no, è il lavoro che faccio:
[montelli.dev](https://montelli.dev).
