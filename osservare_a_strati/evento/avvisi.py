"""Il generatore degli avvisi della giornata: rumore plausibile e, nella giornata piena, l'avviso sulla sala B."""
import random

# Taratura della giornata: la tranquilla e la piena si cambiano da qui.
PAGINE_PIENA = 40
PAGINE_TRANQUILLA = 3
PAGINA_AVVISO = 23  # a che pagina sta l'avviso sulla sala B nella giornata piena
AVVISI_PER_PAGINA = 10
SEME_AVVISI = 20261105

AVVISO_CHIAVE = ("Sala B: chiusa dalle 15:00 per manutenzione dell'impianto elettrico. "
                 "Le sessioni del pomeriggio in sala B iniziano un'ora prima dell'orario in programma.")
AVVISO_ALLARME = "Prova dell'allarme antincendio alle 11:00: nessuna evacuazione, il suono dura un minuto."
_ORE = ["8:30", "9:15", "10:00", "12:30", "13:00", "16:00", "16:45", "17:30", "18:00", "18:30", "19:00"]  # mai le 14 e le 15
_MODELLI = [
    ("Guardaroba: ritiro borse fino alle {ora}, al piano {p} accanto all'ingresso {i}.",
     {"ora": _ORE, "p": ["terra", "primo"], "i": ["nord", "sud", "est"]}),
    ("Wifi: la rete {r} cambia chiave alle {ora}, la nuova è stampata sul retro del badge.",
     {"r": ["DevFest-Ospiti", "DevFest-Stampa", "DevFest-Espositori"], "ora": _ORE}),
    ("Pranzo: il turno {t} è nell'area ristoro del piano {p}, menù {m}.",
     {"t": ["delle 12:30", "delle 13:00", "delle 13:30"], "p": ["terra", "primo"],
      "m": ["vegetariano", "classico", "senza glutine", "vegano"]}),
    ("Sponsor: lo stand {s} regala {g} a chi passa entro le {ora}.",
     {"s": ["Nimbus", "Quadra", "Orbita", "Fulcro", "Vertice", "Sestante"], "g": ["una borraccia", "degli adesivi",
      "una power bank", "un taccuino", "una maglietta"], "ora": _ORE}),
    ("Badge: chi ha perso il badge può ritirarne uno nuovo al desk {d}, {c}.",
     {"d": ["1", "2", "3", "4"], "c": ["con un documento", "mostrando la mail di conferma", "dopo aver firmato il modulo"]}),
    ("Parcheggio: il parcheggio {a} è completo, usare {b}.", {"a": ["nord", "est", "ovest", "sud"], "b": ["il parcheggio sud",
      "l'interrato", "quello di via Verdi", "quello di piazza Mercato", "quello della stazione"]}),
    ("Keynote: la keynote {k} è spostata alle {ora} in auditorium.",
     {"k": ["sull'intelligenza artificiale", "sui linguaggi", "sugli open data", "sul software libero", "sulla sostenibilità", "dei fondatori"],
      "ora": ["9:15", "10:00", "12:30", "17:30", "18:00", "18:30"]}),
    ("Sessione annullata: «{x}», prevista domani, è annullata perché il relatore è bloccato in viaggio.",
     {"x": ["Introduzione a Zig", "Event sourcing senza dolore", "Il debito tecnico spiegato a tuo cugino",
            "Design system in tre settimane", "Mobile offline-first", "Testare l'impossibile",
            "Database in embedded", "Accessibilità nel frontend", "Code review senza litigare"]}),
    ("Sala A: {c}.", {"c": ["il proiettore è stato sostituito", "distribuite le cuffie per la traduzione",
                            "le prime due file sono riservate a chi ha bisogno di spazio", "il microfono a mano è sul tavolo",
                            "il condizionatore è stato regolato", "la porta laterale resta chiusa", "ci sono prese in ogni fila"]}),
    ("Sala C: {c}.", {"c": ["il condizionatore è stato regolato", "ci sono sedie aggiuntive in fondo",
                            "la lavagna a fogli è stata cambiata", "l'ingresso è dal corridoio est",
                            "il proiettore ha un nuovo telecomando", "le tende sono state abbassate", "ci sono prese in ogni fila"]}),
    ("Navetta: la navetta per {d} parte ogni {n} minuti dal cancello {i}.",
     {"d": ["la stazione", "la fiera", "il centro", "l'aeroporto"], "n": ["10", "15", "20", "30"], "i": ["nord", "sud", "est"]}),
    ("Oggetti smarriti: trovati {o}, ritirabili al desk {d}.",
     {"o": ["un caricatore", "un ombrello", "un paio di occhiali", "una felpa grigia", "un quaderno", "delle chiavi",
            "una borraccia blu", "un cappello"], "d": ["1", "2", "3", "4"]}),
    ("Community: il tavolo {t} è riservato al gruppo {g} fino alle {ora}.",
     {"t": ["1", "2", "3", "4", "5"], "g": ["Python", "Rust", "Cloud Native", "Frontend", "Open Source", "Dati"], "ora": _ORE}),
    ("Foto: il fotografo ufficiale sarà {l} alle {ora}, chi vuole la foto di gruppo passi di lì.",
     {"l": ["in area ristoro", "all'ingresso", "nell'atrio", "davanti all'auditorium"], "ora": _ORE}),
    ("Accessibilità: l'ascensore {a} {c}, chiedere allo staff in caso di coda.",
     {"a": ["nord", "sud", "centrale", "di servizio"], "c": ["è riservato a chi ne ha bisogno", "è in manutenzione ordinaria",
      "ha la precedenza per le carrozzine", "si ferma a tutti i piani"]}),
    ("Caffè: la macchina del piano {p} è guasta, usare quella {q}.",
     {"p": ["terra", "primo", "secondo"], "q": ["del piano superiore", "del piano inferiore", "dell'area ristoro", "del bar esterno"]}),
    ("Registrazioni: i talk di {s} sono registrati, i video saranno online {q}.",
     {"s": ["auditorium", "sala A", "sala C", "tutte le sale"], "q": ["entro una settimana", "entro dieci giorni",
      "dopo la chiusura", "entro fine mese"]}),
    ("Cambio relatore: la sessione «{x}» sarà tenuta da {r}, la sala è sul programma aggiornato.",
     {"x": ["Observability per tutti", "Il cloud costa meno di quanto pensi", "Rust nel firmware", "Dati in tempo reale",
            "Piattaforme interne", "API che invecchiano bene"], "r": ["una collega", "un collega", "il moderatore", "un ospite"]}),
    ("Feedback: compila il questionario di {s} entro le {ora}, bastano due minuti.",
     {"s": ["giornata", "sessione", "evento"], "ora": ["12:30", "13:00", "16:00", "17:30", "18:00", "19:00"]}),
    ("Merchandise: le {g} sono in vendita al banco {d} fino alle {ora}.",
     {"g": ["magliette", "felpe", "borracce", "tote bag", "spille"], "d": ["1", "2", "3"], "ora": _ORE}),
    ("Treni: l'ultimo regionale per {c} parte alle {ora}, la navetta per la stazione parte mezz'ora prima.",
     {"c": ["Bologna", "Firenze", "Milano", "Padova", "Verona"], "ora": ["19:30", "20:15", "21:00", "21:45", "22:30"]}),
    ("Silenzio: la zona {z} è riservata a chi vuole lavorare in silenzio, telefonate nell'atrio.",
     {"z": ["al primo piano", "dietro l'auditorium", "vicino alla biblioteca", "nel corridoio est"]}),
    ("Ricarica: le colonnine per i dispositivi sono {l}, {c}.",
     {"l": ["nell'atrio", "in area ristoro", "al primo piano", "vicino ai desk"], "c": ["a disposizione di tutti", "gratuite",
      "con cavi USB-C e Lightning", "fino a esaurimento posti"]}),
]


