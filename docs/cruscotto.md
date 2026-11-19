# Cruscotto, misure e banco

## Il cruscotto

I segnali su Grafana, letti da Tempo con TraceQL, i log correlati letti da Loki e le metriche dei token in Prometheus:
dallo span di uno strumento si salta alle sue righe di log (stesso trace id), da una riga di log alla sua trace, da un
exemplar dell'istogramma alla trace della richiesta. Un collector riceve OTLP HTTP e smista span a Tempo, log a Loki e
metriche al ricevitore OTLP di Prometheus (acceso con `--web.enable-otlp-receiver`, exemplar con
`--enable-feature=exemplar-storage`). Le porte stanno fuori da 3000, 3100, 3200, 4317/4318 e 9090: Grafana su 3377,
Tempo su 3210, Loki su 3110, Prometheus su 3990, OTLP HTTP su 4418.

```bash
docker compose -f cruscotto/compose.yaml up -d
strati cruscotto invia registrazioni/strato-5 registrazioni/strato-5-correzione   # span e log, come appena finiti
strati cruscotto verifica registrazioni/strato-5 registrazioni/strato-5-correzione   # cruscotto contro strati segnali
open "http://localhost:3377/d/segnali?var-cartella=strato-5&var-modo=guasto"
open "http://localhost:3377/d/token?var-cartella=strato-5&var-modo=guasto&var-richiesta=7923fcc3"   # la richiesta di Giulia
```

Il cruscotto «I token, per agente» (`token`) legge l'istogramma e i contatori da Prometheus e le righe per chiamata da
Loki. Le registrazioni del banco del 5/11 sono di prima delle righe per chiamata e delle metriche: `strati cruscotto
invia` le rifà dagli span della stessa run (`osservare_a_strati.analisi.span.chiamate_dagli_span`), con le cifre di
quella run, l'id della richiesta stabile (dalla trace originale: la richiesta di Giulia,
`strato-5/20261105-202614-guasto.json`, è `7923fcc3`) e gli exemplar sulle trace rimandate. Sul banco del 5/11,
strato 5, giornata piena: avvisi spende 866.266 token su 1.346.654 (64%); in una richiesta 17 mila token in 11
richieste, circa 34 mila in 18, 52 mila in una, cioè una, due o tre volte.

Le metriche TraceQL contano span, non richieste: per questo ogni richiesta porta i suoi fatti sullo span in
cima, `invoke_workflow` (`richiesta.forma`, `richiesta.costo_microusd`, `richiesta.quota_avvisi_pct`,
`richiesta.pagine_avvisi`). Il cruscotto guarda l'ultima ora, e `strati cruscotto invia` sposta gli orari delle
registrazioni ad adesso, log compresi (ogni log tiene il proprio orario, dentro il suo span): dopo un'ora si rimandano.
`banco.cartella` e `banco.modo` servono solo a filtrare le run della demo.

## Le misure

Una run non basta: il comportamento di un agente è una distribuzione. Il banco è di 30 run per strato e per
caso.

```bash
strati riepilogo        # una riga per cartella e modo: risposte giuste, avvisate e sbagliate, tempi, token, costo
strati misure 5         # rami nello stesso giro, cosa riporta avvisi, verdetti di valida, token e costo per agente, quota delle riletture
strati segnali registrazioni/strato-5 registrazioni/strato-5-correzione   # i segnali, dai soli span
```

`strati segnali` calcola i segnali di «Lunedì, in produzione» leggendo solo gli span, come farebbe un backend: la forma
dell'albero, il costo per richiesta alla mediana e al 95° percentile, la quota di `avvisi` sui token, le pagine di
avvisi lette nel ramo di `coordina` (i ricontrolli sono contati a parte, `pagine_ricontrolli`), quanto spesso `valida`
approva.

## Rifare le run e il banco

