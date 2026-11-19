# Le registrazioni

Sono le run vere del banco, fatte il 5/11/2026 con Claude Haiku 5.5 (`claude-haiku-5-5`), tranne `strato-5-maschera`
(7/11/2026). Il file si chiama
`AAAAMMGG-HHMMSS-modo.json`, dove `modo` è `sana` o `guasto`; nella stessa cartella convivono le due giornate, e il
campo `modo` dentro la registrazione le distingue. Una registrazione contiene domanda, risposta, log, fattura,
secondi, span e log OpenTelemetry.

| cartella | run | cosa contiene |
|---|---|---|
| `strato-0` | 60 | 30 `sana` e 30 `guasto` dello strato 0 |
| `strato-1` | 60 | 30 `sana` e 30 `guasto` dello strato 1 |
| `strato-2` | 60 | 30 `sana` e 30 `guasto` dello strato 2 |
| `strato-3` | 60 | 30 `sana` e 30 `guasto` dello strato 3 |
| `strato-4` | 60 | 30 `sana` e 30 `guasto` dello strato 4 |
| `strato-5` | 60 | 30 `sana` e 30 `guasto` dello strato 5 |
| `strato-5-correzione` | 30 | la correzione `istruzioni`, giornata piena |
| `strato-5-correzione-completa` | 30 | la correzione `filtro`, giornata piena |
| `strato-5-correzione-dialogo` | 30 | la correzione `dialogo`, giornata piena |
| `strato-5-maschera` | 10 | lo strato 5 con la maschera dell'email, giornata piena, 7/11/2026 |

La run che usa il talk è `strato-5/20261105-202614-guasto.json`, la richiesta di Giulia con id `7923fcc3` (le prime
otto cifre dello sha1 dell'id della trace originale, come le calcola `strati cruscotto invia`). Si rigioca senza chiave:

```bash
strati replay registrazioni/strato-5/20261105-202614-guasto.json
```

Le registrazioni non si modificano e non si rigenerano. I comandi che le leggono sono in [docs/cruscotto.md](../docs/cruscotto.md) e in
[docs/banco/README.md](../docs/banco/README.md).
