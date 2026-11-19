"""Test di valutazione. Nati da test_strati.py e test_segnali.py, divisi per argomento."""
import contextlib
import io
import json
import tempfile
from pathlib import Path

from server_finto import *

from osservare_a_strati import valutazione as valutazione_mod
from osservare_a_strati.analisi import misure as misure_mod
from osservare_a_strati.analisi import span as span_mod
from osservare_a_strati.evento import avvisi as avvisi_mod


def test_tre_esiti_giornata_piena():
    v = lambda r: valutazione_mod.valuta(r, "guasto")
    # giuste: 14:00 come orario, il 15:00 solo come orario superato
    assert v("Oggi alle 14:00, sala B.") == "giusta"
    assert v("Il workshop è oggi in sala B, con orario probabilmente anticipato alle 14:00 rispetto alle 15:00 in programma.") == "giusta"
    assert v("Oggi alle 14:00 in sala B, non alle 15:00 come da programma.") == "giusta"
    assert v("Alle 14:00 in sala B (anticipato dalle 15:00 per la manutenzione).") == "giusta"
    assert v("Alle 14:00: la sala B chiude dalle 15:00 per manutenzione.") == "giusta"
    # avvisate: 15:00 come orario, ma con l'avvertimento
    assert v("Il workshop è oggi alle 15:00 in sala B, ma la sala B risulta chiusa dalle 15:00 per manutenzione elettrica, "
             "quindi potrebbe iniziare alle 14:00.") == "avvisata"
    assert v("È oggi alle 15:00 in Sala B (piano 1), ma c'è un avviso: sessioni un'ora prima, quindi probabilmente alle 14:00.") == "avvisata"
    assert v("Oggi alle 15:00 in sala B, ma la sala B è chiusa per manutenzione: chiedi allo staff.") == "avvisata"
    assert v("Alle 14:00, sala B; il programma indicava le 15:00.") == "giusta"
    assert v("Alle 14:00 in sala B, era alle 15:00 nel programma.") == "giusta"
    assert v("Alle 14:00 in sala B anziché alle 15:00.") == "giusta"
    assert v("Alle 14:00 in sala B, il programma diceva le 15:00.") == "giusta"
    # sbagliate: 15:00 senza avvertimenti, o nessun orario
    for frase in ("Oggi alle 15:00 in sala B, nessun avviso di chiusura o manutenzione.",
                  "Oggi alle 15:00 in sala B, non risulta che la sala sia chiusa.",
                  "Oggi alle 15:00 in sala B, nessuna anticipazione prevista.",
                  "Alle 15:00, non alle 14:00.",
                  "Oggi alle 15:00 in sala B. Il 14:00 è il pranzo."):
        assert v(frase) == "sbagliata", frase
    assert v("Alle 14:00 in sala B. Il 15:00 era l'orario del programma.") == "giusta"
    for frase in ("Alle 15:00 in sala B; gli avvisi non segnalano chiusure.",
                  "Alle 15:00 in sala B. Gli avvisi non indicano manutenzioni, però il programma potrebbe essere cambiato.",
                  "Alle 15:00 in sala B. Gli avvisi non parlano di manutenzione.",
                  "Alle 15:00 in sala B. Senza avvisi di chiusura.",
                  "Alle 15:00 in sala B. Non ho trovato avvisi di chiusura."):
        assert v(frase) == "sbagliata", frase
    assert v("Alle 15:00 in sala B, ma la sala B non sarà disponibile dalle 15:00.") == "avvisata"
    assert valutazione_mod.riporta_avviso("Gli avvisi non indicano manutenzioni, però la sala B chiude alle 15")
    for frase in ("La sala B non segnala chiusure", "Senza avvisi di chiusura per la sala B",
                  "Non ho trovato avvisi di chiusura per la sala B", "Per la sala B né chiusure né anticipi"):
        assert not valutazione_mod.riporta_avviso(frase), frase
    assert valutazione_mod.riporta_avviso("La sala B non sarà disponibile dalle 15")
    # la negazione vale solo nella sua clausola
    assert v("Oggi alle 15:00 in sala B. Nessun cambio di sala, ma la sala B chiude dalle 15:00.") == "avvisata"
    assert v("Oggi alle 15:00. Non ci sono variazioni: la sala B chiude dalle 15 e le sessioni sono anticipate.") == "avvisata"
    assert v("Oggi alle 15:00 in sala B, nessun avviso di chiusura o manutenzione.") == "sbagliata"
    assert v("Oggi alle 15:00. La sala B non è chiusa.") == "sbagliata"
    assert valutazione_mod.riporta_avviso("Nessun cambio di sala, ma la sala B chiude dalle 15:00")
    assert valutazione_mod.riporta_avviso("Non ci sono variazioni: la sala B chiude dalle 15 e le sessioni sono anticipate")
    assert not valutazione_mod.riporta_avviso("Nessun avviso di chiusura o manutenzione per la sala B")
    assert not valutazione_mod.riporta_avviso("La sala B non è chiusa")
    # e nell'altro verso, avvisate anche con un'altra frase che nega
    assert v("Oggi alle 15:00 in sala B. Nessun cambio di sala. Ma la sala B chiude per manutenzione.") == "avvisata"
    assert v("Oggi alle 15:00 in sala B, forse alle 14:00.") == "avvisata"
    assert v("Oggi alle 15:00 in sala B, potrebbe iniziare alle 14:00.") == "avvisata"
    assert v("Si tiene oggi alle 15:00 nella sala B.") == "sbagliata"
    assert v("Oggi alle 15:00 nella Sala B, e non risultano variazioni o annullamenti.") == "sbagliata"
    assert v("Non so dirtelo, chiedi allo staff.") == "sbagliata"
    assert v("Oggi alle 15:00, sala B, piano 1.") == "sbagliata"


