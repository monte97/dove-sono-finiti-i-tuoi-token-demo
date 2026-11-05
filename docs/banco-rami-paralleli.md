# Banco: i numeri della giornata piena

Scheletro della tabella dei numeri del talk. I valori sono `[banco]` finché il banco non è stato rifatto sul
sistema nuovo (cinque agenti, rami paralleli). `registrazioni/` parte vuota: il banco del sistema precedente sta in
`archivio/banco-2026-11-06/` (e nel tag `banco-2026-11-06`), fuori da `--riepilogo`, `--misure` e `segnali.py`.

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
| Costo per agente | `[banco]` | `.venv/bin/python strati.py --misure 5` (riga `costo per agente, $ (mediana)`: costo a `LISTINO` delle chiamate al modello di ogni agente) |
| Quota delle riletture | `[banco]` | `.venv/bin/python strati.py --misure 5` (riga `quota delle riletture`). Definizione: in ogni `invoke_agent`, ogni chiamata dopo la prima rilegge la conversazione fin lì; si sommano i token in ingresso della chiamata precedente, e si divide per i token in ingresso di tutta la richiesta |
| Esiti su 30, guasta: giusta / avvisata / sbagliata | `[banco]` | `.venv/bin/python strati.py --misure 5` (riga `guasto: n 30 · giusta ... · avvisata ... · sbagliata ...`) |
| Esiti su 30, sana: giusta / sbagliata | `[banco]` | `.venv/bin/python strati.py --misure 5` (riga `sana: n 30 · giusta ... · avvisata 0 · sbagliata ...`) |
| Run in cui `avvisi` omette l'avviso | `[banco]` | `.venv/bin/python strati.py --misure 5` (righe `leggi_avvisi ha restituito l'avviso sulla sala B` contro `avvisi lo riporta a coordina`) |
| Verdetti di `valida` | `[banco]` | `.venv/bin/python strati.py --misure 5` (riga `valida approva`); `.venv/bin/python segnali.py registrazioni/strato-5` |
| Run con i tre rami nello stesso giro | `[banco]` | `.venv/bin/python strati.py --misure 5` (riga `programma, sale, avvisi nello stesso giro`) |
| Forme dell'albero | `[banco]` | `.venv/bin/python strati.py --misure 5` (elenco `forme dell'albero`); `.venv/bin/python segnali.py registrazioni/strato-5` |
| Correzione, passo 1: correttezza e costo | `[banco]` | `.venv/bin/python strati.py --misure 5` (cartella `strato-5-correzione`); `.venv/bin/python segnali.py registrazioni/strato-5-correzione` |
| Correzione completa, passo 2: correttezza e costo | `[banco]` | `.venv/bin/python strati.py --misure 5` (cartella `strato-5-correzione-completa`); `.venv/bin/python segnali.py registrazioni/strato-5-correzione-completa` |

`--misure 5` stampa insieme `strato-5`, `strato-5-correzione` e `strato-5-correzione-completa`, ognuna con le
giornate `guasto` e `sana` che contiene.

## I tre esiti

Nella giornata piena una risposta è `giusta` se dà le 14:00 come orario (il 15:00 solo come orario in programma
superato), `avvisata` se dà le 15:00 ma avverte della chiusura della sala B o dell'anticipo, `sbagliata` se dà le
15:00 senza avvertimenti. Nella tranquilla: `giusta` se dà le 15:00 senza dire 14:00, `sbagliata` altrimenti. Il
rilevatore è `valuta()` in `strati.py`, con le regole e il limite noto (regex su frasi italiane) nel commento sopra.
Il cruscotto Grafana non mostra gli esiti: sono un conteggio del banco (`--misure`, `controllo.py`).

## Il fatto sull'SDK

L'SDK `anthropic` 1.15.0 (`_tracing.py`), verificato il 5/11/2026, scrive il contenuto solo come attributi di
span (`gen_ai.input.messages`, `gen_ai.output.messages`). Non produce eventi, log né metriche. I log correlati
dello strato 3 sono quelli dello strumento, scritti con il `logging` di Python ed esportati da un
`LoggingHandler` OpenTelemetry.
