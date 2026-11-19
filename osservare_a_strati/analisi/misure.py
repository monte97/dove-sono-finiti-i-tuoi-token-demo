"""Le misure della giornata: esito di una run, banco, riepilogo e cosa ha deciso il modello."""
import json
import statistics
from pathlib import Path

from ..evento.avvisi import AVVISO_CHIAVE
from ..modello import costo
from ..osservabilita.tracce import EMAIL
from ..stampa import c, con_email
from ..valutazione import AVVISI_SALA_B, CLASSI_DOMANDA, ESITI, classe_domanda, riporta_avviso, valuta
from .span import (archi, attr, avvisi_dopo_sala, cicli, costo_per_agente, dialogo, dialogo_riporta, domande_ad_avvisi,
                   grafo, in_ordine, pagine_avvisi, pagine_ricontrolli, per_trace, profondita_agenti, quota_avvisi,
                   quota_riletture, sale_da_due, stesso_giro, strumenti, token_per_agente, verdetti)


def esito(r: dict) -> dict:
    span, f = r["span"], r["fattura"]
    risposta = r["risposta"] or ""
    return {"tracce": len(per_trace(span)), "span": len(span), "chiamate": f["chiamate"],
            "strumento": sum(attr(s, "gen_ai.operation.name") == "execute_tool" for s in span),
            "esito": valuta(risposta, r["modo"]),
            "secondi": r["secondi"], "token": f["in"] + f["out"], "costo": costo(f["in"], f["cache"], f["out"]),
            "email": con_email(span), "attributi": sum(len(s["attributi"]) for s in span)}


def banco(regs: list):
    print(f"{'#':>2} {'trace':>5} {'span':>4} {'chiamate':>8} {'secondi':>7} {'token':>6} {'costo $':>9}  risposta")
    for i, r in enumerate(regs, 1):
        e = esito(r)
        print(f"{i:>2} {e['tracce']:>5} {e['span']:>4} {e['chiamate']:>8} {e['secondi']:>7.1f} {e['token']:>6} "
              f"{e['costo']:>9.6f}  {' '.join(r['risposta'].split())[:70]}")


def riepilogo(cartella: Path):
    gruppi, speso = {}, 0.0
    for f in sorted(cartella.rglob("*.json")):
        r = json.loads(f.read_text())
        e = esito(r)
        speso += e["costo"]
        gruppi.setdefault((f.parent.name, r["modo"]), []).append(e)
    print(f"{'cartella':<28} {'modo':6} {'n':>3} {'trace':>5} {'span':>4} {'attr':>4} {'chiam.':>6} "
          f"{'giuste':>6} {'avvis.':>6} {'sbagl.':>6} {'email':>5} {'sec med':>7} {'token med':>9} {'$ med':>9}")
    for (cartella_, modo), ee in sorted(gruppi.items()):
        conta = lambda k: sum(e["esito"] == k for e in ee) if k in ESITI else sum(e[k] for e in ee)
        med = lambda k: statistics.median(e[k] for e in ee)
        print(f"{cartella_:<28} {modo:6} {len(ee):>3} {med('tracce'):>5.0f} {med('span'):>4.0f} "
              f"{med('attributi'):>4.0f} {med('chiamate'):>6.0f} {conta('giusta'):>6} {conta('avvisata'):>6} {conta('sbagliata'):>6} "
              f"{med('email'):>5.0f} {med('secondi'):>7.1f} {med('token'):>9.0f} {med('costo'):>9.6f}")
    print(f"\nspeso in tutto, dalle registrazioni: $ {speso:.4f}")


# Le misure della giornata piena. Ognuna dice da quale strato in su gli span che servono esistono: sotto, None.
MINIMO_MISURE = {"stesso_giro": 2, "dopo_sala": 2, "token": 2, "letto": 3, "riporta": 3, "verdetti": 3, "email_valida": 3,
                 "pagine": 4, "sale_due": 2, "valida_rivede": 2, "valida_riporta": 3, "dialogo": 2, "dialogo_riporta": 3,
                 "cicli": 2, "profondita_agenti": 2, "domanda_avvisi": 3}