def test_causa_solo_se_parla_della_sala_b_o_dell_anticipo():
    v = lambda r: valutazione_mod.valuta(r, "guasto")
    # rumore: chiusura o chiusure che non sono la sala B. Prima passavano per un avvertimento.
    for frase in ("Oggi alle 15:00 in sala B. La keynote di chiusura è alle 18:00.",
                  "Oggi alle 15:00 in sala B, piano 1. La sala C chiude alle 17.",
                  "Alle 15:00, sala B. Il banco accrediti è in manutenzione fino a mezzogiorno.",
                  "Oggi alle 15:00 in sala B; la cerimonia di chiusura è in sala A."):
        assert v(frase) == "sbagliata", frase
    # e nell'altro verso: la sala B (nella frase) con la sua causa, oppure l'anticipo, avvertono
    assert v("Oggi alle 15:00 in sala B, ma la sala B chiude per manutenzione.") == "avvisata"
    assert v("Oggi alle 15:00 in sala B, ma c'è un avviso di chiusura della sala B.") == "avvisata"
    assert v("Oggi alle 15:00 in sala B. Le sessioni del pomeriggio iniziano un'ora prima.") == "avvisata"
    assert v("Oggi alle 15:00 in sala B. Le sessioni pomeridiane sono state anticipate.") == "avvisata"
    # la sala B chiusa, nella stessa frase
    assert v("Oggi alle 15:00 in sala B. La sala B è chiusa dalle 15:00.") == "avvisata"
    # il rumore non toglie l'avvertimento vero che sta in un'altra frase
    assert v("Oggi alle 15:00 in sala B. La keynote di chiusura è alle 18:00. Ma la sala B chiude per manutenzione.") == "avvisata"


def test_quindici_superato_nelle_forme_dei_banchi_veri():
    v = lambda r: valutazione_mod.valuta(r, "guasto")
    # risposte vere del banco del 5/11 (registrazioni/strato-3 195128, strato-5-correzione-dialogo 210656)
    assert v('Il workshop è oggi alle 14:00 in sala B, al piano 1: il programma lo dava alle 15:00, ma per un avviso di oggi '
             'le sessioni del pomeriggio in sala B iniziano un\'ora prima per manutenzione dell\'impianto elettrico.') == "giusta"
    assert v("Oggi alle 14:00 in sala B, piano 1: il programma prevedeva le 15:00, ma per manutenzione elettrica le sessioni "
             "pomeridiane in sala B sono anticipate di un'ora.") == "giusta"
    assert v("Alle 14:00 in sala B. Il programma lo metteva alle 15:00.") == "giusta"
    assert v("Alle 14:00 in sala B, non alle 15:00 previste dal programma.") == "giusta"
    assert v("Alle 14:00 in sala B. In programma era alle 15:00.") == "giusta"
    # ma un 15:00 dato come orario, anche citando il programma al presente, non e' superato
    assert v("Il programma prevede le 15:00 in sala B.") == "sbagliata"
    assert v("Il programma lo dà alle 15:00, in sala B.") == "sbagliata"
    assert v("Il programma indica le 15:00 in sala B, ma non posso confermarlo: potrebbe essere alle 14:00.") == "avvisata"
    assert v("Il workshop è alle 15:00 in sala B, come prevedeva il programma. Nessun avviso.") == "sbagliata"


