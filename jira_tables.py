"""Tabellarische Auswertungen: reine Funktionen, die aus einer `Analysis` Zeilen (Listen von Wörterbüchern) bauen.

Die Zeilen tragen Zahlen als Zahlen (kein Text); Formatierung übernimmt die Anzeige. `rows_to_csv` schreibt die Datei für Excel mit Dezimalkomma, `rows_to_wiki` und
`rows_to_html` bereiten dieselben Zeilen zum Einfügen in Jira und Confluence auf."""

import html
from dataclasses import replace

import numpy as np

import jira_constants as C
import jira_core as A
from jira_evaluation import Analysis, analyse, de, pct

SUM_LABEL = "Summe"


ROW_COL, OWN_COL, SUM_COL, CHECK_COL = "Ticket", "Story Points (Ticket)", "Summe darunter (direkt)", "Vergleich"
REJECTED_COL, TOTAL_NET_COL, PROGRESS_COL = "Rejected", "Total (ohne Rejected)", "Fortschritt (gewichtet)"


def status_matrix(issues, a: Analysis) -> tuple[list[dict], list[str], str]:
    """Matrix der Status: Zeilen = die Tickets direkt unter der Wurzel (im ganzen Plan die obersten, siehe `summary_level`), Spalten = die Status der zählenden Tickets darunter (nach Gewicht
    geordnet, das Gewicht im Kopf), Zelle = Gewicht (Story Points). Die ersten Spalten vergleichen die eigenen Story Points des Tickets (leer, wenn es keine hat) mit der Summe der Story Points seiner
    direkten Kinder ohne die zurückgewiesenen (leer, wenn keines Story Points hat; Kinder ohne Story Points tragen nichts bei); „Vergleich“ steht nur, wenn beide da sind. Dann die zurückgewiesenen Tickets
    darunter in einer eigenen Spalte, das Total ohne sie, den Anteil der Status ab 90 % („Completed“) und den nach Status und Gewicht gewichteten Fortschritt. Die Matrix folgt Teilprojekt und
    Status-Gewichten der Auswertung. Rückgabe: Zeilen, die Statusspalten und der Name der Completed-Spalte."""
    keep, rej = list(a.atoms), list(a.rejected_atoms)
    w_rej = A.atom_weights(issues, rej, a.settings.unest_rule, basis=keep, plan=a.plan)
    statuses = sorted({issues[i].status for i in keep}, key=lambda st: (a.credits[st], A.new_rank(st), st.lower()))
    heads = {st: st + (f" ({de(a.credits[st])})" if a.credits[st] > 0 else "") for st in statuses}
    done_statuses = [st for st in statuses if a.credits[st] >= C.COMPLETED_MIN_CREDIT - 1e-9]
    completed_col = f"Completed ({'+'.join(done_statuses)})/(Total−Rejected)" if done_statuses else "Completed (kein Status ab 90 %)"
    level = a.level
    chains = A.hierarchy_chains(issues)
    kids = A.children_of(issues)
    rejected = A.rejected_indices(issues)

    def ticket_of(i):
        chain = chains[i]
        return issues[chain[level - 1]] if len(chain) >= level else None

    def label(t):
        return f"(keine Stufe {level})" if t is None else (f"{t.key}: {t.summary}" if t.summary else t.key)

    def children_sum(t):
        given = [issues[j].points for j in kids.get(t.key, []) if j not in rejected and issues[j].points is not None] if t is not None else []
        return float(sum(given)) if given else None

    cells: dict[str, dict] = {}

    def entry(i):
        t = ticket_of(i)
        return cells.setdefault(label(t), {"by_status": {}, "rejected": 0.0, "credited": 0.0, "own": None if t is None else t.points, "sum": children_sum(t)})
    for pos, i in enumerate(keep):
        row = entry(i)
        row["by_status"][issues[i].status] = row["by_status"].get(issues[i].status, 0.0) + float(a.w[pos])
        row["credited"] += float(a.w[pos] * a.c[pos])
    for pos, i in enumerate(rej):
        entry(i)["rejected"] += float(w_rej[pos])

    def build(name, row, check):
        net = sum(row["by_status"].values())
        done = sum(row["by_status"].get(st, 0.0) for st in done_statuses)
        out = {ROW_COL: name, OWN_COL: row["own"], SUM_COL: row["sum"], CHECK_COL: check}
        out.update({heads[st]: row["by_status"].get(st, 0.0) for st in statuses})
        out.update({REJECTED_COL: row["rejected"], TOTAL_NET_COL: net,
                    completed_col: (done / net if net > 0 and done_statuses else None), PROGRESS_COL: (row["credited"] / net if net > 0 else None)})
        return out

    rows = []
    for name in sorted(cells, key=A.natural_key):
        row = cells[name]
        own, summed = row["own"], row["sum"]
        if own is None or summed is None:
            check = ""
        elif abs(summed - own) <= 1e-9:
            check = "gleich"
        else:
            check = f"⚠ weicht ab ({de(summed - own, sign=True)})"
        rows.append(build(name, row, check))
    if rows:
        owns = [c["own"] for c in cells.values() if c["own"] is not None]
        sums = [c["sum"] for c in cells.values() if c["sum"] is not None]
        merged = {"by_status": {st: sum(c["by_status"].get(st, 0.0) for c in cells.values()) for st in statuses}, "rejected": sum(c["rejected"] for c in cells.values()),
                  "credited": sum(c["credited"] for c in cells.values()), "own": float(sum(owns)) if owns else None, "sum": float(sum(sums)) if sums else None}
        rows.append(build(SUM_LABEL, merged, ""))
    return rows, [heads[st] for st in statuses], completed_col