def _voce(rng: random.Random, modello: str, slot: dict) -> str:
    return modello.format(**{k: rng.choice(v) for k, v in slot.items()})


def avvisi(piena: bool) -> list[list[str]]:
    """Le comunicazioni di oggi, a pagine. Deterministiche: rumore plausibile, e nella piena l'avviso sulla sala B a metà."""
    rng, pagine, viste = random.Random(SEME_AVVISI), PAGINE_PIENA if piena else PAGINE_TRANQUILLA, set()
    voci = [AVVISO_ALLARME]
    viste.add(AVVISO_ALLARME)
    attivi, giro = list(range(len(_MODELLI))), 0  # un tipo dopo l'altro: nessuno prende il sopravvento
    while len(voci) < pagine * AVVISI_PER_PAGINA:
        k = attivi[giro % len(attivi)]
        for _ in range(40):  # un tipo che non sa piu' variare esce dal giro
            v = _voce(rng, *_MODELLI[k])
            if v not in viste:
                viste.add(v)
                voci.append(v)
                giro += 1
                break
        else:
            attivi.remove(k)
    if piena:
        voci[(PAGINA_AVVISO - 1) * AVVISI_PER_PAGINA + AVVISI_PER_PAGINA // 2] = AVVISO_CHIAVE
    return [voci[i:i + AVVISI_PER_PAGINA] for i in range(0, len(voci), AVVISI_PER_PAGINA)]
