# Osservare a strati

Spike per il talk "Dove sono finiti i tuoi token? Tracciare un sistema multi-agente con OpenTelemetry"
(DevFest Alps 2026). La stessa risposta sbagliata, guardata con sei livelli di strumentazione: ogni
strato aggiunge poche righe e mostra qualcosa in più.

Il caso è costruito e il difetto è messo apposta. Tre agenti: `coordina` è l'orchestratore e ha
come strumenti gli agenti `cerca` e `valida`; chi chiamare, in che ordine, cosa passare e quando
rispondere lo decide il modello. `cerca` legge il programma con lo strumento `leggi_programma`,
`valida` controlla una risposta prima che arrivi all'utente. Con `--guasto` il servizio del programma
va in timeout (2 s) e per 120 s lo strumento serve la copia di ieri: 15:00 invece di 14:00. L'età
della copia sta solo sullo span `cache.read`, mai in ciò che vede il modello.

| strato | cosa si accende |
|---|---|
| 0 | niente OpenTelemetry: una riga di log e la fattura (somma dell'usage) |
| 1 | la strumentazione nativa dell'SDK Anthropic (`open_telemetry=`) |
| 2 | span `invoke_workflow`, `invoke_agent` e gli archi fra agenti (`execute_tool cerca`, `execute_tool valida`) a mano |
| 3 | span `execute_tool` a mano: argomenti, risultato, timeout; anche gli argomenti degli archi, che sono prompt |
| 4 | span `cache.read`: età e motivo della copia |
| 5 | `content_mode: "content"`: messaggi e riassunto del ragionamento negli span |

Ogni strato contiene i precedenti. Le righe che esistono solo per osservare finiscono con un
marcatore (`# s3`); `--righe` le conta.

## Uso

```bash
/percorso/di/un/python3.14 -m venv .venv && .venv/bin/pip install -r requirements.txt
echo "ANTHROPIC_API_KEY=..." > .env
.venv/bin/python strati.py --strato 0 --guasto              # una run
.venv/bin/python strati.py --strato 3 --guasto --banco 5    # cinque run, una riga ciascuna
.venv/bin/python strati.py --replay registrazioni/strato-4/<file>.json
.venv/bin/python strati.py --riepilogo                      # una riga per strato e modo
.venv/bin/python strati.py --misure 5                       # riprove, verifiche, cosa arriva a valida, grafi diversi
.venv/bin/python segnali.py registrazioni/strato-5-freeze  # i cinque segnali per la produzione, dagli span
.venv/bin/python strati.py --righe                          # righe di codice per strato
.venv/bin/python strati.py --codice 4                       # le righe dello strato 4, pulite per le slide
.venv/bin/python strati.py --strato 5 --dominio freeze --guasto     # stesso codice, altra domanda: il freeze di un deploy
.venv/bin/python strati.py --strato 5 --correzione          # lo strumento dice quanto è vecchio il dato
.venv/bin/python strati.py --strato 5 --correzione-completa # ...e valida sa cosa farne
.venv/bin/python strati.py --strato 5 --guasto --maschera   # uno SpanProcessor toglie l'email dagli span
.venv/bin/python test_strati.py                             # controlli senza rete
.venv/bin/python test_segnali.py                            # i segnali, sulle registrazioni e su run finte
```

Il replay stampa la registrazione come la run dal vivo, e ogni registrazione contiene solo gli
span che il suo strato ha catturato.

## Registrazioni

Le cartelle si chiamano `strato-N`, più il dominio (`-freeze`), la correzione (`-correzione`,
`-correzione-completa`) e la maschera (`-maschera`). `--riepilogo` dà una riga per cartella e modo.

`registrazioni/strato-N/` sono versionate. Prima di salvare (e di stampare) `anthropic.organization.id`,
`anthropic.workspace.id` e `anthropic.request.id` diventano `"oscurato"`. Le registrazioni dello
strato 5 contengono prompt, risposte e riassunto del ragionamento, quindi anche l'email dell'utente
(qui finta): in un sistema vero vanno filtrate prima di uscire dal processo.

Il costo è una stima, token per listino di Claude Haiku 5.5 letto il 23/10/2026. Le convenzioni
GenAI di OpenTelemetry sono sperimentali e i nomi possono cambiare.

## L'orchestratore e le convenzioni

L'arco fra agenti è strumentato come nel refinement «Agent as a tool» delle convenzioni GenAI
(`gen_ai.execute_tool.transfer.internal`, repo `open-telemetry/semantic-conventions-genai`, stato
Development): span `execute_tool {agente}` del chiamante, con `gen_ai.agent.name` del chiamante,
`gen_ai.transfer.mode = return_to_caller` e `gen_ai.transfer.target.name`, e dentro lo span
`invoke_agent` del chiamato.

La pipeline fissa (il passaggio da `cerca` a `valida` scritto nel codice), la variante A (`cerca`
che chiama `valida` come strumento) e il tool runner dell'SDK sono nel tag git `spike-a-b`, con le
loro registrazioni.