# ---------------------------------------------------------------- Ausgabe: CSV, Wiki-Markup, HTML

def format_cell(value, fmt=None) -> str:
    """Zelle als Text für Jira und Confluence (deutsche Zahlen): Streamlit-Formate „percent“, „%.0f“, „%.1f“, „%.2f“; Ganzzahlen ohne Nachkommastelle; fehlende Werte leer."""
    if value is None or (isinstance(value, float) and value != value):
        return ""
    if isinstance(value, bool):
        return "ja" if value else "nein"
    if isinstance(value, (int, float)):
        if fmt == "percent":
            return pct(value)
        digits = {"%.0f": 0, "%.1f": 1, "%.2f": 2}.get(fmt)
        if digits is None:
            return str(int(value)) if float(value).is_integer() else de(float(value), 1)
        return de(float(value), digits)
    return str(value)


_WIKI_SPECIAL = "\\|{}[]*_"


def _wiki_escape(text: str) -> str:
    return "".join("\\" + ch if ch in _WIKI_SPECIAL else ch for ch in text)


def rows_to_wiki(rows: list[dict], formats: dict | None = None) -> str:
    """Tabelle als Wiki-Markup für Jira- und Confluence-Textfelder (`||Kopf||` und `|Zelle|`); leere Zellen als Leerzeichen, die Summenzeile fett, Sonderzeichen mit Rückstrich geschützt.
    Schlüssel wie ABC-12 verlinkt Jira beim Anzeigen selbst."""
    if not rows:
        return ""
    formats = formats or {}
    lines = ["||" + "||".join(_wiki_escape(h) for h in rows[0]) + "||"]
    for row in rows:
        bold = str(next(iter(row.values()))) == SUM_LABEL
        cells = []
        for name, value in row.items():
            text = _wiki_escape(format_cell(value, formats.get(name)))
            cells.append((f"*{text}*" if bold and text else text) or " ")
        lines.append("|" + "|".join(cells) + "|")
    return "\n".join(lines)


