# Convenzioni, agenti e limiti

## L'orchestratore e le convenzioni

L'arco fra agenti è strumentato come nel refinement «Agent as a tool» delle convenzioni GenAI
(`gen_ai.execute_tool.transfer.internal`, repo `open-telemetry/semantic-conventions-genai`, stato Development):
lo span `execute_tool {agente}` del chiamante, con `gen_ai.agent.name` del chiamante,
`gen_ai.transfer.mode = return_to_caller` e `gen_ai.transfer.target.name`, e dentro lo span `invoke_agent` del
chiamato.

## Agenti che si chiamano

`programma` ha `sale` come strumento (per il piano), `valida` ha `programma` e `avvisi` (può ricontrollare alla fonte,
le istruzioni lo consigliano), e con `--correzione dialogo` anche `avvisi` ha `programma`. Ogni chiamata fra agenti è un
arco `execute_tool <agente>` del chiamante con dentro `invoke_agent <agente>`, a qualsiasi livello.

Guardia contro i cicli: la catena di chiamata (chi ha chiamato chi, da `coordina`) viaggia in una variabile di contesto,
mai nel prompt. Un agente non può chiamare se stesso né uno già nella catena, e la catena ha al massimo 4 chiamate una
dentro l'altra (il ramo più lungo che serve è `coordina>valida>avvisi>programma>sale`). Se il modello ci prova, lo
strumento gli restituisce l'errore («<agente> è già nella catena di chiamata ...», `is_error`) e l'arco ha stato di errore
ed `error.type = ciclo`: è un errore vero del modello, non il meccanismo del guasto.

Con le chiamate annidate una run allo strato 5 ha più span: sul server finto, con `programma>sale` e i due ricontrolli
di `valida`, sono 44 contro 23 senza (oltre i 40 indicativi). Pagine di avvisi: `pagine_avvisi` (riga `pagine di
avvisi lette da coordina`, `richiesta.pagine_avvisi` nel cruscotto, `strati segnali`) conta solo le pagine lette da
`leggi_avvisi` sotto l'arco di `avvisi` chiamato da `coordina`: è il numero della slide, 40 nella giornata piena.
`pagine_ricontrolli` (riga `pagine di avvisi nei ricontrolli`) conta le letture sotto qualunque altro chiamante: i
ricontrolli di `valida` e il dialogo.

## Cosa questa demo non dice

- Le convenzioni GenAI di OpenTelemetry sono sperimentali: i nomi possono cambiare. L'SDK di Anthropic le usa a
  metà (lo span si chiama `anthropic.messages.create`, il motivo di fine sta in `anthropic.message.stop_reason`).
- Il costo è una stima: token per listino di Claude Haiku 5.5, letto il 23/10/2026. La fattura vera arriva dopo.
- `claude-haiku-5-5` è un alias senza snapshot datato: lo stesso nome può indicare un modello diverso domani.
  `strati controllo` serve a vedere se i numeri si sono spostati.
- Che i tre rami girino nello stesso giro lo decide il modello. Il banco misura quanto spesso succede, e il
  guasto dipende da quello.
- La demo non usa il prompt caching del provider: ogni giro rilegge tutto a prezzo pieno.

## Test

```bash
pytest -q    # controlli senza rete, contro un server finto; segnali, cruscotto e rimando a Tempo
```

I test girano sul server finto e sulle registrazioni finte: non chiamano l'API e non toccano le registrazioni del banco.
