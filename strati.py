"""La stessa risposta sbagliata, osservata uno strato alla volta.

Cinque agenti. `coordina` e' l'orchestratore: ha come strumenti gli agenti `programma`, `sale`, `avvisi` e
`valida` e decide lui chi chiamare, in che ordine, cosa passare e quando rispondere. `programma`, `sale` e
`avvisi` leggono ciascuno una fonte con uno strumento (`leggi_programma`, `leggi_sale`, `leggi_avvisi`),
`valida` controlla una risposta prima che arrivi all'utente. Nessun componente e' rotto: il programma di
ieri sera dice 15:00 sala B, e solo un avviso di stamattina sulla sala B dice che la sessione e' un'ora prima.

`--guasto` (modo "guasto" nelle registrazioni) e' la giornata piena: 40 pagine di avvisi, quello sulla sala B a
meta'. Senza `--guasto` (modo "sana") e' la giornata tranquilla: 3 pagine, niente sulla sala B.

Strati (ognuno contiene i precedenti):
  0  oggi: una riga di log per ogni chiamata al modello (agente e token) e la fattura, niente OpenTelemetry
  1  le metriche dei token e l'SDK: contatori per chiamata, un istogramma per agente in ogni richiesta, e la
     strumentazione nativa di anthropic
  2  gli agenti: span invoke_workflow, invoke_agent e gli archi fra agenti, scritti a mano
  3  lo strumento: span execute_tool con argomenti e risultato
  4  i dati letti: da dove viene il dato e quanto
  5  il contenuto: content_mode "content" (messaggi e ragionamento riassunto)

  python strati.py --strato 3 --guasto             una run
  python strati.py --strato 3 --guasto --banco 5   cinque run, una riga ciascuna
  python strati.py --strato 5 --correzione-dialogo avvisi puo' chiedere a programma (ricalcola la sala da solo)
  python strati.py --replay registrazioni/strato-3/<file>.json
  python strati.py --riepilogo                     una riga per strato e modo
  python strati.py --misure 5                      come ha deciso il grafo, cosa ha letto e riportato avvisi, token per agente
  python strati.py --righe                         righe di codice di ogni strato

Le righe che esistono solo per osservare finiscono con il marcatore dello strato (s0 ... s5 dopo il cancelletto).
La pipeline fissa, la variante A (agente come strumento) e il tool runner sono nel tag git spike-a-b.
"""

import argparse
import datetime as dt
import json
import statistics
from pathlib import Path

from dotenv import load_dotenv
from osservare_a_strati import esecuzione as esecuzione_mod, registrazioni as registrazioni_mod
from osservare_a_strati.agenti.ciclo import (CATENA, PROFONDITA_MAX, agente, chiama_agente, ciclo, controlla_catena,
                                             esegui_chiamate, esegui_strumento, richiesta_di_verifica)
from osservare_a_strati.agenti.prompt import (CORREZIONE_AVVISI, CORREZIONE_COORDINA, CORREZIONE_DIALOGO,
                                              DESCRIZIONI, ISTRUZIONI, agenti_strumento, istruzioni_coordina, schemi,
                                              versione, versione_prompt)
from osservare_a_strati.agenti.strumenti import leggi_dato
from osservare_a_strati.esecuzione import concludi_banco, esegui, esegui_banco
from osservare_a_strati.evento.avvisi import (AVVISO_ALLARME, AVVISO_CHIAVE, AVVISI_PER_PAGINA, PAGINA_AVVISO,
                                              PAGINE_PIENA, PAGINE_TRANQUILLA, SEME_AVVISI, _MODELLI, _ORE, _voce, avvisi)
from osservare_a_strati.evento.dati import (AVVISI_AGGIORNATI, DOMANDA, PROGRAMMA, PUBBLICATO, SALE, SESSIONE_SALA,
                                            _trova, sala_normale)
from osservare_a_strati.modello import LISTINO, MAX_GIRI, MODEL, PENSIERO, costo
from osservare_a_strati.valutazione import (APPROVA, AVVISI_CAUSA, AVVISI_NEGA, AVVISI_SALA_B, CHIEDE_VARIAZIONI,
                                            CLASSI_DOMANDA, ESITI, _CONFINE_CLAUSOLA, _QUATTORDICI_POSSIBILE,
                                            _QUINDICI_SUPERATO, _avverte, _clausole, approva, classe_domanda,
                                            riporta_avviso, valuta)
from osservare_a_strati.impostazioni import NOMI_CORREZIONE, Impostazioni, attuali, con, imposta
from osservare_a_strati.osservabilita import log as osservabilita_log
from osservare_a_strati.osservabilita import metriche, tracce
from osservare_a_strati.osservabilita.client import cliente
from osservare_a_strati.osservabilita.log import (CAMPI_RIGA, LOG, Righe, fai_log, logfmt, processore_otlp_log,
                                                  url_log)
from osservare_a_strati.osservabilita.metriche import (CONFINI_TOKEN, fai_metriche, leggi_metriche, memoria_metriche,
                                                       metriche_in_dict, url_metriche)
from osservare_a_strati.osservabilita.tracce import (EMAIL, VERSIONE, MascheraEmail, fai_provider, processore_otlp,
                                                     senza_email)