def rows_to_html(rows: list[dict], formats: dict | None = None) -> str:
    """Dieselbe Tabelle als HTML mit eingebetteten Stilen: markieren, kopieren und in Confluence oder ein Jira-Textfeld einfügen übernimmt die Tabelle samt Kopfzeile. Zahlen rechtsbündig."""
    if not rows:
        return ""
    formats = formats or {}
    border = "border:1px solid #c1c7d0;padding:4px 8px;"
    numeric = {name for name in rows[0] if any(isinstance(r[name], (int, float)) and not isinstance(r[name], bool) for r in rows)}
    head = "".join(f'<th style="{border}background:#f4f5f7;text-align:{"right" if n in numeric else "left"};">{html.escape(n)}</th>' for n in rows[0])
    body = []
    for row in rows:
        bold = str(next(iter(row.values()))) == SUM_LABEL
        cells = []
        for name, value in row.items():
            text = html.escape(format_cell(value, formats.get(name)))
            cells.append(f'<td style="{border}text-align:{"right" if name in numeric else "left"};">{f"<strong>{text}</strong>" if bold and text else text}</td>')
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f'<table style="border-collapse:collapse;"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def status_rules_markdown() -> str:
    """Welcher Statusname zählt standardmäßig wie viel? Erst die Regeln in der Reihenfolge, in der sie geprüft werden (der erste Treffer gilt), dann die Auflistung mit Beispielnamen.
    Die Prozentwerte stammen aus `C.STATUS_CLASS_CREDIT`, die Beispiele aus `A.STATUS_EXAMPLES`."""
    pct_of = {name: f"{round(100 * credit)} %" for name, credit in C.STATUS_CLASS_CREDIT.items()}
    examples = {name: ", ".join(names) for name, names in A.STATUS_EXAMPLES.items()}
    return f"""
**Regeln.** Verglichen wird der Name des Status ohne Groß- und Kleinschreibung, Akzente, Umlaut-Punkte und Satzzeichen. Die Regeln werden in dieser Reihenfolge geprüft, der erste Treffer gilt
(„Test Review“ zählt also als Test, nicht als Review):

1. **Zurückgewiesen → zählt nicht.** Der Name enthält Rejected, Declined, Zurückgewiesen, Abgelehnt, Won't do, Will not do, Wontfix, Cancel…, Abgebrochen, Verworfen, Storniert, Abandon…, Duplicate, Duplikat,
   Obsolete, Invalid, Ungültig, Nicht umgesetzt oder Won't implement. Das Ticket und alles unter ihm fällt aus Gewicht und Anzahl.
2. **Verneinung → 0 %.** Not done, Nicht fertig, Unfertig, Nicht erledigt, Unresolved, Unreleased, Not closed, Nicht abgeschlossen, Incomplete, Unvollständig, Unfinished, Not merged, Untested, Ungetestet,
   Unreviewed, Ungeprüft, Nicht überprüft, Not reviewed, Not tested, Not resolved, Not finished, Unmerged, Nicht geschlossen, Unabgeschlossen u. ä.
3. **Fertig → {pct_of['done']}.** Der Name enthält Done, Closed, Resolved, Fertig, Erledigt, Abgeschlossen, Geschlossen, Released, Deployed, Delivered, Ausgeliefert, Complete, Finished, Production, Produktion oder
   Produktiv, endet auf „Prod“ (Ready4Prod) oder enthält das Wort „Live“.
4. **Merged → {pct_of['merged']}.** Merged, Gemerged, Zusammengeführt.
5. **Test → {pct_of['test']}.** Der Name enthält Test (In Test, Testing, Ready4Test), Abnahme, Acceptance, Verif… oder Validat…, oder ist das Wort QA oder UAT.
6. **Review → {pct_of['review']}.** Review, Überprüf…, Geprüft, Prüfung, Prüfen, Begutachtung.
7. **Alles andere → 0 %** (In Arbeit, In Progress, On Hold, Backlog, To Do, Specification …).

**Auflistung** (Beispielnamen, nicht vollständig):

| Gewicht | Beispiele |
|---|---|
| {pct_of['done']} | {examples['done']} |
| {pct_of['test']} | {examples['test']} |
| {pct_of['merged']} | {examples['merged']} |
| {pct_of['review']} | {examples['review']} |
| 0 % | {examples['other']} |
| zählt nicht | {examples['rejected']} |

Jedes Gewicht lässt sich nach dem Laden in der Tabelle „Gewichte der Status“ ändern, falls ein Status anders heißt, als sein Name vermuten lässt. Die Namen, die in euren Daten vorkommen, stehen dort mit ihrem
Standardgewicht.
"""


def unestimated_rule_comparison(issues, a: Analysis) -> list[dict]:
    """Wirkung der wählbaren Regeln für Tickets ohne Story Points auf die vorliegenden Daten: je Regel der Gesamtfortschritt, das Gesamtgewicht und die Zahl der Tickets ohne Story Points.
    Alles andere (Teilprojekt, Status-Gewichte) wie in der aktuellen Auswertung."""
    rows = []
    for rule in C.UNEST_RULES:
        b = analyse(issues, replace(a.settings, unest_rule=rule), a.plan)
        rows.append({"Regel": rule, "Fortschritt": None if np.isnan(b.progress) else float(b.progress), "Gewicht gesamt": float(b.weight), "Tickets ohne Story Points": b.n_unestimated})
    return rows