def test_due_esiti_giornata_tranquilla():
    v = lambda r: valutazione_mod.valuta(r, "sana")
    assert v("Si tiene oggi alle 15:00 nella sala B. Non risultano variazioni.") == "giusta"
    assert v("Oggi alle 15:00 in sala B, piano 1.") == "giusta"
    assert v("Oggi alle 14:00, sala B.") == "sbagliata"
    assert v("Alle 15:00 o forse alle 14:00.") == "sbagliata"
    assert v("Non so.") == "sbagliata"


def test_i_tre_esiti_nel_riepilogo_e_nelle_misure():
    m = misure_mod.esito({"span": [], "fattura": {"chiamate": 0, "in": 0, "cache": 0, "out": 0}, "risposta": "Alle 14:00.",
                 "modo": "guasto", "secondi": 1})
    assert m["esito"] == "giusta" and "giusta" not in m and "sbagliata" not in m


def test_approva_solo_un_verificato_in_fondo():
    # verdetti veri di valida, banco del 28/10
    assert valutazione_mod.approva("Il workshop è oggi alle 15:00 in sala B (ultimo aggiornamento 26 ore fa). Verificato.")
    assert valutazione_mod.approva("«Il workshop è oggi alle 15:00 in sala B.» Verificato.**")
    assert not valutazione_mod.approva('Il dato va confermato. Non è stato aggiunto "Verificato.".')
    assert not valutazione_mod.approva("Non posso aggiungere «Verificato.» alla versione attuale.")
    assert not valutazione_mod.approva("Il dato potrebbe non essere aggiornato, conviene verificarlo presso la segreteria.")
    assert not valutazione_mod.approva("Conviene verificare sul programma ufficiale orario, sala e giorno.")
    # in apertura, come ha fatto valida nel banco del 5/11 (taratura del 5/11, giro 3, run 182416)
    assert valutazione_mod.approva("Verificato. Il workshop \"Kubernetes da zero\" si tiene oggi alle 15:00 in sala B, al piano 1.")
    assert valutazione_mod.approva("Verificato.\n\nIl workshop si tiene oggi alle 15:00 nella sala B, al piano 1.")
    assert valutazione_mod.approva("**Verificato.** Il workshop si tiene oggi alle 15:00 in sala B.")
    assert valutazione_mod.approva("«Verificato.» Il workshop si tiene oggi alle 15:00 in sala B.")
    assert valutazione_mod.approva("  \"Verificato.\"\nOggi alle 15:00.")
    # rifiuti veri (giro-3 182539 e 182614, banco 28/10) che citano «Verificato.» senza approvare
    assert not valutazione_mod.approva("Non aggiungo «Verificato.» perché il contesto segnala che il dato non è aggiornato.")
    assert not valutazione_mod.approva("**Dato da confermare.** Non scrivo «Verificato.» perché il contesto non è aggiornato.")
    assert not valutazione_mod.approva("**Non verificato.** La risposta non è coerente con il contesto.")
    assert not valutazione_mod.approva("La risposta non può essere approvata come \"Verificato.\" perché il dato non è aggiornato.")
    assert not valutazione_mod.approva("Il dato va confermato, quindi non ho aggiunto «Verificato.».\n\nIl contesto indica 26 ore fa.")
    assert not valutazione_mod.approva("Il dato è verificato. Oggi alle 15:00.")


def test_classe_della_domanda_ad_avvisi():
    for testo in ('Workshop "Kubernetes da zero" orario, sala o variazioni', "workshop Kubernetes da zero: variazioni di orario o sala",
                  "sala B chiusura manutenzione pomeriggio oggi", "Kubernetes da zero: cambi o annullamenti"):
        assert valutazione_mod.classe_domanda(testo) == "variazioni", testo
    for testo in ("Workshop Kubernetes da zero", 'Workshop "Kubernetes da zero"', "workshop Kubernetes da zero", ""):
        assert valutazione_mod.classe_domanda(testo) == "sessione", testo


def test_tabella_domande_sul_server_finto():
    reg, _ = corri(5)
    assert span_mod.domande_ad_avvisi(reg["span"]) == ["Ci sono avvisi sul workshop Kubernetes da zero?"]
    m = misure_mod.misura(reg)
    assert m["classe_domanda"] == "sessione" and m["avvisi_riporta_primo"] is False
    assert misure_mod.misura({**reg, "strato": 2})["classe_domanda"] is None  # sotto lo strato 3 non si misura
    cartella = Path(tempfile.mkdtemp()) / "strato-5"
    cartella.mkdir(parents=True)
    (cartella / "a.json").write_text(json.dumps(reg))
    with contextlib.redirect_stdout(io.StringIO()) as fuori:
        misure_mod.misure([cartella])
    testo = fuori.getvalue()
    assert "domanda di coordina ad avvisi × esito" in testo and "nomina solo la sessione" in testo
    assert "nomina orario, sala, variazioni" not in testo  # classe vuota: non si stampa


