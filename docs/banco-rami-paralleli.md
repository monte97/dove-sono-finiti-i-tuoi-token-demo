# Banco: i numeri della giornata piena

Scheletro della tabella dei numeri del talk. I valori sono `[banco]` finché il banco non è stato rifatto sul
sistema nuovo (cinque agenti, rami paralleli): le registrazioni che stanno oggi in `registrazioni/` sono quelle
del sistema precedente, tag `tre-agenti-in-fila`, e le misure nuove non le leggono.

## Rifare il banco

30 run per modo e per strato. Il costo reale di ogni run è nella fattura della registrazione; il tetto
indicativo per l'intero banco è 5 $.

```bash
for N in 0 1 2 3 4 5; do
  .venv/bin/python strati.py --strato $N --banco 30                        # sana
  .venv/bin/python strati.py --strato $N --guasto --banco 30               # guasto
  .venv/bin/python strati.py --strato $N --correzione --banco 30           # correzione
  .venv/bin/python strati.py --strato $N --correzione-completa --banco 30  # correzione completa
done
```

Le cartelle risultanti sono `registrazioni/strato-N`, `strato-N-correzione` e `strato-N-correzione-completa`;
`sana` e `guasto` stanno nella stessa cartella e si distinguono dal campo `modo`.

## La tabella

| Numero | Valore | Comando che lo riproduce |
|---|---|---|
| Durata e costo, guasta contro sana, strato 0 | `[banco]` | `.venv/bin/python strati.py --riepilogo` (righe `strato-0 guasto` e `strato-0 sana`: colonne `sec med` e `$ med`) |
| Token per richiesta (strato 5, guasta) | `[banco]` | `.venv/bin/python strati.py --misure 5` (riga `mediane`: `token`) |
| Quota di `avvisi` sui token della richiesta | `[banco]` | `.venv/bin/python strati.py --misure 5` (riga `quota di avvisi sui token`); per mediana e 95° percentile `.venv/bin/python segnali.py registrazioni/strato-5` |
| Costo per agente | `[banco]` | `.venv/bin/python strati.py --misure 5` (riga `token per agente`, a prezzo di `LISTINO`; non c'è un comando che lo stampi già in dollari) |
| Quota delle riletture | `[banco]` | `.venv/bin/python strati.py --misure 5` (`chiamate al modello` e `token per agente`; nessun comando la calcola direttamente, va aggiunto o ricavato dagli span `gen_ai.usage.input_tokens`) |
| Sbagliate su 30, guasta | `[banco]` | `.venv/bin/python strati.py --misure 5` (riga `guasto: n 30 · sbagliata ...`) |
| Sbagliate su 30, sana | `[banco]` | `.venv/bin/python strati.py --misure 5` (riga `sana: n 30 · sbagliata ...`) |
| Run in cui `avvisi` omette l'avviso | `[banco]` | `.venv/bin/python strati.py --misure 5` (righe `leggi_avvisi ha restituito l'avviso sulla sala B` contro `avvisi lo riporta a coordina`) |
| Verdetti di `valida` | `[banco]` | `.venv/bin/python strati.py --misure 5` (riga `valida approva`); `.venv/bin/python segnali.py registrazioni/strato-5` |
| Run con i tre rami nello stesso giro | `[banco]` | `.venv/bin/python strati.py --misure 5` (riga `programma, sale, avvisi nello stesso giro`) |
| Forme dell'albero | `[banco]` | `.venv/bin/python strati.py --misure 5` (elenco `forme dell'albero`); `.venv/bin/python segnali.py registrazioni/strato-5` |
| Correzione, passo 1: correttezza e costo | `[banco]` | `.venv/bin/python strati.py --misure 5` (cartella `strato-5-correzione`); `.venv/bin/python segnali.py registrazioni/strato-5-correzione` |
| Correzione completa, passo 2: correttezza e costo | `[banco]` | `.venv/bin/python strati.py --misure 5` (cartella `strato-5-correzione-completa`); `.venv/bin/python segnali.py registrazioni/strato-5-correzione-completa` |

`--misure 5` stampa insieme `strato-5`, `strato-5-correzione` e `strato-5-correzione-completa`, ognuna con le
giornate `guasto` e `sana` che contiene.

## Il fatto sull'SDK

L'SDK `anthropic` 1.15.0 (`_tracing.py`), verificato il 5/11/2026, scrive il contenuto solo come attributi di
span (`gen_ai.input.messages`, `gen_ai.output.messages`). Non produce eventi, log né metriche. I log correlati
dello strato 3 sono quelli dello strumento, scritti con il `logging` di Python ed esportati da un
`LoggingHandler` OpenTelemetry.
