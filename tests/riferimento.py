"""Rete di sicurezza del riordino: scrive su file le uscite della demo, controllo per controllo.

Uso: python tests/riferimento.py --adattatore vecchio|nuovo USCITA_DIR

L'adattatore `vecchio` importa strati, segnali e tempo dalla radice del repo. L'adattatore `nuovo` importa dal
pacchetto osservare_a_strati (arriva con i Task 3-7); finche' non c'e', solleva NotImplementedError. Il codice dei
controlli e' unico: cambia solo il dizionario di funzioni che ogni adattatore fornisce.
"""
import argparse
import contextlib
import io
import json
import os
import random
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))

os.environ.pop("NO_COLOR", None)  # lo stesso ambiente di oggi: i colori restano nell'uscita

REGISTRAZIONI = RADICE / "registrazioni"

SCHEMA_CARTELLE = (
    "strato-2", "strato-3", "strato-4", "strato-5",
    "strato-5-correzione", "strato-5-correzione-completa", "strato-5-correzione-dialogo",
)
MODI_SCHEMA = (None, "guasto", "sana")
INVIO_CARTELLE = ("strato-5", "strato-5-correzione")
ADESSO = 1_800_000_000.0


def cartelle_registrazioni() -> list[Path]:
    return sorted(p for p in REGISTRAZIONI.iterdir() if p.is_dir())


def registrazioni(cartella: Path) -> list[dict]:
    return [json.loads(f.read_text()) for f in sorted(cartella.glob("*.json"))]


def cattura(funzione, *args, **kwargs) -> str:
    with contextlib.redirect_stdout(io.StringIO()) as fuori:
        funzione(*args, **kwargs)
    return fuori.getvalue()


def scrivi(uscita: Path, relativo: str, testo: str):
    percorso = uscita / relativo
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(testo)


# --- gli adattatori: un dizionario di funzioni con gli stessi nomi per vecchio e nuovo ---

def adattatore_vecchio() -> dict:
    import segnali
    import strati
    import tempo
    from osservare_a_strati.impostazioni import Impostazioni, imposta
    from osservare_a_strati.osservabilita import metriche, tracce

    def fissa_risorsa():
        # La Resource di oggi prende un service.instance.id casuale a ogni processo: l'harness lo fissa, il codice no.
        from opentelemetry.sdk.resources import Resource
        risorsa = Resource.create({"service.name": "osservare-a-strati", "service.version": strati.VERSIONE,
                                   "service.instance.id": "00000000-0000-0000-0000-000000000000"})
        tracce.RISORSA = risorsa
        tempo.RISORSA = risorsa

    def prepara_metriche():
        imposta(Impostazioni(strato=5, otlp=None))  # l'harness puo' toccare le impostazioni; il codice della demo no
        metriche.fai_metriche()

    def forza_metriche():
        metriche.provider.force_flush()

    return {
        "fissa_risorsa": fissa_risorsa,
        "mostra": strati.mostra,
        "riepilogo": strati.riepilogo,
        "misure": strati.misure,
        "mostra_schema": strati.mostra_schema,
        "righe": strati.righe,
        "codice": strati.codice,
        "versione_prompt": strati.versione_prompt,
        "versione": strati.versione,
        "segnali_cruscotto": segnali.cruscotto,
        "segnali_stampa": segnali.stampa,
        "rimappa": tempo.rimappa,
        "in_otlp": tempo.in_otlp,
        "log_in_otlp": tempo.log_in_otlp,
        "righe_ricostruite": tempo.righe_ricostruite,
        "misura": tempo.misura,
        "prepara_metriche": prepara_metriche,
        "forza_metriche": forza_metriche,
        "leggi_metriche": strati.leggi_metriche,
    }


def adattatore_nuovo() -> dict:
    raise NotImplementedError(
        "adattatore nuovo: il pacchetto osservare_a_strati arriva con i Task 3-7; "
        "per ora il riferimento si genera solo con --adattatore vecchio")


# --- i controlli, uguali per tutti gli adattatori ---

def controllo_replay(ad: dict, uscita: Path):
    for cartella in cartelle_registrazioni():
        for f in sorted(cartella.glob("*.json")):
            reg = json.loads(f.read_text())
            scrivi(uscita, f"replay/{cartella.name}/{f.stem}.txt", cattura(ad["mostra"], reg, registrata=True))


