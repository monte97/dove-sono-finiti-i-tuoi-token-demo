"""Il comando `strati`: run, replay, riepilogo, misure, schema, righe, segnali, controllo, cruscotto."""
import argparse
import hashlib
import json
from pathlib import Path

from dotenv import load_dotenv

from . import esecuzione as esecuzione_mod
from . import registrazioni as registrazioni_mod
from .analisi import controllo as controllo_mod
from .analisi import misure
from .analisi import schema as schema_mod
from .analisi import segnali as segnali_mod
from .cruscotto import invio, verifica
from .impostazioni import Impostazioni, imposta
from .righe import codice, righe
from .stampa import mostra

QUI = Path(__file__).resolve().parent.parent

_CORREZIONI = {"istruzioni": 1, "filtro": 2, "dialogo": 3}


def _opzioni_run(p: argparse.ArgumentParser) -> None:
    p.add_argument("--strato", type=int, choices=range(6), default=0)
    p.add_argument("--guasto", action="store_true")
    p.add_argument("--correzione", choices=tuple(_CORREZIONI),
                   help="istruzioni: coordina chiede ad avvisi la sala della sessione; filtro: leggi_avvisi "
                        "restituisce solo gli avvisi di quella sala; dialogo: avvisi puo' chiedere a programma")
    p.add_argument("--maschera", action="store_true", help="solo con strato 5: l'email non esce dagli span")
    p.add_argument("--produzione", action="store_true", help="dallo strato 2: il riassunto della richiesta sulla radice")
    p.add_argument("--otlp", metavar="URL", help="esporta gli span via HTTP (implica produzione)")


def _prepara(a) -> tuple[Impostazioni, bool]:
    produzione, otlp = a.produzione or bool(a.otlp), a.otlp
    if a.maschera and a.strato != 5:
        raise SystemExit("--maschera serve allo strato 5, dove il contenuto entra negli span")
    if produzione and a.strato < 2:
        raise SystemExit("--produzione serve dallo strato 2, dove c'e' la radice della richiesta")
    correzione = _CORREZIONI.get(a.correzione, 0)
    guasto = a.guasto or correzione > 0  # la correzione ha senso solo nella giornata piena
    return Impostazioni(strato=a.strato, correzione=correzione, maschera=a.maschera,
                        produzione=produzione, otlp=otlp), guasto


def _run(a) -> int:
    i, guasto = _prepara(a)
    imposta(i)
    cartella = registrazioni_mod.cartella_della_run(i)
    mostra(esecuzione_mod.esegui(guasto, cartella))
    return 0


def _banco(a) -> int:
    i, guasto = _prepara(a)
    imposta(i)
    cartella = registrazioni_mod.cartella_della_run(i)
    esecuzione_mod.concludi_banco(a.n, *esecuzione_mod.esegui_banco(a.n, guasto, cartella))
    return 0


def _replay(a) -> int:
    reg = registrazioni_mod.leggi(Path(a.file))
    if not reg.get("richiesta") and reg.get("span"):
        # l'id stabile delle registrazioni vecchie: lo stesso che usa il cruscotto (invio.righe_ricostruite)
        reg["richiesta"] = hashlib.sha1(reg["span"][0]["trace"].encode()).hexdigest()[:8]
    if reg.get("richiesta"):
        print(f"richiesta {reg['richiesta']}")
    mostra(reg, registrata=True)
    return 0


def _riepilogo(a) -> int:
    misure.riepilogo(QUI / "registrazioni")
    return 0


def _misure(a) -> int:
    misure.misure(sorted(QUI.glob(f"registrazioni/strato-{a.n}*")))
    return 0


def _schema(a) -> int:
    schema_mod.mostra_schema(Path(a.cartella), a.modo, a.senza_strumenti)
    return 0


def _righe(a) -> int:
    righe()
    return 0


def _codice(a) -> int:
    print(codice(a.n))
    return 0


def _segnali(a) -> int:
    cartelle = [Path(x) for x in a.cartelle] or sorted(p for p in registrazioni_mod.RADICE.iterdir() if p.is_dir())
    for cartella in cartelle:
        regs = [json.loads(f.read_text()) for f in sorted(cartella.glob("*.json"))]
        for modo in ("guasto", "sana"):
            if mm := [r for r in regs if r["modo"] == modo]:
                segnali_mod.stampa(f"{cartella.name} · {modo}", segnali_mod.cruscotto(mm))
                print()
    return 0


def _controllo_stima(a) -> int:
    controllo_mod.stima(10)
    return 0


