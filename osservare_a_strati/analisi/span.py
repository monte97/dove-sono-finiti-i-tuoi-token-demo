"""Lettura degli span: attributi, token, ordine, archi e le forme che il modello decide."""
import json

from ..modello import MODEL, costo
from ..valutazione import approva, riporta_avviso


def attr(s, chiave, altrimenti=None):
    return s["attributi"].get(chiave, altrimenti)


def token(s):
    if "gen_ai.usage.input_tokens" not in s["attributi"]:
        return None
    return {"in": attr(s, "gen_ai.usage.input_tokens"), "cache": attr(s, "gen_ai.usage.cache_read.input_tokens") or 0,
            "out": attr(s, "gen_ai.usage.output_tokens") or 0, "pensiero": attr(s, "gen_ai.usage.reasoning.output_tokens") or 0}


def in_ordine(span):
    figli, ids, fuori = {}, {s["id"] for s in span}, []
    for s in span:
        figli.setdefault(s["padre"], []).append(s)

    def giu(s, livello):
        fuori.append((s, livello))
        for f in sorted(figli.get(s["id"], []), key=lambda x: x["inizio"]):
            giu(f, livello + 1)

    for radice in sorted((s for s in span if s["padre"] not in ids), key=lambda x: x["inizio"]):
        giu(radice, 0)
    return fuori


def agente_di(s, per_id):
    while s:
        if attr(s, "gen_ai.operation.name") == "invoke_agent":
            return attr(s, "gen_ai.agent.name", "?")
        s = per_id.get(s["padre"])
    return "?"


def per_trace(span) -> dict:
    gruppi = {}
    for s in span:
        gruppi.setdefault(s["trace"], []).append(s)
    return dict(sorted(gruppi.items(), key=lambda kv: min(x["inizio"] for x in kv[1])))


# I thread di uno stesso giro partono a pochi millisecondi uno dall'altro: se uno strumento istantaneo (leggi_programma)
# finisce prima che parta il fratello (un agente), sono comunque dello stesso giro. Un giro dopo, invece, parte dopo una
# chiamata al modello (secondi).
SCARTO_GIRO_S = 0.02


def grafo(span) -> list[str]:
    """Chi ha chiamato che cosa, in una forma che non dipende da chi e' partito prima nei rami paralleli.

    Le chiamate figlie dello stesso invoke_agent che partono mentre una del giro e' ancora in corso sono dello
    stesso giro (il modello le ha chieste insieme): si scrivono come insieme ordinato, `{avvisi,programma,sale}`.
    Dentro un'agente-strumento, fra parentesi, cosa ha chiamato a sua volta; `!` se lo span e' in errore."""
    figli = {}
    for x in span:
        figli.setdefault(x["padre"], []).append(x)
    e = lambda x, operazione: attr(x, "gen_ai.operation.name") == operazione

    def giri(agente_span):
        chiamate = sorted((x for x in figli.get(agente_span["id"], []) if e(x, "execute_tool")), key=lambda x: x["inizio"])
        gruppi = []
        for x in chiamate:
            if gruppi and (x["inizio"] < max(y["fine"] for y in gruppi[-1])  # parte mentre una del giro e' ancora in corso
                           or x["inizio"] - gruppi[-1][0]["inizio"] < SCARTO_GIRO_S):  # o subito dopo: uno strumento istantaneo
                gruppi[-1].append(x)
            else:
                gruppi.append([x])
        return gruppi

    def voce(gruppo):
        nomi = []
        for x in gruppo:
            dentro = " ".join(voce(g) for a in sorted((a for a in figli.get(x["id"], []) if e(a, "invoke_agent")),
                                                     key=lambda a: a["inizio"]) for g in giri(a))
            nomi.append(attr(x, "gen_ai.tool.name") + ("!" if x["errore"] else "") + (f"({dentro})" if dentro else ""))
        return nomi[0] if len(nomi) == 1 else "{" + ",".join(sorted(nomi)) + "}"

    per_id, passi = {x["id"]: x for x in span}, []
    radici = sorted((x for x in span if e(x, "invoke_agent")
                     and not (per_id.get(x["padre"]) and e(per_id[x["padre"]], "execute_tool"))), key=lambda x: x["inizio"])
    for a in radici:
        nome = attr(a, "gen_ai.agent.name")
        passi.append(f"codice>{nome}")  # un agente chiamato dal codice, non da un modello
        passi += [f"{nome}>{voce(g)}" for g in giri(a)]
    return passi


def domande_ad_avvisi(span) -> list[str]:
    """Gli argomenti `richiesta` degli archi coordina -> avvisi, nell'ordine in cui sono partiti."""
    fuori = []
    for x in archi(span, ("avvisi",), da="coordina"):
        try:
            fuori.append(str(json.loads(attr(x, "gen_ai.tool.call.arguments", "{}")).get("richiesta", "")))
        except (ValueError, AttributeError):
            fuori.append("")
    return fuori


