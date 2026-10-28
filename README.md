# Osservare a strati

Spike per il talk "Dove sono finiti i tuoi token? Tracciare un sistema multi-agente con OpenTelemetry"
(DevFest Alps 2026). La stessa risposta sbagliata, guardata con sei livelli di strumentazione: ogni
strato aggiunge poche righe e mostra qualcosa in più.

Il caso è costruito e il difetto è messo apposta. Due agenti: `cerca` legge il programma con lo
strumento `leggi_programma`, `valida` vede solo il testo di `cerca`. Con `--guasto` il servizio del
programma va in timeout (2 s) e per 120 s lo strumento serve la copia di ieri: 15:00 invece di 14:00.
L'età della copia sta solo sullo span `cache.read`, mai in ciò che vede il modello.

| strato | cosa si accende |
|---|---|
| 0 | niente OpenTelemetry: una riga di log e la fattura (somma dell'usage) |
| 1 | la strumentazione nativa dell'SDK Anthropic (`open_telemetry=`) |
| 2 | span `invoke_workflow` e `invoke_agent` a mano |
| 3 | span `execute_tool` a mano: argomenti, risultato, timeout |
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
.venv/bin/python strati.py --strato 1 --runner --guasto     # strato 1 con il tool runner dell'SDK
.venv/bin/python strati.py --replay registrazioni/strato-4/<file>.json
.venv/bin/python strati.py --riepilogo                      # una riga per strato e modo
.venv/bin/python strati.py --righe                          # righe di codice per strato
.venv/bin/python test_strati.py                             # controlli senza rete
```

Il replay stampa la registrazione come la run dal vivo, e ogni registrazione contiene solo gli
span che il suo strato ha catturato.

## Registrazioni

`registrazioni/strato-N/` sono versionate. Prima di salvare (e di stampare) `anthropic.organization.id`,
`anthropic.workspace.id` e `anthropic.request.id` diventano `"oscurato"`. Le registrazioni dello
strato 5 contengono prompt, risposte e riassunto del ragionamento, quindi anche l'email dell'utente
(qui finta): in un sistema vero vanno filtrate prima di uscire dal processo.

Il costo è una stima, token per listino di Claude Haiku 5.5 letto il 23/10/2026. Le convenzioni
GenAI di OpenTelemetry sono sperimentali e i nomi possono cambiare.

## Varianti: il grafo fra agenti lo decide il modello (ramo `grafo-del-modello`)

Nella pipeline fissa il passaggio da `cerca` a `valida` è scritto nel codice. Le varianti tengono
dominio, guasto, modello e ciclo scritto a mano, e lasciano il grafo al modello:

- `--variante A`, **agente come strumento**: `cerca` ha anche `chiedi_verifica`, che invoca `valida`.
  Se chiamarla, quando e cosa passarle (domanda, risposta, un `contesto` facoltativo) lo decide il modello.
- `--variante B`, **orchestratore**: `coordina` ha come strumenti gli agenti `cerca` e `valida` e
  decide chi chiamare, in che ordine, cosa passare e quando rispondere.

Strumentazione dell'arco fra agenti come nel refinement «Agent as a tool» delle convenzioni GenAI
(`gen_ai.execute_tool.transfer.internal`, repo `open-telemetry/semantic-conventions-genai`, stato
Development): span `execute_tool {strumento}` del chiamante, con `gen_ai.agent.name` del chiamante,
`gen_ai.transfer.mode = return_to_caller` e `gen_ai.transfer.target.name`, e dentro lo span
`invoke_agent` del chiamato.

Cosa cambia negli strati:

| strato | pipeline fissa | varianti A e B |
|---|---|---|
| 2 | radice e agenti, in fila | anche gli archi fra agenti (`execute_tool chiedi_verifica`, `execute_tool cerca`, `execute_tool valida`): senza, non si vede chi ha chiamato chi |
| 3 | argomenti e risultato di `leggi_programma` | anche argomenti e risultato degli archi: sono prompt, quindi il problema della redazione arriva qui |
| 5 | messaggi e ragionamento | in più: perché il modello ha scelto quell'arco e cosa ha deciso di passare |

```bash
.venv/bin/python strati.py --strato 5 --variante A --guasto
.venv/bin/python strati.py --strato 5 --variante B --guasto --banco 30
.venv/bin/python strati.py --misure 5     # riprove, verifiche, cosa arriva a valida, grafi diversi
```

Le registrazioni delle varianti stanno in `registrazioni/strato-N-A/` e `registrazioni/strato-N-B/`.
Le istruzioni di `valida` nelle varianti dicono in più che può ricevere un contesto: non sono
identiche a quelle della pipeline fissa.