from osservare_a_strati.registrazioni import (ID_ACCOUNT, RADICE, cartella_della_run, in_dict, leggi, log_in_dict)  # noqa: F401
from osservare_a_strati.analisi.misure import (  # noqa: F401
    MINIMO_MISURE, banco, esito, misura, misure, riepilogo, tabella_domande)
from osservare_a_strati.analisi.schema import ORDINE_NODI, mostra_schema, schema  # noqa: F401
from osservare_a_strati.analisi.span import (  # noqa: F401
    SCARTO_GIRO_S, agente_di, archi, archi_della_run, attr, avvisi_dopo_sala, chiamate_dagli_span, cicli,
    costo_per_agente, dialogo, dialogo_riporta, domande_ad_avvisi, figli_arco, grafo, in_ordine, pagine_avvisi,
    pagine_ricontrolli, per_trace, profondita_agenti, quota_avvisi, quota_riletture, sale_da_due, stesso_giro,
    strumenti, token, token_per_agente, verdetti)
from osservare_a_strati.righe import codice, righe
from osservare_a_strati.stampa import (  # noqa: F401
    COLORI, albero, breve, c, cascata, colore, con_email, contenuto, mostra, mostra_metriche, ms, verbale)


QUI = Path(__file__).parent
load_dotenv(QUI / ".env")

_MODULI_DINAMICI = {
    "memoria": (tracce, "memoria"),
    "RISORSA": (tracce, "RISORSA"),
    "memoria_log": (osservabilita_log, "memoria_log"),
    "_handler": (osservabilita_log, "_handler"),
    "_provider_log": (osservabilita_log, "_provider_log"),
    "TOKEN_IN": (metriche, "TOKEN_IN"),
    "TOKEN_OUT": (metriche, "TOKEN_OUT"),
    "TOKEN_AGENTE": (metriche, "TOKEN_AGENTE"),
    "provider": (metriche, "provider"),
    "_provider_metriche": (metriche, "provider"),
}


def __getattr__(nome):
    """I nomi spostati restano leggibili da qui, sempre dal modulo che li possiede."""
    if nome in _MODULI_DINAMICI:
        modulo, campo = _MODULI_DINAMICI[nome]
        return getattr(modulo, campo)
    raise AttributeError(f"module {__name__!r} has no attribute {nome!r}")



if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--strato", type=int, choices=range(6), default=0)
    p.add_argument("--guasto", action="store_true")
    p.add_argument("--correzione", action="store_true", help="coordina chiede ad avvisi la sala della sessione")
    p.add_argument("--correzione-completa", action="store_true", help="...e leggi_avvisi restituisce solo gli avvisi di quella sala")
    p.add_argument("--correzione-dialogo", action="store_true", help="avvisi puo' chiedere a programma giorno, ora e sala (alternativa alle altre due)")
    p.add_argument("--maschera", action="store_true", help="solo con --strato 5: l'email non esce dagli span")
    p.add_argument("--produzione", action="store_true", help="dallo strato 2: il riassunto della richiesta sulla radice")
    p.add_argument("--otlp", metavar="URL", help="esporta gli span via HTTP (implica --produzione)")
    p.add_argument("--banco", type=int, default=0)
    p.add_argument("--replay")
    p.add_argument("--riepilogo", action="store_true")
    p.add_argument("--misure", type=int, metavar="N", help="le misure della giornata piena e della tranquilla in uno strato")
    p.add_argument("--schema", metavar="CARTELLA", help="il grafo delle chiamate fra agenti sulle registrazioni (strato 2+), in testo e Mermaid")
    p.add_argument("--modo", choices=("guasto", "sana"), help="con --schema: solo le run di quel modo")
    p.add_argument("--senza-strumenti", action="store_true", help="con --schema: nascondi gli strumenti dei dati (leggi_*)")
    p.add_argument("--righe", action="store_true")
    p.add_argument("--codice", type=int, choices=range(6), metavar="N", help="le righe di uno strato, pulite per le slide")
    a = p.parse_args()
    if a.schema:
        mostra_schema(Path(a.schema), a.modo, a.senza_strumenti)
    elif a.righe:
        righe()
    elif a.codice is not None:
        print(codice(a.codice))
    elif a.misure is not None:
        misure(sorted(QUI.glob(f"registrazioni/strato-{a.misure}*")))
    elif a.riepilogo:
        riepilogo(QUI / "registrazioni")
    elif a.replay:
        mostra(registrazioni_mod.leggi(Path(a.replay)), registrata=True)
    else:
        if a.maschera and a.strato != 5:
            raise SystemExit("--maschera serve allo strato 5, dove il contenuto entra negli span")
        produzione, otlp = a.produzione or bool(a.otlp), a.otlp
        if produzione and a.strato < 2:
            raise SystemExit("--produzione serve dallo strato 2, dove c'e' la radice della richiesta")
        maschera = a.maschera
        correzione = 3 if a.correzione_dialogo else 2 if a.correzione_completa else 1 if a.correzione else 0
        a.guasto = a.guasto or correzione > 0  # la correzione ha senso solo nella giornata piena
        i = Impostazioni(strato=a.strato, correzione=correzione, maschera=maschera, produzione=produzione, otlp=otlp)
        imposta(i)
        cartella = registrazioni_mod.cartella_della_run(i)
        if a.banco:
            esecuzione_mod.concludi_banco(a.banco, *esecuzione_mod.esegui_banco(a.banco, a.guasto, cartella))
        else:
            mostra(esecuzione_mod.esegui(a.guasto, cartella))