def subtask_rule_comparison(issues, a: Analysis) -> list[dict]:
    """Wirkung der Regeln für Sub-Tasks auf die vorliegenden Daten: je Regel der Gesamtfortschritt, das Gesamtgewicht und die Zahl der zählenden Tickets. Alles andere wie in der aktuellen Auswertung."""
    rows = []
    for rule in C.SUB_RULES:
        b = analyse(issues, replace(a.settings, sub_rule=rule), a.plan)
        rows.append({"Regel": rule, "Fortschritt": None if np.isnan(b.progress) else float(b.progress), "Gewicht gesamt": float(b.weight), "Zählende Tickets": b.n_atoms})
    return rows


UNEST_OPTIONS_MARKDOWN = """
Ein Ticket ohne Story Points braucht ein Gewicht, sonst fehlt es im Fortschritt. Dafür gibt es mehrere Möglichkeiten. Zwei Fragen sind getrennt zu entscheiden (beide haben ein Auswahlmenü in der Seitenleiste): **aus welcher Vergleichsgruppe** der Ersatzwert kommt
(Teil 1) und **wie mit Sub-Tasks** umzugehen ist, deren Story Points fehlen (Teil 2). Was „Stand“ als *wählbar* ausweist, steht in der Seitenleiste unter „Tickets ohne Story Points“ bzw. „Sub-Tasks einer Story“ zur Wahl (mit dem Buchstaben der Variante); alles andere ist ein **Vorschlag** und noch nicht
eingebaut. Vor- und Nachteile sind Überlegungen zur Methode, keine Messungen an euren Daten.

### Teil 1: Woher kommt das Gewicht eines Tickets ohne Story Points?

| Variante | Vergleichsgruppe | Vorteile | Nachteile | Stand |
|---|---|---|---|---|
| **A. Median der Stufe im Teilbaum** | geschätzte Blätter derselben Tiefe im gewählten Teilbaum (Tiefe ab der Wurzel) | Das Teilprojekt ist ein eigenständiger Datensatz; einfach zu erklären; Stories und Sub-Tasks werden nicht gemischt | Gewichte und Fortschritt ändern sich mit dem gewählten Teilbaum; „Stufe“ ist die Tiefe, nicht der Typ (ein Bug ohne Epic liegt auf einer anderen Stufe als Stories unter Epics); bei wenigen geschätzten Tickets wackelt der Median | wählbar, Voreinstellung |
| **B. Median der Stufe im ganzen Plan** | geschätzte Blätter derselben Tiefe im ganzen Plan | Dasselbe Ticket wiegt in jeder Ansicht gleich; ein Teilprojekt ist ein Ausschnitt der Gesamtansicht; größere Datenbasis | Das Teilprojekt ist nicht mehr eigenständig, Tickets außerhalb bestimmen die Gewichte; mischt Teams mit unterschiedlicher Story-Point-Skala | wählbar |
| **C. Median je Ticket-Typ** | geschätzte Blätter desselben Typs (Story, Task, Bug, Sub-Task) im gewählten Teilbaum | Vergleicht Gleiches (Bugs sind oft kleiner als Stories), unabhängig von der Tiefe | Seltene Typen haben kaum geschätzte Tickets; Typnamen und Konventionen unterscheiden sich je Jira-Instanz | wählbar |
| **D. Median der Geschwister** | geschätzte Tickets mit demselben übergeordneten Ticket | Lokal: passt zur Größe des Epics bzw. der Story und zur Skala des Teams | Oft gibt es zu wenige oder keine geschätzten Geschwister (Sub-Tasks einer Story); Gewichte schwanken von Epic zu Epic | wählbar |
| **E. Median je Team** | geschätzte Blätter desselben Teams (Spalte Team; ohne Team bilden die Tickets ohne Team eine Gruppe) im gewählten Teilbaum | Story Points gelten nur innerhalb eines Teams: Das ist die vergleichbarste Gruppe | Das Team-Feld ist oft leer; dünne Datenbasis je Team | wählbar |
| **F. Rückfallkette** | Geschwister → gleicher Typ → gleiche Stufe (je im Teilbaum) → alle geschätzten Tickets des ganzen Plans → 1 | Nutzt die genaueste vorhandene Basis und fällt nur auf 1 zurück, wenn nirgends etwas geschätzt ist | Das Gewicht eines Tickets hängt davon ab, was in seiner Nähe geschätzt ist; schwerer zu erklären und nachzurechnen | wählbar |
| **G. Mittelwert statt Median** | wie A oder B | Nutzt alle Werte | Ausreißer (ein Ticket mit 21 Story Points) verschieben ihn stark; der Median ist robuster | Vorschlag, nicht empfohlen |
| **H. Als 1 Story Point** | keine | Einfach, transparent, unabhängig von den Daten | Verzerrt, wenn typische Tickets größer sind: ungeschätzte Tickets wirken zu leicht, der Fortschritt fällt zu hoch aus, wenn sie offen sind | wählbar |
| **I. Nicht zählen** | keine | Keine erfundenen Gewichte | Offene, ungeschätzte Tickets verschwinden aus dem Fortschritt, die Zahl wird zu optimistisch; bei vielen ungeschätzten Tickets kaum aussagekräftig | wählbar |

### Teil 2: Sub-Tasks ohne Story Points

Seit nur Blätter zählen, zählt eine Story mit Sub-Tasks durch ihre Sub-Tasks. Haben diese keine Story Points, gilt für sie die Regel aus Teil 1; die Story Points der Story selbst fallen weg.

| Variante | Vorteile | Nachteile | Stand |
|---|---|---|---|
| **a. Sub-Tasks wie ungeschätzte Tickets** | Einheitliche Regel für alle Blätter | Die Story Points der Story fallen weg; die Summe der Sub-Tasks weicht von der Story ab; eine Story mit vielen Sub-Tasks wiegt mehr als eine mit wenigen | wählbar, Voreinstellung |
| **b. Story Points der Story gleichmäßig auf die Sub-Tasks verteilen** (nur wenn keine Sub-Task eigene Story Points hat) | Das Gewicht der Story bleibt erhalten, „Epic vs. Total“ in der Status-Matrix stimmt, keine erfundenen Zahlen | Annahme gleich großer Sub-Tasks; setzt eine geschätzte Story voraus; Mischformen (einige Sub-Tasks geschätzt, andere nicht) brauchen eine Zusatzregel | wählbar |
| **c. Story zählt selbst, Sub-Tasks bleiben außen vor** (frühere Fassung) | Die Story Points der Planung bleiben das Gewicht | Der Fortschritt der Sub-Tasks bleibt unsichtbar, bis der Status der Story wechselt | wählbar |

### Einschätzung

Das ist eine Einschätzung, keine Messung. Kommt es auf **vergleichbare Zahlen zwischen Teilprojekten** an (z. B. ein Bericht je Epic), sprechen B oder F dafür, die Vergleichsgruppe nicht vom gewählten Teilbaum abhängen zu lassen. Soll ein **Teilprojekt für sich stehen**, ist A richtig.
Für **Sub-Tasks ohne Story Points** ist b am nächsten an der Planung. Wie stark die Wahl die Zahl verschiebt, zeigt die Tabelle am Ende für alle wählbaren Regeln an den geladenen Daten (sobald eine Datei geladen ist); für den Vorschlag G gibt es keine Zahlen.
"""


def rows_to_csv(rows: list[dict]) -> bytes:
    """CSV für Excel im deutschen Raum: Semikolon, Dezimalkomma, UTF-8 mit Kennung. Zahlen unverändert genau, leere Zellen für None, Semikolon in Text durch Komma ersetzt."""
    if not rows:
        return "".encode("utf-8-sig")

    def cell(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return ""
        if isinstance(v, float):
            return repr(v).replace(".", ",")
        return str(v).replace(";", ",").replace("\n", " ")
    header = list(rows[0])
    lines = [";".join(h.replace(";", ",") for h in header)] + [";".join(cell(r.get(h)) for h in header) for r in rows]
    return ("\n".join(lines) + "\n").encode("utf-8-sig")