def _controllo_run(a) -> int:
    controllo_mod.lancia(a.n)
    return 0


def _controllo_confronta(a) -> int:
    controllo_mod.confronta(Path(a.cartella))
    return 0


def _cruscotto_invia(a) -> int:
    invio.invia([Path(x) for x in a.cartelle], a.otlp, a.tempo, a.ancora)
    return 0


def _cruscotto_verifica(a) -> int:
    return 1 if verifica.verifica([Path(x) for x in a.cartelle]) else 0


def _costruisci() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="La stessa risposta sbagliata, osservata uno strato alla volta.")
    comandi = p.add_subparsers(dest="comando", required=True)

    run = comandi.add_parser("run", help="una run")
    _opzioni_run(run)
    run.set_defaults(funzione=_run)

    banco = comandi.add_parser("banco", help="piu' run, una riga ciascuna")
    banco.add_argument("n", type=int, metavar="K")
    _opzioni_run(banco)
    banco.set_defaults(funzione=_banco)

    replay = comandi.add_parser("replay", help="una registrazione, come allora")
    replay.add_argument("file", metavar="F")
    replay.set_defaults(funzione=_replay)

    riepilogo = comandi.add_parser("riepilogo", help="una riga per strato e modo")
    riepilogo.set_defaults(funzione=_riepilogo)

    m = comandi.add_parser("misure", help="come ha deciso il grafo, cosa ha letto e riportato avvisi, token per agente")
    m.add_argument("n", type=int, metavar="N")
    m.set_defaults(funzione=_misure)

    s = comandi.add_parser("schema", help="il grafo delle chiamate fra agenti (strato 2+), in testo e Mermaid")
    s.add_argument("cartella", metavar="CARTELLA")
    s.add_argument("--modo", choices=("guasto", "sana"), help="solo le run di quel modo")
    s.add_argument("--senza-strumenti", action="store_true", help="nascondi gli strumenti dei dati (leggi_*)")
    s.set_defaults(funzione=_schema)

    r = comandi.add_parser("righe", help="righe di codice di ogni strato")
    r.set_defaults(funzione=_righe)

    c = comandi.add_parser("codice", help="le righe di uno strato, pulite per le slide")
    c.add_argument("n", type=int, choices=range(6), metavar="N")
    c.set_defaults(funzione=_codice)

    seg = comandi.add_parser("segnali", help="cinque segnali da cruscotto dalle registrazioni")
    seg.add_argument("cartelle", nargs="*", metavar="C")
    seg.set_defaults(funzione=_segnali)

    controllo = comandi.add_parser("controllo", help="il banco breve della settimana del talk")
    controllo_comandi = controllo.add_subparsers(dest="azione", required=True)
    stima = controllo_comandi.add_parser("stima", help="cosa verrebbe lanciato e quanto costa, senza chiamare l'API")
    stima.set_defaults(funzione=_controllo_stima)
    controllo_run = controllo_comandi.add_parser("run", help="poche run per caso, poi il confronto")
    controllo_run.add_argument("n", type=int, metavar="N")
    controllo_run.set_defaults(funzione=_controllo_run)
    confronta = controllo_comandi.add_parser("confronta", help="solo il confronto, su run gia' fatte")
    confronta.add_argument("cartella", metavar="CARTELLA")
    confronta.set_defaults(funzione=_controllo_confronta)

    cruscotto = comandi.add_parser("cruscotto", help="rimanda le registrazioni a Tempo/Loki/Prometheus e verifica")
    cruscotto_comandi = cruscotto.add_subparsers(dest="azione", required=True)
    invia = cruscotto_comandi.add_parser("invia", help="rimanda le registrazioni, con orari spostati ad adesso")
    invia.add_argument("cartelle", nargs="+", metavar="C")
    invia.add_argument("--otlp", default="http://localhost:4418", metavar="URL")
    invia.add_argument("--tempo", default="http://localhost:3210", metavar="URL")
    invia.add_argument("--ancora", action="store_true", help="rimanda anche se la cartella e' gia' in Tempo")
    invia.set_defaults(funzione=_cruscotto_invia)
    ver = cruscotto_comandi.add_parser("verifica", help="confronta il cruscotto con i segnali")
    ver.add_argument("cartelle", nargs="+", metavar="C")
    ver.set_defaults(funzione=_cruscotto_verifica)

    return p


def main(argv: list[str] | None = None) -> int:
    """Esegue un sottocomando e torna il codice di uscita."""
    load_dotenv(QUI / ".env")
    a = _costruisci().parse_args(argv)
    return a.funzione(a)