def archi(span, verso=None, da=None) -> list:
    """Gli archi fra agenti (execute_tool con destinazione), in ordine di inizio, magari solo verso certi agenti
    e/o solo chiamati da un certo agente."""
    return sorted((x for x in span if attr(x, "gen_ai.operation.name") == "execute_tool"
                   and attr(x, "gen_ai.transfer.target.name") and (verso is None or attr(x, "gen_ai.transfer.target.name") in verso)
                   and (da is None or attr(x, "gen_ai.agent.name") == da)),
                  key=lambda x: x["inizio"])


def strumenti(span, nome: str) -> list:
    return [x for x in span if attr(x, "gen_ai.operation.name") == "execute_tool" and attr(x, "gen_ai.tool.name") == nome
            and not attr(x, "gen_ai.transfer.target.name")]


def stesso_giro(span) -> bool:
    """programma, sale e avvisi sono partiti insieme: gli archi hanno lo stesso padre e si sovrappongono nel tempo."""
    primi = {}
    for x in archi(span, ("programma", "sale", "avvisi"), da="coordina"):  # le chiamate annidate non contano
        primi.setdefault(attr(x, "gen_ai.transfer.target.name"), x)
    tre = list(primi.values())
    return len(tre) == 3 and len({x["padre"] for x in tre}) == 1 and max(x["inizio"] for x in tre) < min(x["fine"] for x in tre)


def avvisi_dopo_sala(span) -> bool:
    """avvisi e' stato chiamato quando programma o sale avevano gia' finito: coordina sapeva gia' la sala."""
    precedenti = archi(span, ("programma", "sale"), da="coordina")
    return any(p["fine"] <= a["inizio"] for a in archi(span, ("avvisi",), da="coordina") for p in precedenti)


def sale_da_due(span) -> bool:
    """sale e' stato chiamato da due agenti diversi (coordina e programma): lo stesso dato letto per due strade."""
    return len({attr(x, "gen_ai.agent.name") for x in archi(span, ("sale",))}) >= 2


def figli_arco(span, arco):
    """Gli archi che l'agente chiamato da `arco` ha chiamato a sua volta."""
    dentro = {x["id"] for x in span if x["padre"] == arco["id"] and attr(x, "gen_ai.operation.name") == "invoke_agent"}
    return [x for x in archi(span) if x["padre"] in dentro]


def dialogo(span) -> bool:
    """avvisi ha chiesto a programma (la correzione dialogo)."""
    return bool(archi(span, ("programma",), da="avvisi"))


def dialogo_riporta(span) -> bool:
    """...e poi la sua risposta riporta l'avviso sulla sala B."""
    return any(riporta_avviso(attr(a, "gen_ai.tool.call.result", "")) for a in archi(span, ("avvisi",))
               if any(attr(f, "gen_ai.transfer.target.name") == "programma" for f in figli_arco(span, a)))


def cicli(span) -> int:
    """Quante volte la guardia ha rifiutato una chiamata (archi in errore con error.type ciclo)."""
    return sum(attr(x, "error.type") == "ciclo" for x in archi(span))


def profondita_agenti(span) -> int:
    """Quanti agenti uno dentro l'altro, contando gli archi da coordina in giu': il ramo piu' lungo."""
    per_id, fondo = {x["id"]: x for x in span}, 0
    for a in archi(span):
        n, y = 0, a
        while y:
            n += attr(y, "gen_ai.transfer.target.name") is not None and attr(y, "gen_ai.operation.name") == "execute_tool"
            y = per_id.get(y["padre"])
        fondo = max(fondo, n)
    return fondo


def _letture_avvisi(span, di_coordina: bool) -> int:
    """Pagine lette da leggi_avvisi: quelle sotto l'arco di avvisi chiamato da coordina, oppure tutte le altre."""
    per_id, tot = {x["id"]: x for x in span}, 0
    for x in strumenti(span, "leggi_avvisi"):
        y = per_id.get(x["padre"])
        while y and not (attr(y, "gen_ai.operation.name") == "execute_tool" and attr(y, "gen_ai.transfer.target.name")):
            y = per_id.get(y["padre"])
        if (y is not None and attr(y, "gen_ai.agent.name") == "coordina") == di_coordina:
            tot += attr(x, "avvisi.pagine", 0)
    return tot


def pagine_avvisi(span) -> int:
    """Le pagine che legge l'avvisi chiamato da coordina: il numero della slide."""
    return _letture_avvisi(span, True)


def pagine_ricontrolli(span) -> int:
    """Le pagine lette da leggi_avvisi sotto qualunque altro chiamante (i ricontrolli di valida, il dialogo)."""
    return _letture_avvisi(span, False)