Servono una chiave Anthropic e un po' di spesa. Il costo reale di ogni run è nella sua fattura, dentro la
registrazione, e `strati riepilogo` stampa la somma. Per tutto il banco il tetto indicativo è 5 $.

```bash
python3.14 -m venv .venv && .venv/bin/pip install -r requirements.txt -e .
echo "ANTHROPIC_API_KEY=..." > .env
strati run --strato 3 --guasto                      # una run, stampata come il replay
strati banco 10 --strato 5 --guasto                 # dieci run, una riga ciascuna
strati run --strato 5 --correzione istruzioni       # il primo passo della correzione
strati run --strato 5 --correzione filtro           # ...e il secondo
strati run --strato 5 --guasto --maschera           # uno SpanProcessor toglie l'email dagli span
strati run --strato 5 --guasto --otlp http://localhost:4418/v1/traces   # dal vivo verso il cruscotto
```

Il banco completo, 30 run per modo (`sana`, `guasto`, `correzione`, `correzione completa`, `correzione dialogo`) e per
strato:

```bash
for N in 0 1 2 3 4 5; do
  strati banco 30 --strato $N
  strati banco 30 --strato $N --guasto
  strati banco 30 --strato $N --correzione istruzioni
  strati banco 30 --strato $N --correzione filtro
  strati banco 30 --strato $N --correzione dialogo
done
```

Ogni run finisce in `registrazioni/strato-N` più il suffisso del caso (`-correzione`, `-correzione-completa`,
`-correzione-dialogo`, `-maschera`). Prima di salvare, e di stampare, `anthropic.organization.id`,
`anthropic.workspace.id` e `anthropic.request.id` diventano `"oscurato"`. Le registrazioni dello strato 5 contengono
prompt, risposte e riassunto del ragionamento, e quindi l'email dell'utente (qui finta): in un sistema vero il
contenuto va filtrato prima che esca dal processo. Quali righe del banco alimentano quali numeri sta in
[banco/README.md](banco/README.md).

Il controllo della settimana del talk fa poche run per caso in una cartella sua e le confronta con il banco:

```bash
strati controllo stima               # cosa lancerebbe e quanto costa, senza chiamare l'API
strati controllo run 10              # dieci run per caso, poi il confronto
strati controllo confronta controllo/AAAA-MM-GG
```

Il confronto finisce con le soglie dello strato 5 senza correzione, cioè quando la storia regge:

| | Banco (30 run) | Controllo (10 run) |
|---|---|---|
| giornata piena, risposte giuste | nessuna | al massimo 1 |
| giornata piena, sbagliate e silenziose | almeno due terzi | almeno 5 |
| giornata tranquilla, giuste | tutte | tutte |

Il banco del 5/11 sta dentro: 0 giuste e 22 sbagliate su 30 nella giornata piena, 30 giuste su 30 nella
tranquilla. Le 8 risposte che non sono sbagliate avvertono l'utente: in 7 è `avvisi` a riportare l'avviso a
`coordina` (in 6 alla prima domanda, in 1 alla seconda), quando `coordina` chiede delle variazioni di orario o di sala;
quando chiede solo del workshop, `avvisi` risponde «Nessun avviso.». Il ricontrollo di `valida` conferma l'errore in 12
run e lo scopre da solo in una. Se il controllo esce dalle soglie, il modello dietro l'alias è cambiato: si rifà il
banco e si aggiornano i numeri.

## I diciassette alberi

`docs/banco/diciassette-alberi/` è un'elaborazione delle registrazioni, rifatta dai comandi del repo: la stessa domanda di Giulia trenta volte, nella giornata piena dello strato 5, dà
diciassette forme diverse dell'albero delle chiamate. `forme.tsv` è l'uscita di `strati misure 5` (quante volte,
forma), `diciassette-alberi.png` la disegna: un riquadro per forma, un colore per agente, il fondo arancio chiaro
raccoglie le chiamate fatte insieme, in parallelo.
