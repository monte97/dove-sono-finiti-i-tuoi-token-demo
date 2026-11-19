"""Test di schema. Nati da test_strati.py e test_segnali.py, divisi per argomento."""
import json
import re

from server_finto import *

from osservare_a_strati.analisi import schema as schema_mod
from osservare_a_strati.analisi import span as span_mod


def test_schema_conteggi_e_rimpalli():
    cartella = cartella_finta(3, annidate=True, valida_sala=True)
    testo = schema_di(cartella)
    assert "3 run, strato 5" in testo
    assert "utente → coordina" in testo
    for riga in ("coordina → programma", "coordina → avvisi", "coordina → valida", "programma → sale", "valida → avvisi"):
        assert re.search(rf"{riga}\s+3 su 3 · +\d+ volte", testo), riga
    assert re.search(r"coordina → sale\s+3 su 3", testo)
    assert "sale chiamato da 2 chiamanti (coordina, programma): 3 run su 3" in testo
    assert "valida richiama avvisi: 3 run su 3" in testo and "valida richiama programma: 3 run su 3" in testo
    assert "riporta l'avviso sulla sala B: 3 run su 3" in testo  # valida_sala: il ricontrollo nomina la sala
    assert "avvisi chiede a programma (dialogo): 0 run su 3" in testo
    assert "guardia dei cicli scattata: 0 run su 3 · 0 volte" in testo
    assert re.search(r"coordina → leggi_\w+", testo) is None and "avvisi → leggi_avvisi" in testo  # gli strumenti sono foglie dell'agente
    assert "strumenti dei dati" in testo and "strumenti dei dati" not in schema_di(cartella, senza_strumenti=True)
    assert "leggi_avvisi" not in schema_di(cartella, senza_strumenti=True)
    # senza chiamate annidate: nessun rimpallo
    semplice = schema_di(cartella_finta(2))
    assert "nessun agente chiamato da piu' chiamanti" in semplice and "valida richiama avvisi: 0 run su 2" in semplice


def test_schema_dialogo_e_guardia():
    testo = schema_di(cartella_finta(2, correzione=3, dialogo=True, ciclo="avvisi"))
    assert "avvisi chiede a programma (dialogo): 2 run su 2" in testo
    assert "guardia dei cicli scattata: 2 run su 2 · 2 volte" in testo
    assert re.search(r"\*programma → avvisi\s+2 su 2", testo)  # l'arco respinto dalla guardia e' un rimpallo
    mermaid = testo.split("```mermaid\n")[1]
    assert "avvisi -.->|2/2| programma" in mermaid and "programma -.->|2/2| avvisi" in mermaid


def test_schema_mermaid_stabile_e_valido():
    cartella = cartella_finta(2, annidate=True, valida_sala=True)
    uno = schema_di(cartella)
    assert uno == schema_di(cartella)  # stabile
    blocco = uno.split("```mermaid\n")[1].split("```")[0].rstrip("\n").splitlines()
    assert blocco[0] == "flowchart LR" and sum(r.strip().startswith("%%") for r in blocco) == 2
    archi_ = [r.strip() for r in blocco if "-->" in r or "-.->" in r]
    for r in archi_:
        assert re.fullmatch(r"\w+ (-->|-\.->)\|[^|]+\| \w+", r), r
    assert "utente -->|2/2| coordina" in archi_
    assert "coordina -->|2/2| avvisi" in archi_
    assert "programma -->|2/2 ×2.0| sale" in archi_  # la strada normale di sale resta piena...
    assert "valida -.->|2/2| avvisi" in archi_  # ...i controlli di valida sono tratteggiati
    assert "coordina -->|2/2| sale" in archi_  # coordina → sale resta un arco pieno, ma in rosso (sotto)
    # linkStyle: tratteggiati in grigio, la strada in piu' coordina → sale in rosso (indici numerati dal primo arco scritto)
    scritti = [r for r in blocco if "-->" in r or "-.->" in r]
    grigi = next(r for r in blocco if r.strip().startswith("linkStyle") and "#7f8c8d" in r).split()[1].split(",")
    rossi = next(r for r in blocco if r.strip().startswith("linkStyle") and "#c0392b" in r).split()[1].split(",")
    assert [i for i, r in enumerate(scritti) if "-.->" in r] == [int(i) for i in grigi]
    assert [scritti[int(i)].strip() for i in rossi] == ["coordina -->|2/2| sale"]
    assert sum(r.strip().startswith("linkStyle") for r in blocco) == 2
    leggenda = " ".join(r for r in blocco if r.strip().startswith("%%"))
    assert "tratteggiato = chi controlla o chiede a una fonte fuori dal giro di coordina" in leggenda
    assert "rosso = coordina → sale quando sale e' chiamato anche da programma" in leggenda
    nodi = [r.strip() for r in blocco if re.fullmatch(r"\s+\w+(\[\w+\]|\(\[\w+\]\))", r)]
    assert nodi == ["utente([utente])", "coordina[coordina]", "programma[programma]", "sale[sale]", "avvisi[avvisi]", "valida[valida]"]


def test_schema_volte_per_run_nell_etichetta():
    regs = [json.loads(f.read_text()) for f in sorted(cartella_finta(1).glob("*.json"))]
    sdoppiato = json.loads(json.dumps(regs[0]))
    # una chiamata in piu' coordina → sale nella stessa run: 2 volte, in 1 run
    x = next(y for y in sdoppiato["span"] if span_mod.attr(y, "gen_ai.transfer.target.name") == "sale")
    y = json.loads(json.dumps(x))
    y["id"] = "duplicato"
    sdoppiato["span"].append(y)
    _, mermaid = schema_mod.schema([sdoppiato])
    assert "coordina -->|1/1 ×2.0| sale" in mermaid and "coordina -->|1/1| programma" in mermaid
    assert "#c0392b" not in mermaid  # sale e' chiamato solo da coordina: nessuna strada in piu'
    # la media si arrotonda a un decimale: 3 volte in 2 run = ×1.5, 7 in 3 = ×2.3, e 1.04 non e' piu' di 1
    base = json.loads(json.dumps(regs[0]))
    due = [json.loads(json.dumps(base)), sdoppiato]  # 1 chiamata in una run, 2 nell'altra
    _, m3 = schema_mod.schema(due)
    assert "coordina -->|2/2 ×1.5| sale" in m3


def test_schema_filtra_per_modo():
    cartella = cartella_finta(n_guasto=2, n_sana=1, annidate=True)
    assert "3 run" in schema_di(cartella)
    assert "2 run, strato 5" in schema_di(cartella, modo="guasto")
    assert "1 run, strato 5" in schema_di(cartella, modo="sana")
    assert "nessuna registrazione in modo sana" in schema_di(cartella_finta(2), modo="sana")


def test_schema_sotto_lo_strato_2_e_sotto_il_3():
    assert "serve lo strato 2" in schema_di(cartella_finta(1, strato=1))
    testo = schema_di(cartella_finta(1, strato=2, annidate=True))
    assert "2 run" not in testo and "strato 2" in testo and "```mermaid" in testo
    assert "riporta l'avviso sulla sala B: serve lo strato 3" in testo
    assert "serve lo strato 2" not in testo
