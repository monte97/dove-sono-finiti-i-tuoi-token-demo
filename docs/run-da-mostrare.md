# Le run da mostrare

Scelte dal banco del 5/11 (tag `banco-2026-11-05`), tutte allo strato 5. Ognuna si rivede con
`python strati.py --replay registrazioni/<cartella>/<file>`. Le run sono vere: Claude Haiku 5.5, nessuna ritoccata.

## La coppia del cuore: stessa domanda dell'utente, due domande fra agenti

È la coppia più interessante del banco. Giulia fa la stessa domanda. Quello che cambia è come `coordina` interroga
`avvisi`, e da lì cambia l'esito.

| | `strato-5/20261105-202614-guasto.json` | `strato-5/20261105-202946-guasto.json` |
|---|---|---|
| `coordina` chiede ad `avvisi` | «workshop Kubernetes da zero» | «Workshop "Kubernetes da zero": variazioni di orario o sala» |
| `avvisi` risponde | «Nessun avviso.» | l'avviso sulla sala B («chiusa dalle 15:00 … iniziano un'ora prima») |
| `valida` richiama `avvisi` con | «Workshop "Kubernetes da zero"» → «Nessun avviso.» | «… sala B, chiusura o variazioni di orario per oggi» → l'avviso |
| verdetto di `valida` | «… alle 15:00 in sala B, al piano 1. Verificato.» | «Non approvo la risposta così com'è …» |
| risposta all'utente | 15:00, sala B, «non ci sono avvisi»: **sbagliata e verificata due volte** | 15:00 con l'avviso della chiusura: **avvisata** |
| span · secondi · costo | 41 · 19,6 s · 0,0059 $ | 45 · 27,6 s · 0,0071 $ |

Sul banco questa differenza conta. In 7 delle 8 risposte avvisate, `avvisi` riporta l'avviso a `coordina` al primo
giro, perché la domanda nomina le variazioni di orario o di sala. Quando la domanda nomina solo il workshop,
`avvisi` risponde «Nessun avviso.», come il suo contratto chiede.

Gli screenshot di Grafana sono della run `202614` (cartella del talk, `talk/screenshot/2026-11-05-rami-paralleli/`).

## Le altre run della giornata piena

- **`valida` che scopre da sola: `strato-5/20261105-202457-guasto.json`** (52 span, 0,0072 $). È l'unica run in
  cui `avvisi` dice «Nessun avviso.» a `coordina` e poi riporta l'avviso al ricontrollo di `valida`. `coordina`
  scrive all'utente: «Il controllo di validazione ha segnalato un avviso sulla Sala B». Mostra che il ricontrollo
  può servire, una volta su 19.
- **Lo stesso errore a metà prezzo: `strato-5/20261105-202429-guasto.json`** (24 span, 0,0033 $). Nessun
  ricontrollo: `valida` approva senza richiamare nessuno. Ha la stessa risposta sbagliata della `202614` con metà
  degli span, quindi è un'altra forma dell'albero per la stessa domanda.

## La giornata tranquilla

- **`strato-5/20261105-201337-sana.json`** (41 span, 0,0029 $, il costo più vicino alla mediana). Le 15:00 sono
  giuste e `avvisi` legge 3 pagine. È il termine di paragone per il costo: la giornata piena costa circa il doppio.

## Le correzioni

- **Il filtro per sala nello strumento: `strato-5-correzione-completa/20261105-205907-guasto.json`** (50 span,
  0,0038 $). Risposta giusta, «alle 14:00 … e non alle 15:00 come da programma». Costa meno della giornata piena
  senza correzione, perché `avvisi` legge una pagina invece di 40.
- **Il dialogo fra agenti: `strato-5-correzione-dialogo/20261105-210915-guasto.json`** (33 span, 0,0044 $).
  `avvisi` chiede la sala a `programma`, poi riporta l'avviso. Risposta giusta, «alle 14:00 (anziché le 15:00 del
  programma)». È la più compatta delle run di dialogo. La mediana del dialogo è 72 span e 0,0092 $, quindi va
  detto che questa è una run fortunata.
- **Le istruzioni a `coordina`: `strato-5-correzione/20261105-203803-guasto.json`** (29 span, 0,0041 $).
  Risposta giusta, «alle 14:00 … anticipato di un'ora rispetto alle 15:00 previste dal programma».

Le correzioni portano tutte l'avviso all'utente, ma quasi sempre come avvertimento: giuste 5, 2 e 2 su 30. Le run
qui sopra sono fra le poche giuste, e sul palco va detto.
