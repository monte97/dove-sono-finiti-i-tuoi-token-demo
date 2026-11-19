# Il caso

Il caso è costruito e il guasto è messo apposta. Le decisioni del modello no: quelle sono registrate da run
vere con Claude Haiku 5.5.

## Il criterio

Nessun componente sbaglia rispetto al proprio contratto: niente retry, fallback, eccezioni o attese messi
apposta. Nessun componente ha un indizio locale che qualcosa sia andato storto, quindi non c'è un flag da
propagare. La causa sta nella composizione dei rami, e si vede solo guardandoli insieme nella stessa trace.

## La domanda

DevFest Immaginario 2026. Giulia Rossi (giulia.rossi@example.com) chiede: «A che ora è il workshop Kubernetes
da zero?». Il programma, pubblicato ieri sera, dice oggi alle 15:00 in sala B. Stamattina la sala B è stata
chiusa dalle 15:00 per manutenzione e le sessioni del pomeriggio in sala B iniziano un'ora prima. Lo sa solo un
avviso, e l'avviso parla della sala B senza nominare il workshop. La risposta giusta, in quella giornata, è 14:00.

Il caso sta in `osservare_a_strati/evento/`: programma, sale, generatore degli avvisi e domanda.

## Le due giornate

- `sana`, la giornata tranquilla: 3 pagine di avvisi, nessuno sulla sala B. Risposta giusta: 15:00.
- `guasto`, la giornata piena (`--guasto`): 40 pagine di avvisi plausibili, con quello sulla sala B a metà.
  Risposta giusta: 14:00. Il sistema risponde 15:00.

## Gli agenti

Gli agenti sono cinque. `coordina` è l'orchestratore e ha come strumenti gli altri quattro:

| agente | cosa fa |
|---|---|
| `programma` | `leggi_programma`: giorno, ora e sala dal programma pubblicato |
| `sale` | `leggi_sale`: sala, piano e capienza dal database delle sale, senza orario |
| `avvisi` | `leggi_avvisi`: tutte le comunicazioni di oggi, tutte le pagine in una chiamata. Deve riportare in al massimo tre righe quelle più importanti per la richiesta |
| `valida` | controlla la risposta contro il contesto che riceve; consiglia, non impone |

Chi chiamare, in che ordine e con quali parole lo decide il modello. Quando chiede più strumenti nello stesso
giro, girano in parallelo. Qui sta la causa: `avvisi` riceve una richiesta sul workshop, non sa che è in sala B,
e l'avviso sulla sala B per lui è uno fra tanti. Non lo riporta. `coordina` compone «15:00, sala B» e `valida`
approva. Nessuno ha sbagliato, e i token in ingresso stanno quasi tutti in `avvisi`.

Gli agenti si chiamano anche fra loro (`programma` ha `sale`, `valida` ha `programma` e `avvisi`): il dettaglio e la
guardia contro i cicli stanno in [convenzioni.md](convenzioni.md#agenti-che-si-chiamano).

## La correzione

Due passi, da misurare uno dopo l'altro:

- `--correzione istruzioni`: solo istruzioni a `coordina`, che deve chiedere ad `avvisi` le comunicazioni sulla sala
  della sessione dopo averla saputa. I rami non sono più tutti nello stesso giro.
- `--correzione filtro`: in più `leggi_avvisi` ha un parametro obbligatorio `sala` e restituisce solo gli
  avvisi di quella sala, una pagina.

C'è poi un'alternativa alle due, che non le include: `--correzione dialogo`, dove `avvisi` ha anche l'agente
`programma` come strumento.

Si guardano correttezza e token. Una volta vista la causa, la correzione è banale. I numeri delle tre stanno in
[banco/README.md](banco/README.md).

## I tre esiti

Nella giornata piena una risposta è `giusta`, `avvisata` o `sbagliata`; le regole stanno in
[banco/README.md](banco/README.md#i-tre-esiti) e il rilevatore in `osservare_a_strati/valutazione.py`.

## Il sistema precedente

La versione con tre agenti in fila (una sola fonte che serviva un dato vecchio) sta nel tag
git `tre-agenti-in-fila`, con le sue registrazioni. La pipeline fissa, la variante in cui un agente chiama
l'altro come strumento e il tool runner dell'SDK stanno nel tag `spike-a-b`. Il banco del sistema precedente non è nel repo
pubblico.