def misura(r: dict) -> dict:
    """Cosa e' successo in una run: il grafo, cosa ha letto e riportato avvisi, i verdetti di valida, i token per agente.
    None dove gli span che servono non esistono a quello strato."""
    span, risposta, strato = r["span"], r["risposta"] or "", r["strato"]
    se = lambda nome, valore: valore() if strato >= MINIMO_MISURE[nome] else None
    livelli = [lv for _, lv in in_ordine(span)]
    avvisi_tool, a_avvisi = strumenti(span, "leggi_avvisi"), archi(span, ("avvisi",), da="coordina")
    ricontrolli = archi(span, ("avvisi",), da="valida")
    verdetto = se("verdetti", lambda: verdetti(span))
    return {**esito(r), "grafo": " ".join(grafo(span)), "profondita": max(livelli) + 1 if livelli else 0,
            "stesso_giro": se("stesso_giro", lambda: stesso_giro(span)),
            "avvisi_dopo_sala": se("dopo_sala", lambda: avvisi_dopo_sala(span)),
            "pagine_avvisi": se("pagine", lambda: pagine_avvisi(span)),
            "pagine_ricontrolli": se("pagine", lambda: pagine_ricontrolli(span)),
            "tool_ha_avviso": se("letto", lambda: any(AVVISO_CHIAVE in attr(x, "gen_ai.tool.call.result", "") for x in avvisi_tool)),
            "avvisi_riporta": se("riporta", lambda: any(riporta_avviso(attr(x, "gen_ai.tool.call.result", "")) for x in a_avvisi)),
            "classe_domanda": se("domanda_avvisi", lambda: classe_domanda(domande_ad_avvisi(span)[0]) if a_avvisi else None),
            "avvisi_riporta_primo": se("domanda_avvisi", lambda: bool(a_avvisi) and riporta_avviso(attr(a_avvisi[0], "gen_ai.tool.call.result", ""))),
            "avvisi_con_sala": se("riporta", lambda: any(AVVISI_SALA_B.search(attr(x, "gen_ai.tool.call.arguments", "")) for x in a_avvisi)),
            "sale_da_due": se("sale_due", lambda: sale_da_due(span)),
            "valida_avvisi": se("valida_rivede", lambda: bool(ricontrolli)),
            "valida_avvisi_riporta": se("valida_riporta", lambda: any(riporta_avviso(attr(x, "gen_ai.tool.call.result", "")) for x in ricontrolli)),
            "valida_programma": se("valida_rivede", lambda: bool(archi(span, ("programma",), da="valida"))),
            "avvisi_chiede_programma": se("dialogo", lambda: dialogo(span)),
            "avvisi_poi_riporta": se("dialogo_riporta", lambda: dialogo_riporta(span)),
            "cicli": se("cicli", lambda: cicli(span)),
            "profondita_agenti": se("profondita_agenti", lambda: profondita_agenti(span)),
            "valida_chiamate": None if verdetto is None else len(verdetto),
            "valida_approva": None if verdetto is None else sum(verdetto),
            "email_a_valida": se("email_valida", lambda: any(EMAIL.search(attr(x, "gen_ai.tool.call.arguments", ""))
                                                             for x in archi(span, ("valida",)))),
            "token_agente": se("token", lambda: token_per_agente(span)),
            "quota_avvisi": se("token", lambda: quota_avvisi(span)),
            "costo_agente": se("token", lambda: costo_per_agente(span)),
            "riletture": se("token", lambda: quota_riletture(span))}


def tabella_domande(mm: list[dict]) -> list[str]:
    """La tabella incrociata «domanda di coordina ad avvisi × esito», sulla prima domanda di ogni run (quella dei rami
    paralleli, quando coordina non sa ancora la sala), e per ogni classe quante volte avvisi riporta l'avviso a coordina
    (nella prima risposta e in qualunque giro)."""
    righe = [f"  {'domanda di coordina ad avvisi × esito':<50} {'n':>3} {'giusta':>7} {'avvisata':>9} {'sbagliata':>10}"
             f" {'avvisi riporta (1° giro)':>25} {'(qualunque giro)':>17}"]
    for classe in CLASSI_DOMANDA + (None,):
        gruppo = [m for m in mm if m["classe_domanda"] == classe]
        if not gruppo:
            continue
        nome = {"variazioni": "nomina orario, sala, variazioni...", "sessione": "nomina solo la sessione",
                None: "avvisi non chiamato"}[classe]
        righe.append(f"    {nome:<48} {len(gruppo):>3} " + " ".join(
            f"{sum(m['esito'] == e for m in gruppo):>{w}}" for e, w in zip(ESITI, (7, 9, 10)))
            + f" {sum(m['avvisi_riporta_primo'] for m in gruppo):>25} {sum(bool(m['avvisi_riporta']) for m in gruppo):>17}")
    return righe


