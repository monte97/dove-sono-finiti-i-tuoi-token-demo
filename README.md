# Osservare a strati

La demo del talk «Dove sono finiti i tuoi token? Tracciare un sistema multi-agente con OpenTelemetry»
(DevFest Alps 2026, Torino). Un assistente a tre agenti dà una risposta sbagliata con `200 OK`, e la si
guarda con sei livelli di strumentazione: ogni strato aggiunge poche righe di codice e mostra qualcosa in più
della stessa risposta.

Il caso è costruito e il guasto è messo apposta. Le decisioni del modello no: quelle sono registrate da run
vere con Claude Haiku 5.5.

## Il caso

`coordina` riceve la domanda dell'utente e ha due strumenti, che sono agenti: `cerca` legge il programma
dell'evento con lo strumento `leggi_programma`, `valida` controlla la risposta prima che arrivi all'utente.
Chi chiamare, in che ordine, quante volte e con quali parole lo decide il modello. Nel codice nessuna riga
dice «riprova» né «richiama `cerca`»: il ciclo dell'agente è scritto a mano proprio per vederlo.

Il guasto: con `--guasto` il servizio del programma va in timeout dopo 2 secondi, lo strumento apre un
interruttore e per 120 secondi serve l'ultima copia, di 26 ore prima. Il workshop è stato spostato alle 14:00,
la copia dice 15:00. L'età della copia sta solo sullo span `cache.read`, mai in quello che vede un modello.

Un secondo dominio, `--dominio freeze`, usa lo stesso codice e lo stesso guasto per una domanda più costosa da
sbagliare: si può fare adesso il deploy del servizio pagamenti, durante il freeze del Black Friday?

## Gli strati

| strato | cosa si accende |
|---|---|
| 0 | niente OpenTelemetry: una riga di log e la fattura (la somma dell'usage) |
| 1 | la strumentazione nativa dell'SDK Anthropic (`open_telemetry=`) |
| 2 | gli span `invoke_workflow`, `invoke_agent` e gli archi fra agenti (`execute_tool cerca`, `execute_tool valida`), scritti a mano |
| 3 | lo span `execute_tool` dello strumento: argomenti, risultato, timeout |
| 4 | lo span `cache.read`: età e motivo della copia |
| 5 | `content_mode: "content"`: messaggi e riassunto del ragionamento negli span |

Ogni strato contiene i precedenti. Le righe che esistono solo per osservare finiscono con un marcatore
(`# s3`): `strati.py --righe` le conta, `strati.py --codice N` stampa quelle dello strato N.

## Rigiocare le run, senza chiave

Tutte le run del talk sono in `registrazioni/`, e si rigiocano senza chiamare l'API. Il replay mostra solo
quello che lo strato di quella run aveva catturato.

```bash
python3.14 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python strati.py --replay registrazioni/strato-0/20261103-084248-guasto.json   # log 200 e fattura
.venv/bin/python strati.py --replay registrazioni/strato-1/20261103-085844-guasto.json   # sette trace scollegate
.venv/bin/python strati.py --replay registrazioni/strato-2/20261103-091541-guasto.json   # una trace, il grafo, il buco
.venv/bin/python strati.py --replay registrazioni/strato-5/20261103-083955-guasto.json   # tutto, ragionamento compreso
.venv/bin/python strati.py --replay registrazioni/strato-5/20261103-084022-guasto.json   # stessa domanda, altro albero
```

## Le misure

Una run non basta: il comportamento di un agente è una distribuzione. Le registrazioni sono un banco di 30 run
per strato e per caso, girato il 3/11/2026 sul modello e sull'SDK fissati in `requirements.txt` (tag
`banco-2026-11-06`).

```bash
.venv/bin/python strati.py --riepilogo        # una riga per cartella e modo: risposte sbagliate, tempi, token, costo
.venv/bin/python strati.py --misure 5         # riprove, alberi, approvazioni di valida, cosa arriva a valida
.venv/bin/python segnali.py registrazioni/strato-5 registrazioni/strato-5-freeze   # i cinque segnali, dai soli span
```

`segnali.py` calcola i cinque segnali di «Lunedì, in produzione» leggendo solo gli span, come farebbe un
backend: le richieste che chiamano uno strumento più di una volta, le forme dell'albero, quanto spesso `valida`
approva, le risposte nate da una copia vecchia, il costo per richiesta alla mediana e al 95° percentile.

## Il cruscotto

Gli stessi cinque segnali su Grafana, letti da Tempo con TraceQL. Le porte stanno fuori da 3000 e 3200:
Grafana su 3377, Tempo su 3210, OTLP HTTP su 4418.

