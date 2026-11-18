"""Come si giudica una risposta: l'esito, l'approvazione di valida e gli avvisi che una frase riporta."""
import re

ESITI = ("giusta", "avvisata", "sbagliata")

# Tre esiti per la giornata piena. Si guarda quale orario la risposta DA' come orario della sessione:
# - una citazione di 15:00 come orario superato non conta (« non alle 15:00», «anticipato dalle 15:00», «rispetto alle
#   15:00 in programma», «15:00 previste») e nemmeno quando e' l'ora di chiusura della sala («chiusa dalle 15:00»);
# - giusta: dopo aver tolto quelle citazioni resta 14:00 e nessun 15:00. Anche con un «probabilmente» o «potrebbe»
#   davanti: se il 15:00 e' solo l'orario in programma, la risposta ha scelto le 14:00 e un pubblico la riterrebbe giusta;
# - avvisata: resta un 15:00 dato come orario ma la risposta avverte (sala B chiusa, manutenzione, un'ora prima,
#   anticipo, oppure le 14:00 date come possibili o probabili). Quindi «e' alle 15:00 ... quindi probabilmente alle 14:00» e' avvisata: apre con il
#   15:00 e lascia a chi legge la scelta. Verso conservativo: nel dubbio mai «giusta»;
# - sbagliata: il resto (15:00 senza avvertimento, o con un avvertimento negato, oppure nessun orario riconoscibile).
# Limite noto: sono regex su frasi italiane; un giro di parole fuori da questi modi (per esempio «alle tre del
# pomeriggio») non si riconosce e finisce in sbagliata; un 15:00 superato detto in un modo fuori elenco («il programma
# parlava delle 15:00») resta un 15:00 dato: mai giusta (verso conservativo), e sbagliata se non c'e' un avvertimento
# (avvisata se c'e'); una negazione
# vale solo nella sua clausola (vedi _clausole): «Nessun cambio di sala, ma la sala B chiude» avverte. Nella giornata tranquilla: giusta se c'e' 15:00 e non 14:00.
_QUINDICI_SUPERATO = re.compile(
    r"\bnon (?:più )?(?:alle|per le|delle|dalle)\s+15:00"
    r"|(?:\binvece\b|anzich[eé]|al posto\b|\brispetto\b|anticipat\w*|spostat\w*|\bchius\w*|\bchiude\b)[^.;!?]{0,30}?15:00"
    r"|15:00 (?:in programma|previst\w*|pubblicat\w*|originari\w*)"
    r"|\bprogramma (?:indicava|diceva|riportava|dava|segnava)\s+(?:le\s+|alle\s+)?15:00"
    r"|\b(?:lo\s+)?(?:dava|prevedeva|metteva|segnava|indicava)\s+(?:le\s+|alle\s+)?15:00"  # «il programma lo dava alle 15:00»
    r"|15:00\s+(?:erano\s+|era\s+)?previst[oae]\s+(?:dal|nel|sul)\s+programma"  # «le 15:00 previste dal programma»
    r"|previst[oae]\s+(?:dal|nel)\s+programma[^.;!?]{0,12}?15:00"  # «previsto dal programma alle 15:00»
    r"|(?:previst[oa]|era)\s+alle\s+15:00\s+nel\s+programma"
    r"|\bin\s+programma\s+(?:era|c'era)\s+(?:alle\s+|le\s+)?15:00"  # «in programma era alle 15:00»: passato, superato
    r"|15:00 (?:era|erano)\s+l'orario\s+(?:del|in|nel)\s+programma", re.I)
# Cosa vale come avvertimento: una causa oppure le 14:00 presentate come possibili o probabili. Una causa e' una di due
# cose, nella stessa frase o clausola, come in riporta_avviso: la sala B chiusa o in manutenzione («sala B» nella frase e
# chiusura, manutenzione, non disponibile nella clausola), oppure le sessioni pomeridiane portate avanti («un'ora prima»,
# «anticipat»). «La keynote di chiusura e' alle 18:00» o «la sala C chiude alle 17» non sono una causa: parlano d'altro.
# Una 14:00 nuda non avverte («il 14:00 e' il pranzo»). Una negazione che regge la causa nella stessa clausola la toglie:
# «nessun avviso di chiusura», «non risulta che sia chiusa», «nessuna anticipazione prevista», «non alle 14:00».
# Limite noto: «sala B» in una frase e la chiusura in un'altra («E' in sala B. Chiude alle 15.») non si legano
# (verso conservativo: sbagliata, non avvisata).
_CAUSA_SALA = re.compile(r"chius|chiud|manutenzion|\bnon\s+(?:sar[àa]\s+|è\s+)?disponibil|indisponibil", re.I)
_CAUSA_ANTICIPO = re.compile(r"un.ora prima|anticip", re.I)
_QUATTORDICI_POSSIBILE = re.compile(r"(?:potrebbe|probabilmente|forse|dovrebbe|magari)[^.;!?]{0,30}?14:00", re.I)


def _avverte(risposta: str) -> bool:
    for f in re.split(r"[.!?;\n]+", risposta):
        sala_b = AVVISI_SALA_B.search(f) is not None
        for k in _clausole(f):
            negazioni = list(AVVISI_NEGA.finditer(k))
            spie = [m.start() for rx in ((_CAUSA_SALA,) if sala_b else ()) + (_CAUSA_ANTICIPO, _QUATTORDICI_POSSIBILE)
                    for m in rx.finditer(k)]
            if any(not any(n.end() <= p for n in negazioni) for p in spie):
                return True
    return False