def misure(cartelle: list[Path]):
    for cartella in cartelle:
        regs = [json.loads(f.read_text()) for f in sorted(cartella.glob("*.json"))]
        if not regs:
            continue
        print(c("inverso", f" {cartella.name} "))
        for modo in ("guasto", "sana"):
            mm = [misura(r) for r in regs if r["modo"] == modo]
            if not mm:
                continue
            n, strato = len(mm), regs[0]["strato"]
            med = lambda k: statistics.median(m[k] for m in mm)

            def conta(k, minimo, etichetta):  # quante run su n; se lo strato non basta lo dice
                if any(m[k] is None for m in mm):
                    return f"  {etichetta:<52} serve lo strato {minimo}"
                return f"  {etichetta:<52} {sum(bool(m[k]) for m in mm):>2} su {n}"
            print(f"{modo}: n {n} · " + " · ".join(
                f"{e} {sum(1 for m in mm if m['esito'] == e)}" for e in ESITI))
            print(conta("stesso_giro", 2, "programma, sale, avvisi nello stesso giro"))
            print(conta("avvisi_dopo_sala", 2, "avvisi chiamato dopo che si sapeva la sala"))
            print(conta("avvisi_con_sala", 3, "la richiesta ad avvisi nomina la sala B"))
            print(conta("tool_ha_avviso", 3, "leggi_avvisi ha restituito l'avviso sulla sala B"))
            print(conta("avvisi_riporta", 3, "avvisi lo riporta a coordina"))
            if strato >= MINIMO_MISURE["domanda_avvisi"] and modo == "guasto":
                print("\n".join(tabella_domande(mm)))
            print(conta("sale_da_due", 2, "sale chiamato da due chiamanti diversi"))
            print(conta("valida_avvisi", 2, "valida richiede ad avvisi"))
            print(conta("valida_avvisi_riporta", 3, "...e la risposta di avvisi riporta l'avviso"))
            print(conta("valida_programma", 2, "valida richiede a programma"))
            if regs[0].get("correzione") == 3:  # solo la correzione dialogo
                print(conta("avvisi_chiede_programma", 2, "avvisi chiede a programma"))
                print(conta("avvisi_poi_riporta", 3, "...e poi avvisi riporta l'avviso"))
            if strato < MINIMO_MISURE["pagine"]:
                print(f"  {'pagine di avvisi lette':<52} serve lo strato 4")
            else:
                print(f"  {'pagine di avvisi lette da coordina':<52} mediana {med('pagine_avvisi'):.0f} (da {min(m['pagine_avvisi'] for m in mm)} "
                      f"a {max(m['pagine_avvisi'] for m in mm)})")
                print(f"  {'pagine di avvisi nei ricontrolli':<52} mediana {med('pagine_ricontrolli'):.0f} (da {min(m['pagine_ricontrolli'] for m in mm)} "
                      f"a {max(m['pagine_ricontrolli'] for m in mm)})")
            if any(m["valida_approva"] is None for m in mm):
                print(f"  {'valida approva':<52} serve lo strato 3")
            else:
                print(f"  {'valida approva':<52} {sum(m['valida_approva'] > 0 for m in mm):>2} su {n} · "
                      f"mai chiamata in {sum(m['valida_chiamate'] == 0 for m in mm)}")
            print(conta("email_a_valida", 3, "l'email arriva a valida"))
            if strato < MINIMO_MISURE["token"]:
                print(f"  {'token per agente':<52} serve lo strato 2")
            else:
                agenti = sorted({a for m in mm for a in m["token_agente"]})
                print(f"  {'token per agente (mediana)':<52} " + " · ".join(
                    f"{a} {statistics.median(m['token_agente'].get(a, 0) for m in mm):.0f}" for a in agenti))
                print(f"  {'costo per agente, $ (mediana)':<52} " + " · ".join(
                    f"{a} {statistics.median(m['costo_agente'].get(a, 0) for m in mm):.6f}" for a in agenti))
                print(f"  {'quota di avvisi sui token della richiesta':<52} mediana {med('quota_avvisi'):.0%}")
                print(f"  {'quota delle riletture (token in ingresso)':<52} mediana {med('riletture'):.0%}")
            if strato < MINIMO_MISURE["cicli"]:
                print(f"  {'guardia dei cicli scattata':<52} serve lo strato 2")
            else:
                print(f"  {'guardia dei cicli scattata':<52} {sum(m['cicli'] > 0 for m in mm):>2} su {n} · {sum(m['cicli'] for m in mm)} volte"
                      + (" · guardia mai scattata" if not any(m['cicli'] for m in mm) else ""))
                print(f"  massimi: profondità {max(m['profondita'] for m in mm)} (agenti uno dentro l'altro "
                      f"{max(m['profondita_agenti'] for m in mm)}) · span {max(m['span'] for m in mm)}")
            print(f"  mediane: profondità {med('profondita'):.0f} · span {med('span'):.0f} · chiamate al modello "
                  f"{med('chiamate'):.0f} · token {med('token'):.0f} · secondi {med('secondi'):.1f} · $ {med('costo'):.6f}")
            grafi = {}
            for m in mm:
                grafi[m["grafo"]] = grafi.get(m["grafo"], 0) + 1
            if strato < 2:  # senza invoke_agent non c'e' un albero da confrontare
                print(f"  {"forme dell'albero":<52} serve lo strato 2")
            else:
                print(f"  {len(grafi)} forme dell'albero:")
                for g, k in sorted(grafi.items(), key=lambda kv: -kv[1]):
                    print(f"    {k:>2} × {g}")
        print()
