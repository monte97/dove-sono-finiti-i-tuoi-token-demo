# Agenti che si chiamano

Branch: `rami-paralleli`, dopo il commit di taratura `945c7c5`. Continua il piano `2026-11-05-rami-paralleli.md`: Spec e Global Constraints di quel piano restano validi, con le modifiche qui sotto.

## Spec (aggiunte)

La storia non cambia: giornata piena, l'avviso indiretto sulla sala B, `avvisi` con il contratto ristretto («riporta solo gli avvisi che riguardano ciò che ti è stato chiesto, al massimo tre righe, senza supposizioni; se non ce ne sono, rispondi «Nessun avviso.»»), la risposta 15:00 approvata. Il criterio resta: nessun componente sbaglia rispetto al suo contratto, nessuno ha un indizio locale, la causa sta nella composizione.

Il sistema diventa movimentato: gli agenti si chiamano fra loro.

- `coordina` risponde con giorno, ora, sala **e piano**. Ha come strumenti `programma`, `sale`, `avvisi`, `valida`.
- `programma` ha come strumenti `leggi_programma` **e l'agente `sale`**: per il piano chiede a `sale`. Risponde con giorno, ora, sala e piano.
- `valida` ha come strumenti **gli agenti `programma` e `avvisi`**: può ricontrollare alla fonte prima di approvare. Le sue istruzioni lo consigliano, non lo impongono.
- `sale` e `avvisi` come oggi (`avvisi` con il contratto ristretto).
- Nuova correzione `--correzione-dialogo` (cartella `-correzione-dialogo`, valore `CORREZIONE = 3`): `avvisi` ha anche **l'agente `programma`** come strumento e le sue istruzioni dicono che può chiedergli giorno, ora e sala di una sessione. Niente altro cambia. Le correzioni 1 e 2 restano come sono.
- **Guardia contro i cicli:** un agente non può chiamare se stesso né un agente già presente nella sua catena di chiamata (la catena si porta nello `stato` per thread o negli argomenti interni, non nel prompt), e la catena ha profondità massima 4. Se il modello ci prova, lo strumento restituisce un errore esplicito («<agente> è già nella catena di chiamata») e lo span lo registra: è un errore vero del modello, non il meccanismo del guasto.
- Ogni chiamata fra agenti è lo stesso «agent as a tool» di oggi: `execute_tool <agente>` del chiamante (strato 2, con `gen_ai.agent.name` del chiamante e `gen_ai.transfer.target.name`), con dentro `invoke_agent <agente>`. Il parallelismo vale a ogni livello (`esegui_chiamate` già lo fa per ogni `ciclo`).

**Tre esiti** per ogni risposta finale, al posto di giusta/sbagliata:
- nella giornata piena: `giusta` se dà le 14:00 come orario (può citare le 15:00 solo come orario in programma superato, per esempio «non alle 15:00», «anticipato dalle 15:00», «rispetto alle 15:00 in programma»); `avvisata` se dà le 15:00 ma avverte della chiusura della sala B o dell'anticipo; `sbagliata` se dà le 15:00 senza nessun avvertimento;
- nella tranquilla: `giusta` se dà le 15:00 senza dire 14:00; `sbagliata` altrimenti.
I rilevatori sono funzioni con test in entrambe le direzioni su frasi realistiche (prendere spunto dalle risposte vere in `archivio/taratura-2026-11-05/`). Dove la regex non basta si sceglie il verso conservativo dichiarato in un commento, e il limite noto si documenta.

**Schema per le slide:** un comando `--schema CARTELLA` che legge le registrazioni (strato ≥2) e stampa il grafo delle chiamate fra agenti aggregato su tutte le run: per ogni arco chiamante → chiamato, in quante run compare e quante volte in totale; in evidenza i rimpalli (un agente chiamato da due chiamanti diversi nella stessa run; `valida` che richiama una fonte; `avvisi` che chiede a `programma`). Uscita in due forme: testo leggibile e un blocco Mermaid (`flowchart LR`) da incollare in una slide, con le etichette degli archi in italiano e i conteggi.

## Global Constraints (aggiunte)

- I conteggi nuovi entrano in `misura`/`misure` con lo strato minimo: run in cui `sale` è chiamato due volte (da chiamanti diversi), run in cui `valida` richiama `avvisi` e cosa gli risponde (`riporta_avviso`), run in cui `avvisi` chiede a `programma` (solo dialogo) e se poi riporta l'avviso, profondità massima dell'albero, numero di span. E i tre esiti.
- `segnali.py`, `controllo.py`, `verifica_cruscotto.py`, il cruscotto (`cruscotto/grafana/segnali.json`) e `docs/banco-rami-paralleli.md` si allineano ai tre esiti e al modo `correzione-dialogo` dove serve. `controllo.py` include il caso dialogo.
- Leggibilità: una run della giornata piena allo strato 5 deve restare indicativamente sotto 40 span; se si va oltre, annotarlo nel report con i numeri sul server finto.
- Il server finto di `test_strati.py` si estende per simulare le chiamate annidate (programma → sale, valida → programma e avvisi, avvisi → programma nel dialogo).

## Task 7: tre esiti e piano nella risposta

Tre esiti come nella Spec, in `strati.py` (esito, misura, misure, riepilogo), `segnali.py`, `controllo.py`, cruscotto e docs. Istruzioni di `coordina` e `programma` con il piano nella risposta. Test dei rilevatori in entrambe le direzioni.

## Task 8: agenti che si chiamano

`programma` → `sale`, `valida` → `programma` e `avvisi`, `--correzione-dialogo` con `avvisi` → `programma`, guardia contro i cicli, misure nuove. Test con il server finto esteso: parentela degli span a più livelli, parallelismo annidato, guardia, conteggi.

## Task 9: lo schema per le slide

`--schema CARTELLA` come nella Spec, con test su registrazioni finte e un esempio di uscita Mermaid nel README e in `docs/banco-rami-paralleli.md`.
