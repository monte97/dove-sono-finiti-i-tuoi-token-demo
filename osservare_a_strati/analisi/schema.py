"""Lo schema del sistema: il grafo delle chiamate fra agenti, aggregato sulle run."""
import json
from pathlib import Path

from ..valutazione import riporta_avviso
from .misure import MINIMO_MISURE
from .span import archi, archi_della_run, attr

ORDINE_NODI = ("utente", "coordina", "programma", "sale", "avvisi", "valida")  # l'ordine in cui si disegnano


def _ordine(nome: str):
    return (ORDINE_NODI.index(nome), nome) if nome in ORDINE_NODI else (len(ORDINE_NODI), nome)


def _agenti(span) -> set:
    return {attr(x, "gen_ai.agent.name") for x in span if attr(x, "gen_ai.operation.name") == "invoke_agent"}


def schema(regs: list[dict], senza_strumenti: bool = False) -> tuple[str, str]:
    """(testo, mermaid) dello schema delle chiamate, sulle registrazioni date (tutte dallo strato 2 in su)."""
    n = len(regs)
    strato = min(r["strato"] for r in regs)
    archi_run = [archi_della_run(r["span"]) for r in regs]
    agenti = set().union(*(_agenti(r["span"]) for r in regs)) | {"coordina"}
    arco = {}  # (da, a) -> [run in cui compare, volte in totale]
    for ar in archi_run:
        for k, v in ar.items():
            e = arco.setdefault(k, [0, 0])
            e[0] += 1
            e[1] += v
    # rimpalli: chi e' chiamato da due chiamanti diversi nella stessa run
    due_chiamanti, doppia_strada = {}, False
    for ar in archi_run:
        chiamanti = {}
        for (da, a) in ar:
            if a in agenti:
                chiamanti.setdefault(a, set()).add(da)
        for a, ds in chiamanti.items():
            if len(ds) >= 2:
                due_chiamanti.setdefault(a, [0, set()])
                due_chiamanti[a][0] += 1
                due_chiamanti[a][1] |= ds
        doppia_strada |= {"coordina", "programma"} <= chiamanti.get("sale", set())
    guardie = [(r, [x for x in archi(r["span"]) if attr(x, "error.type") == "ciclo"]) for r in regs]
    arco_guardia = {(attr(x, "gen_ai.agent.name"), attr(x, "gen_ai.transfer.target.name")) for _, g in guardie for x in g}
    # tratteggiati: chi controlla o chiede a una fonte fuori dal giro di coordina (valida che richiama, avvisi che chiede a
    # programma) e gli archi respinti dalla guardia. In rosso, pieno: la strada in piu' coordina → sale, quando sale e'
    # chiamato anche da programma nella stessa run (programma → sale e' la strada normale, resta piena).
    tratteggiati = {k for k in arco if k[0] == "valida" or k == ("avvisi", "programma")} | arco_guardia
    tratteggiati = {k for k in tratteggiati if k in arco}
    in_rosso = {("coordina", "sale")} if doppia_strada and ("coordina", "sale") in arco else set()
    rimpalli = tratteggiati | in_rosso

    # --- il testo ---
    righe = [f"schema del sistema: {n} run, strato {strato}", "", "chi chiama chi (in quante run · volte in totale)"]
    righe.append(f"   {'utente → coordina':<28} {n:>3} su {n} · {n:>3} volte")
    ordinati = sorted((k for k in arco if k[1] in agenti), key=lambda k: (_ordine(k[0]), _ordine(k[1])))
    for k in ordinati:
        segno = "  *" if k in rimpalli else "   "
        righe.append(f"{segno}{k[0] + ' → ' + k[1]:<28} {arco[k][0]:>3} su {n} · {arco[k][1]:>3} volte")
    foglie = sorted((k for k in arco if k[1] not in agenti), key=lambda k: (_ordine(k[0]), k[1]))
    if foglie and not senza_strumenti:
        righe.append("  strumenti dei dati")
        for k in foglie:
            righe.append(f"     {k[0] + ' → ' + k[1]:<28} {arco[k][0]:>3} su {n} · {arco[k][1]:>3} volte")
    righe += ["", "rimpalli (* nell'elenco sopra)"]
    for a in sorted(due_chiamanti, key=_ordine):
        righe.append(f"  {a} chiamato da {len(due_chiamanti[a][1])} chiamanti ({', '.join(sorted(due_chiamanti[a][1], key=_ordine))}): "
                     f"{due_chiamanti[a][0]} run su {n}")
    if not due_chiamanti:
        righe.append(f"  nessun agente chiamato da piu' chiamanti nella stessa run: 0 run su {n}")
    for fonte in ("avvisi", "programma"):
        k = ("valida", fonte)
        righe.append(f"  valida richiama {fonte}: {arco[k][0] if k in arco else 0} run su {n}")
        if fonte == "avvisi":
            if strato < MINIMO_MISURE["valida_riporta"]:
                righe.append("    ...e la risposta riporta l'avviso sulla sala B: serve lo strato 3")
            else:
                riportano = sum(any(riporta_avviso(attr(x, "gen_ai.tool.call.result", "")) for x in archi(r["span"], ("avvisi",), da="valida"))
                                for r in regs)
                righe.append(f"    ...e la risposta riporta l'avviso sulla sala B: {riportano} run su {n}")
    k = ("avvisi", "programma")
    righe.append(f"  avvisi chiede a programma (dialogo): {arco[k][0] if k in arco else 0} run su {n}")
    righe.append(f"  guardia dei cicli scattata: {sum(bool(g) for _, g in guardie)} run su {n} · {sum(len(g) for _, g in guardie)} volte")

    # --- Mermaid ---
    def etichetta(k):
        run, volte = arco[k]
        media = round(volte / run, 1)
        return f"{run}/{n}" + (f" ×{media:.1f}" if media > 1 else "")
    mm = ["flowchart LR", "  %% legenda: ogni arco e' «in quante run su quante» (×N = volte per run, in media);",
          "  %% tratteggiato = chi controlla o chiede a una fonte fuori dal giro di coordina (valida che richiama, avvisi che "
          "chiede a programma, arco respinto dalla guardia); rosso = coordina → sale quando sale e' chiamato anche da programma"]
    nodi = sorted(agenti, key=_ordine)
    mm.append("  utente([utente])")
    mm += [f"  {a}[{a}]" for a in nodi]
    mm.append(f"  utente -->|{n}/{n}| coordina")
    tratti, rossi = [], []
    for i, k in enumerate(ordinati, start=1):
        mm.append(f"  {k[0]} {'-.->' if k in tratteggiati else '-->'}|{etichetta(k)}| {k[1]}")
        if k in tratteggiati:
            tratti.append(i)
        if k in in_rosso:
            rossi.append(i)
    if tratti:
        mm.append(f"  linkStyle {','.join(map(str, tratti))} stroke:#7f8c8d,stroke-width:2px,color:#7f8c8d")
    if rossi:
        mm.append(f"  linkStyle {','.join(map(str, rossi))} stroke:#c0392b,stroke-width:3px,color:#c0392b")
    return "\n".join(righe), "\n".join(mm)


def mostra_schema(cartella: Path, modo: str | None = None, senza_strumenti: bool = False):
    if not cartella.is_dir():
        raise SystemExit(f"{cartella}: non e' una cartella di registrazioni")
    regs = [json.loads(f.read_text()) for f in sorted(cartella.glob("*.json"))]
    if not regs:
        raise SystemExit(f"{cartella}: nessuna registrazione")
    if min(r["strato"] for r in regs) < 2:
        print("lo schema delle chiamate serve lo strato 2: sotto non ci sono gli span degli agenti")
        return
    regs = [r for r in regs if modo is None or r["modo"] == modo]
    if not regs:
        print(f"nessuna registrazione in modo {modo}")
        return
    testo, mermaid = schema(regs, senza_strumenti)
    print(testo)
    print("\n```mermaid\n" + mermaid + "\n```")