def valuta(risposta: str, modo: str) -> str:
    """giusta | avvisata | sbagliata (vedi il commento sopra per cosa vuol dire nei due modi)."""
    if modo != "guasto":
        return "giusta" if "15:00" in risposta and "14:00" not in risposta else "sbagliata"
    resto = _QUINDICI_SUPERATO.sub(" ", risposta)
    if "14:00" in risposta and "15:00" not in resto:
        return "giusta"
    return "avvisata" if "15:00" in resto and _avverte(risposta) else "sbagliata"


# Il verdetto di valida: «Verificato.» in fondo (come chiede l'istruzione) oppure in apertura, magari in grassetto o fra
# virgolette («Verificato. Il workshop...»): il banco del 5/11 ha mostrato che a volte lo scrive prima. Un rifiuto che lo
# cita («Non aggiungo «Verificato.» perche'...») ha altro prima e altro dopo: non approva. Stessa regola, riga per riga,
# in verdetti() e nella query del cruscotto (cruscotto/grafana/segnali.json, pannello «valida approva»).
APPROVA = re.compile(r"[\s\"'«*]*Verificato\..*|.*Verificato\.[\s\"'»*]*", re.S)


def approva(testo: str) -> bool:
    """valida approva quando «Verificato.» e' l'ultima cosa o la prima: chi lo cita per rifiutarlo, o scrive
    «verificare», non approva. Limite noto: un rifiuto che apre con «Verificato.» e poi obietta conta come approvato."""
    return bool(APPROVA.fullmatch(testo))


AVVISI_SALA_B = re.compile(r"sala B", re.I)
# la causa legata alla sala (non «chiusura» da sola: «keynote di chiusura» e' rumore)
AVVISI_CAUSA = re.compile(r"\bchius[ao]\b|\bchiud\w+|manutenzion|un.ora prima|anticipat|"
                          r"\bnon\s+(?:sar[àa]\s+|è\s+)?disponibil\w*|indisponibil", re.I)
# una negazione che regge la causa: sta PRIMA e dice che l'avviso o la chiusura non c'e'
# (qui anche «senza», «né» e «non» + fino a tre parole + un verbo che riporta o trova: «non segnalano», «non ho trovato»,
# «non parlano di», «non indicano»; «non sarà disponibile» resta una causa, non una negazione)
AVVISI_NEGA = re.compile(r"\bnessun\w*|\bsenza\b|\bné\b|"
                         r"\bnon\s+(?:\w+\s+){0,3}?(?:segnal|indic|parl|menzion|riport|preved|trov|risult)\w*\s+|"
                         r"\bnon\s+(?:ci\s+sono|c'è|vi\s+è|vi\s+sono|è\s+previst\w+|"
                         r"sono\s+previst\w+|è|sarà|sono)\s+", re.I)


_CONFINE_CLAUSOLA = re.compile(r"(?i:,\s*ma\b|\s+ma\s+|\bperò\b|\btuttavia\b|:\s|\s[—–]\s|,\s+(?=la sala\b))|,\s+(?=[A-Z])")


def _clausole(frase: str) -> list[str]:
    """Una frase a pezzi: «, ma», «ma», «però», «tuttavia», «:», «—» e una virgola seguita da maiuscola o da «la sala»
    chiudono la clausola. La negazione di una clausola non vale per le altre."""
    return _CONFINE_CLAUSOLA.split(frase)


def riporta_avviso(testo: str) -> bool:
    """Una frase dice che la sala B e' chiusa o che le sessioni anticipano: «sala B» e una causa nella stessa frase.
    Una negazione scarta la causa solo se sta prima di essa e la regge («nessun avviso di chiusura», «non risultano
    manutenzioni», «non è chiusa»); dopo la causa o su altro («non alle 16») non conta, e «non sarà disponibile» e'
    una causa. Limite noto: una parafrasi senza nessuna di queste parole (es. «la sala B si
    ferma alle 15») non viene riconosciuta."""
    for f in re.split(r"[.!?;\n]+", testo):
        if not AVVISI_SALA_B.search(f):
            continue
        for k in _clausole(f):  # la negazione vale solo nella sua clausola
            negazioni = list(AVVISI_NEGA.finditer(k))
            if any(not any(n.end() <= c.start() for n in negazioni) for c in AVVISI_CAUSA.finditer(k)):
                return True
    return False


# La domanda che coordina manda ad avvisi (l'argomento `richiesta` dell'arco coordina -> avvisi): nomina orario, sala,
# variazioni, cambi, chiusura o annullamenti (qui anche manutenzione, anticipo, spostamenti), oppure nomina solo la sessione.
# Nel banco del 5/11 le avvisate nascono dalle domande della prima classe: avvisi sa cosa cercare solo se glielo dici.
CHIEDE_VARIAZIONI = re.compile(r"orari|\bsala\b|\bsale\b|variazion|cambi|chius|annull|manutenzion|anticip|spost", re.I)
CLASSI_DOMANDA = ("variazioni", "sessione")


def classe_domanda(richiesta: str) -> str:
    """variazioni | sessione: la domanda ad avvisi chiede di variazioni (orario, sala, cambi, chiusura, annullamenti)
    oppure nomina solo la sessione."""
    return "variazioni" if CHIEDE_VARIAZIONI.search(richiesta) else "sessione"
