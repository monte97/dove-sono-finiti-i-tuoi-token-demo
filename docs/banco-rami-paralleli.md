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
  .venv/bin/python strati.py --strato $N --correzione-dialogo --banco 30   # correzione dialogo
done
```

Le cartelle risultanti sono `registrazioni/strato-N`, `strato-N-correzione`, `strato-N-correzione-completa` e `strato-N-correzione-dialogo`;
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
| Correzione dialogo: correttezza e costo | `[banco]` | `.venv/bin/python strati.py --misure 5` (cartella `strato-5-correzione-dialogo`); `.venv/bin/python segnali.py registrazioni/strato-5-correzione-dialogo`. È un'alternativa alle altre due (non le include): `avvisi` ha anche l'agente `programma` come strumento |
| Run in cui `avvisi` chiede a `programma`, e poi riporta l'avviso (solo dialogo) | `[banco]` | `.venv/bin/python strati.py --misure 5` (righe `avvisi chiede a programma` e `...e poi avvisi riporta l'avviso`, solo nella cartella `-correzione-dialogo`) |
| Run in cui `sale` è chiamato da due chiamanti (`coordina` e `programma`) | `[banco]` | `.venv/bin/python strati.py --misure 5` (riga `sale chiamato da due chiamanti diversi`) |
| Run in cui `valida` ricontrolla con `avvisi`, e se la risposta riporta l'avviso | `[banco]` | `.venv/bin/python strati.py --misure 5` (righe `valida richiede ad avvisi` e `...e la risposta di avvisi riporta l'avviso`) |
| Run in cui `valida` ricontrolla con `programma` | `[banco]` | `.venv/bin/python strati.py --misure 5` (riga `valida richiede a programma`) |
| Profondità massima dell'albero e numero di span | `[banco]` | `.venv/bin/python strati.py --misure 5` (righe `massimi: profondità ... span ...` e `mediane: profondità ... · span ...`) |
| Volte in cui la guardia contro i cicli ha rifiutato una chiamata | `[banco]` | `.venv/bin/python strati.py --misure 5` (riga `guardia dei cicli scattata`) |

`--misure 5` stampa insieme `strato-5`, `strato-5-correzione`, `strato-5-correzione-completa` e
`strato-5-correzione-dialogo`, ognuna con le giornate `guasto` e `sana` che contiene.

## Agenti che si chiamano

`programma` ha `sale` come strumento (per il piano), `valida` ha `programma` e `avvisi` (può ricontrollare alla fonte,
le istruzioni lo consigliano), e con `--correzione-dialogo` anche `avvisi` ha `programma`. Ogni chiamata fra agenti è un
arco `execute_tool <agente>` del chiamante con dentro `invoke_agent <agente>`, a qualsiasi livello.

Guardia contro i cicli: la catena di chiamata (chi ha chiamato chi, da `coordina`) viaggia in una variabile di contesto,
mai nel prompt. Un agente non può chiamare se stesso né uno già nella catena, e la catena ha al massimo 4 chiamate una
dentro l'altra (il ramo più lungo che serve è `coordina>valida>avvisi>programma>sale`). Se il modello ci prova, lo
strumento gli restituisce l'errore («<agente> è già nella catena di chiamata ...», `is_error`) e l'arco ha stato di errore
ed `error.type = ciclo`: è un errore vero del modello, non il meccanismo del guasto.

Con le chiamate annidate una run allo strato 5 ha più span: sul server finto, con `programma>sale` e i due ricontrolli
di `valida`, sono 44 contro 23 senza (oltre i 40 indicativi). Pagine di avvisi: `pagine_avvisi` (riga `pagine di avvisi lette da coordina`, `richiesta.pagine_avvisi`
nel cruscotto, `segnali.py`) conta solo le pagine lette da `leggi_avvisi` sotto l'arco di `avvisi` chiamato da `coordina`:
è il numero della slide, 40 nella giornata piena. `pagine_ricontrolli` (riga `pagine di avvisi nei ricontrolli`) conta le
letture sotto qualunque altro chiamante: i ricontrolli di `valida` e il dialogo.

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