def controllo_riepilogo(ad: dict, uscita: Path):
    scrivi(uscita, "riepilogo.txt", cattura(ad["riepilogo"], REGISTRAZIONI))


def controllo_misure(ad: dict, uscita: Path):
    for n in range(6):
        cartelle = sorted(RADICE.glob(f"registrazioni/strato-{n}*"))
        scrivi(uscita, f"misure-{n}.txt", cattura(ad["misure"], cartelle))


def nome_schema(cartella: str, modo: str | None, senza_strumenti: bool) -> str:
    return "schema-" + cartella + (f"-{modo}" if modo else "") + ("-senza" if senza_strumenti else "") + ".txt"


def controllo_schema(ad: dict, uscita: Path):
    for nome in SCHEMA_CARTELLE:
        cartella = REGISTRAZIONI / nome
        for modo in MODI_SCHEMA:
            for senza in (False, True):
                testo = cattura(ad["mostra_schema"], cartella, modo, senza)
                scrivi(uscita, nome_schema(nome, modo, senza), testo)


def controllo_segnali(ad: dict, uscita: Path):
    def esegui():
        for cartella in cartelle_registrazioni():
            regs = registrazioni(cartella)
            for modo in ("guasto", "sana"):
                if mm := [r for r in regs if r["modo"] == modo]:
                    ad["segnali_stampa"](f"{cartella.name} · {modo}", ad["segnali_cruscotto"](mm))
                    print()
    scrivi(uscita, "segnali.txt", cattura(esegui))


def controllo_invio(ad: dict, uscita: Path):
    ad["fissa_risorsa"]()  # il service.instance.id casuale non e' comportamento della demo: l'harness lo fissa
    ad["prepara_metriche"]()  # solo il lettore in memoria: niente collector, niente rete
    for nome in INVIO_CARTELLE:
        cartella = REGISTRAZIONI / nome
        for f in sorted(cartella.glob("*.json")):
            r = json.loads(f.read_text())
            random.seed(0)
            mappa = ad["rimappa"](r, ADESSO)
            span = [s.to_json() for s in ad["in_otlp"](r, cartella.name, ADESSO, mappa)]
            log = [l.to_json() for l in ad["log_in_otlp"](r, mappa, ad["righe_ricostruite"](r))]
            agenti = ad["misura"](r, mappa, cartella.name)
            ad["forza_metriche"]()
            metriche = ad["leggi_metriche"]()
            scrivi(uscita, f"invio/{cartella.name}/{f.stem}.json",
                   json.dumps({"span": span, "log": log, "misura": agenti, "metriche": metriche},
                              ensure_ascii=False, indent=1))


def controllo_righe(ad: dict, uscita: Path):
    scrivi(uscita, "righe.txt", cattura(ad["righe"]))


def controllo_codice(ad: dict, uscita: Path):
    for n in range(6):
        scrivi(uscita, f"codice-{n}.txt", ad["codice"](n))


def controllo_versione_prompt(ad: dict, uscita: Path):
    righe = []
    for c in range(4):
        righe += [f"correzione {c}", f"versione_prompt {ad['versione_prompt'](c)}",
                  "versione " + json.dumps(ad["versione"](c), ensure_ascii=False, sort_keys=True), ""]
    scrivi(uscita, "versione-prompt.txt", "\n".join(righe))


def controlli(ad: dict, uscita: Path) -> dict:
    return {
        "replay": lambda: controllo_replay(ad, uscita),
        "riepilogo": lambda: controllo_riepilogo(ad, uscita),
        "misure": lambda: controllo_misure(ad, uscita),
        "schema": lambda: controllo_schema(ad, uscita),
        "segnali": lambda: controllo_segnali(ad, uscita),
        "invio": lambda: controllo_invio(ad, uscita),
        "righe": lambda: controllo_righe(ad, uscita),
        "codice": lambda: controllo_codice(ad, uscita),
        "versione-prompt": lambda: controllo_versione_prompt(ad, uscita),
    }


ADATTATORI = {"vecchio": adattatore_vecchio, "nuovo": adattatore_nuovo}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--adattatore", choices=sorted(ADATTATORI), required=True)
    p.add_argument("uscita", type=Path)
    a = p.parse_args()
    ad = ADATTATORI[a.adattatore]()
    a.uscita.mkdir(parents=True, exist_ok=True)
    for nome, funzione in controlli(ad, a.uscita).items():
        print(nome)
        funzione()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