```bash
docker compose -f cruscotto/compose.yaml up -d
.venv/bin/python tempo.py registrazioni/strato-5 registrazioni/strato-5-freeze   # le registrazioni, come appena finite
.venv/bin/python verifica_cruscotto.py registrazioni/strato-5 registrazioni/strato-5-freeze   # cruscotto contro segnali.py
open "http://localhost:3377/d/segnali?var-cartella=strato-5&var-modo=guasto"
```

Le metriche TraceQL contano span, non richieste: per questo ogni richiesta porta i suoi fatti sullo span in
cima, `invoke_workflow` (`richiesta.forma`, `richiesta.costo_microusd`, `richiesta.richiamati`,
`richiesta.copia_vecchia`). Il cruscotto guarda l'ultima ora, e `tempo.py` sposta gli orari delle registrazioni
ad adesso: dopo un'ora si rimandano. `banco.cartella` e `banco.modo` servono solo a filtrare le run della demo.

## Rifare le run

Servono una chiave Anthropic e qualche centesimo: una run costa circa un millesimo di dollaro.

```bash
echo "ANTHROPIC_API_KEY=..." > .env
.venv/bin/python strati.py --strato 3 --guasto                      # una run, stampata come il replay
.venv/bin/python strati.py --strato 5 --guasto --banco 10           # dieci run, una riga ciascuna
.venv/bin/python strati.py --strato 5 --dominio freeze --guasto     # il secondo dominio
.venv/bin/python strati.py --strato 5 --correzione                  # lo strumento dice quanto è vecchio il dato
.venv/bin/python strati.py --strato 5 --correzione-completa         # ...e valida sa cosa farne
.venv/bin/python strati.py --strato 5 --guasto --maschera           # uno SpanProcessor toglie l'email dagli span
.venv/bin/python strati.py --strato 5 --guasto --otlp http://localhost:4418/v1/traces   # dal vivo verso il cruscotto
.venv/bin/python controllo.py --run 10        # poche run per caso, confrontate con il banco
```

Le run nuove finiscono in `registrazioni/` accanto al banco; `controllo.py` usa una cartella sua.

## Le registrazioni

`registrazioni/strato-N` più il dominio (`-freeze`), la correzione (`-correzione`, `-correzione-completa`) e la
maschera (`-maschera`). Prima di salvare, e di stampare, `anthropic.organization.id`, `anthropic.workspace.id` e
`anthropic.request.id` diventano `"oscurato"`. Le registrazioni dello strato 5 contengono prompt, risposte e
riassunto del ragionamento, e quindi l'email dell'utente (qui finta): in un sistema vero il contenuto va
filtrato prima che esca dal processo.

`archivio/2026-10-28/` contiene le run di una versione precedente, da cui vengono le citazioni della prima
stesura del talk; i test di `test_segnali.py` leggono quelle, così i loro numeri restano fermi.

## Cosa questa demo non dice

- Le convenzioni GenAI di OpenTelemetry sono sperimentali: i nomi possono cambiare. L'SDK di Anthropic le usa a
  metà (lo span si chiama `anthropic.messages.create`, il motivo di fine sta in `anthropic.message.stop_reason`).
- Il costo è una stima: token per listino di Claude Haiku 5.5, letto il 23/10/2026. La fattura vera arriva dopo.
- L'interruttore vive dentro la singola richiesta, così ogni run paga il timeout. In produzione sarebbe
  condiviso: dopo il primo timeout le altre richieste leggerebbero la copia senza nessun sintomo nei token, e
  resterebbe acceso solo `cache.read`.
- `claude-haiku-5-5` è un alias senza snapshot datato: lo stesso nome può indicare un modello diverso domani.
  `controllo.py` serve a vedere se i numeri si sono spostati.
- La demo non usa la cache del provider: ogni giro rilegge tutto a prezzo pieno.

## L'orchestratore e le convenzioni

L'arco fra agenti è strumentato come nel refinement «Agent as a tool» delle convenzioni GenAI
(`gen_ai.execute_tool.transfer.internal`, repo `open-telemetry/semantic-conventions-genai`, stato Development):
lo span `execute_tool {agente}` del chiamante, con `gen_ai.agent.name` del chiamante,
`gen_ai.transfer.mode = return_to_caller` e `gen_ai.transfer.target.name`, e dentro lo span `invoke_agent` del
chiamato.

La pipeline fissa (il passaggio da `cerca` a `valida` scritto nel codice), la variante in cui `cerca` chiama
`valida` come strumento e il tool runner dell'SDK sono nel tag git `spike-a-b`, con le loro registrazioni.

## Test

```bash
.venv/bin/python test_strati.py     # controlli senza rete
.venv/bin/python test_segnali.py    # i segnali, sulle registrazioni e su run finte
```

## Chi l'ha scritta

Francesco Montelli. Se vuoi vedere così il tuo sistema, agenti o no, è il lavoro che faccio:
[montelli.dev](https://montelli.dev).