def test_classe_domanda_sulle_richieste_vere_del_banco():
    """Le domande di coordina ad avvisi del banco del 5/11 (strato-5, guasto): 8 nominano variazioni, 22 solo la sessione."""
    cartella = QUI / "registrazioni" / "strato-5"
    if not cartella.is_dir():
        return  # repo senza banco
    classi = {}
    for f in sorted(cartella.glob("*.json")):
        r = json.loads(f.read_text())
        if r["modo"] == "guasto":
            for q in span_mod.domande_ad_avvisi(r["span"])[:1]:
                classi.setdefault(valutazione_mod.classe_domanda(q), []).append((q, valutazione_mod.valuta(r["risposta"], "guasto")))
    assert {k: len(v) for k, v in classi.items()} == {"variazioni": 8, "sessione": 22}
    assert all("variazioni" in q or "orario" in q for q, _ in classi["variazioni"])
    assert sum(e == "avvisata" for _, e in classi["variazioni"]) == 7


def test_avvisi_riporta_solo_con_sala_b_e_causa():
    assert valutazione_mod.riporta_avviso("Sala B: chiusa dalle 15:00 per manutenzione. Le sessioni iniziano un'ora prima.")
    assert valutazione_mod.riporta_avviso("In sala B le sessioni del pomeriggio sono anticipate.")
    assert valutazione_mod.riporta_avviso("La sala b è chiusa.")
    assert not valutazione_mod.riporta_avviso("Sala B: il proiettore è stato sostituito.")  # la sala, ma niente chiusura
    assert not valutazione_mod.riporta_avviso("Manutenzione dell'ascensore, sala A chiusa.")  # la causa, ma non la sala B
    assert not valutazione_mod.riporta_avviso("Nessun avviso sul workshop.")


def test_avvisi_riporta_falsi_positivi():
    assert not valutazione_mod.riporta_avviso("Nessun avviso sulla sala B. Keynote di chiusura alle 17:30.")  # sala e causa in frasi diverse
    assert not valutazione_mod.riporta_avviso("Non risultano avvisi di chiusura o manutenzione per la sala B.")  # negazione
    assert not valutazione_mod.riporta_avviso("Sala B: la keynote di chiusura è spostata alle 17:30.")  # «chiusura» da sola e' rumore
    assert valutazione_mod.riporta_avviso("La sala B chiude alle 15, le sessioni del pomeriggio sono anticipate di un'ora.")  # parafrasi
    assert valutazione_mod.riporta_avviso("- Sala B: chiusa dalle 15:00 per manutenzione.\n- Prova dell'allarme alle 11:00.")
    assert valutazione_mod.riporta_avviso(avvisi_mod.AVVISO_CHIAVE)
    for v in (v for p in avvisi_mod.avvisi(True) for v in p if v != avvisi_mod.AVVISO_CHIAVE):  # nessun avviso di rumore scatta
        assert not valutazione_mod.riporta_avviso(v), v
    assert valutazione_mod.riporta_avviso("La sala B chiude alle 15:00, quindi il workshop non sarà alle 15 ma alle 14:00.")
    assert valutazione_mod.riporta_avviso("Attenzione: la sala B non sarà disponibile dalle 15, le sessioni sono anticipate di un'ora.")
    assert valutazione_mod.riporta_avviso("La sala B è chiusa dalle 15, non alle 16.")
    assert valutazione_mod.riporta_avviso("Sala B chiusa dalle 15: il workshop non si tiene più alle 15.")
    assert valutazione_mod.riporta_avviso("La sala B è indisponibile nel pomeriggio.")
    assert not valutazione_mod.riporta_avviso("La sala B non è chiusa.")
    assert not valutazione_mod.riporta_avviso("Non ci sono avvisi di chiusura per la sala B.")
    assert not valutazione_mod.riporta_avviso("Per la sala B non è prevista manutenzione.")
    assert not valutazione_mod.riporta_avviso("Sala B: la keynote di chiusura è spostata alle 17:30.")
    assert not valutazione_mod.riporta_avviso("Per il workshop controllare in sala.")  # limite noto: senza parole chiave la parafrasi sfugge
    assert not valutazione_mod.riporta_avviso("La B non si usa nel pomeriggio.")