def verdetti(span) -> list[bool]:
    return [approva(attr(x, "gen_ai.tool.call.result")) for x in archi(span, ("valida",))
            if attr(x, "gen_ai.tool.call.result") is not None]


def token_per_agente(span) -> dict:
    """Token (ingresso e uscita) delle chiamate al modello, per agente che le ha fatte."""
    per_id, fuori = {x["id"]: x for x in span}, {}
    for x in span:
        if t := token(x):
            nome = agente_di(x, per_id)
            fuori[nome] = fuori.get(nome, 0) + t["in"] + t["out"]
    return fuori


def chiamate_dagli_span(span) -> list[dict]:
    """Le chiamate al modello ricostruite dagli span, dallo strato 2 in su, in ordine di fine: l'agente e il suo
    invoke_agent (lo span corrente quando la riga di log parte), la fine e il conto con i nomi del provider. Servono a
    strati cruscotto invia: le registrazioni del banco del 5/11 sono di prima delle righe per chiamata e delle metriche,
    e righe e misure si rifanno da qui, con le cifre di quella run. L'SDK scrive gen_ai.usage.input_tokens con la cache
    dentro."""
    per_id, fuori = {x["id"]: x for x in span}, []
    for x in sorted(span, key=lambda x: x["fine"]):
        if (t := token(x)) is None:
            continue
        y = x
        while y and attr(y, "gen_ai.operation.name") != "invoke_agent":
            y = per_id.get(y["padre"])
        if y is None:  # sotto lo strato 2 l'agente non si sa
            continue
        scritti = attr(x, "gen_ai.usage.cache_write.input_tokens") or 0
        fuori.append({"agente": attr(y, "gen_ai.agent.name"), "span": y["id"], "trace": x["trace"], "fine": x["fine"],
                      "campi": {"gen_ai.agent.name": attr(y, "gen_ai.agent.name"),
                                "gen_ai.response.model": attr(x, "gen_ai.response.model", MODEL),
                                "gen_ai.usage.input_tokens": t["in"], "gen_ai.usage.output_tokens": t["out"],
                                "gen_ai.usage.cache_read.input_tokens": t["cache"],
                                "gen_ai.usage.cache_write.input_tokens": scritti}})
    return fuori


def costo_per_agente(span) -> dict:
    """Costo in $ (a LISTINO) delle chiamate al modello, per agente che le ha fatte."""
    per_id, fuori = {x["id"]: x for x in span}, {}
    for x in span:
        if t := token(x):
            nome = agente_di(x, per_id)
            fuori[nome] = fuori.get(nome, 0) + costo(t["in"], t["cache"], t["out"])
    return fuori


def quota_riletture(span) -> float | None:
    """Quota dei token in ingresso che il modello rilegge. In ogni invoke_agent, ogni chiamata dopo la prima rilegge
    la conversazione fin li': conta i token in ingresso della chiamata precedente dello stesso invoke_agent. La quota
    e' la somma di questi sulla somma dei token in ingresso di tutte le chiamate (None se non ci sono token)."""
    per_id, per_invoke = {x["id"]: x for x in span}, {}
    for x in span:
        if token(x):
            y = x
            while y and attr(y, "gen_ai.operation.name") != "invoke_agent":
                y = per_id.get(y["padre"])
            per_invoke.setdefault(y["id"] if y else None, []).append(x)
    totale = sum(token(x)["in"] for xs in per_invoke.values() for x in xs)
    riletti = sum(token(a)["in"] for xs in per_invoke.values() for a, _ in zip(sorted(xs, key=lambda x: x["inizio"]), xs[1:]))
    return riletti / totale if totale else None


def quota_avvisi(span) -> float | None:
    """Che parte dei token della richiesta e' spesa dall'agente avvisi (None se non ci sono token)."""
    per_agente = token_per_agente(span)
    return per_agente.get("avvisi", 0) / sum(per_agente.values()) if per_agente else None


def archi_della_run(span) -> dict:
    """Per una run: {(chiamante, chiamato): quante volte}, con gli strumenti dei dati (leggi_*) come foglie.
    Il chiamante di uno strumento dei dati e' l'agente dell'invoke_agent che lo contiene."""
    per_id, fuori = {x["id"]: x for x in span}, {}
    for x in span:
        if attr(x, "gen_ai.operation.name") != "execute_tool":
            continue
        if attr(x, "gen_ai.transfer.target.name"):
            chiave = (attr(x, "gen_ai.agent.name"), attr(x, "gen_ai.transfer.target.name"))
        else:
            padre = per_id.get(x["padre"])
            chiave = (attr(padre, "gen_ai.agent.name") if padre else None, attr(x, "gen_ai.tool.name"))
        if chiave[0] and chiave[1]:
            fuori[chiave] = fuori.get(chiave, 0) + 1
    return fuori
