"""Tabellarische Auswertungen: reine Funktionen, die aus einer `Analysis` Zeilen (Listen von Wörterbüchern) bauen.

Die Zeilen tragen Zahlen als Zahlen (kein Text); Formatierung übernimmt die Anzeige. `rows_to_csv` schreibt die Datei für Excel (Semikolon, Dezimalkomma), `rows_to_wiki` und
`rows_to_html` bereiten dieselben Zeilen zum Einfügen in Jira und Confluence auf."""

import html
from dataclasses import replace

import numpy as np

import jira_constants as C
import jira_core as A
from jira_evaluation import Analysis, credit_text, de, headline, pct

SUM_LABEL = "Summe"


ROW_COL = "Ticket"
REJECTED_COL, TOTAL_NET_COL, PROGRESS_COL = "Rejected", "Total (ohne Rejected)", "Fortschritt (gewichtet)"


def _row_tickets(issues, a: Analysis):
    """Die Zeilen der Tabellen je Ticket unter der Wurzel: `ticket_of(i)` ist das Ticket der Zusammenfassungsstufe, zu dem das Atom `i` gehört (None, wenn es keine solche Stufe gibt), `label(t)` seine Beschriftung."""
    level = a.level
    chains = A.hierarchy_chains(issues, a.ctx)

    def ticket_of(i):
        chain = chains[i]
        return issues[chain[level - 1]] if len(chain) >= level else None

    def label(t):
        return f"(keine Stufe {level})" if t is None else (f"{t.key}: {t.summary}" if t.summary else t.key)
    return ticket_of, label


def status_matrix(issues, a: Analysis) -> tuple[list[dict], list[str], str]:
    """Matrix der Status: Zeilen = die Tickets direkt unter der Wurzel (im ganzen Plan die obersten, siehe `summary_level`), Spalten = die Status der zählenden Tickets darunter (nach Gewicht
    geordnet, das Gewicht im Kopf), Zelle = Gewicht (Story Points). Dazu die zurückgewiesenen Tickets darunter in einer eigenen Spalte, das Total ohne sie, den Anteil der Status ab 90 %
    („Completed“) und den nach Status und Gewicht gewichteten Fortschritt. Die Matrix folgt Teilprojekt und Status-Gewichten der Auswertung. Rückgabe: Zeilen, die Statusspalten und der Name
    der Completed-Spalte."""
    keep, rej = list(a.atoms), list(a.rejected_atoms)
    w_rej = A.atom_weights(issues, rej, a.settings.unest_rule, basis=keep, plan=a.plan, subtasks_out=a.settings.sub_rule == C.SUB_SELF)
    statuses = sorted({issues[i].status for i in keep}, key=lambda st: (a.credits[st], A.new_rank(st), st.lower()))
    heads = {st: st + (f" ({credit_text(a.credits[st])})" if a.credits[st] > 0 else "") for st in statuses}
    done_statuses = [st for st in statuses if a.credits[st] >= C.COMPLETED_MIN_CREDIT - 1e-9]
    completed_col = f"Completed ({'+'.join(done_statuses)})/(Total−Rejected)" if done_statuses else "Completed (kein Status ab 90 %)"
    ticket_of, label = _row_tickets(issues, a)
    cells: dict[str, dict] = {}

    def entry(i):
        t = ticket_of(i)
        return cells.setdefault(label(t), {"by_status": {}, "rejected": 0.0, "credited": 0.0})
    for pos, i in enumerate(keep):
        row = entry(i)
        row["by_status"][issues[i].status] = row["by_status"].get(issues[i].status, 0.0) + float(a.w[pos])
        row["credited"] += float(a.w[pos] * a.c[pos])
    for pos, i in enumerate(rej):
        entry(i)["rejected"] += float(w_rej[pos])

    def build(name, row):
        net = sum(row["by_status"].values())
        done = sum(row["by_status"].get(st, 0.0) for st in done_statuses)
        out = {ROW_COL: name}
        out.update({heads[st]: row["by_status"].get(st, 0.0) for st in statuses})
        out.update({REJECTED_COL: row["rejected"], TOTAL_NET_COL: net,
                    completed_col: (done / net if net > 0 and done_statuses else None), PROGRESS_COL: (row["credited"] / net if net > 0 else None)})
        return out

    rows = [build(name, cells[name]) for name in sorted(cells, key=A.natural_key)]
    if rows:
        merged = {"by_status": {st: sum(c["by_status"].get(st, 0.0) for c in cells.values()) for st in statuses}, "rejected": sum(c["rejected"] for c in cells.values()),
                  "credited": sum(c["credited"] for c in cells.values())}
        rows.append(build(SUM_LABEL, merged))
    return rows, [heads[st] for st in statuses], completed_col


SPRINT_COL, TICKETS_COL, SPRINT_WEIGHT_COL, SPRINT_DONE_COL = "Sprint", "Tickets", "Gewicht (SP)", "Nur Done, nach Gewicht"
CARRIED_COUNT_COL, CARRIED_WEIGHT_COL = "Mitgenommene Tickets", "Mitgenommenes Gewicht (SP)"


def has_sprints(issues) -> bool:
    """Hat mindestens ein Ticket einen Sprint?"""
    return any(t.sprints for t in issues)


def sprint_rows(issues, a: Analysis) -> list[dict]:
    """Je Sprint die zählenden Tickets, deren letzter Sprint er ist (siehe `A.sprint_labels`): Zahl, Gewicht, gewichteter Fortschritt, „nur Done“ nach Gewicht und die mitgenommenen Tickets, die schon in
    einem früheren Sprint standen (mehr als ein Sprint), mit ihrem Gewicht. Eine Summenzeile am Ende. Alles wie in der Auswertung `a` (Teilprojekt, Regeln, Status-Gewichte)."""
    sprints = A.ticket_sprints(issues, a.ctx)
    groups: dict[str, dict] = {}
    for pos, (i, label) in enumerate(zip(a.atoms, A.sprint_labels(issues, a.atoms, a.ctx), strict=True)):
        g = groups.setdefault(label, {"n": 0, "w": 0.0, "credited": 0.0, "done": 0.0, "carried": 0, "carried_w": 0.0})
        w = float(a.w[pos])
        g["n"] += 1
        g["w"] += w
        g["credited"] += w * float(a.c[pos])
        g["done"] += w if a.done[pos] else 0.0
        if len(sprints[i]) > 1:
            g["carried"] += 1
            g["carried_w"] += w

    def build(name, g):
        return {SPRINT_COL: name, TICKETS_COL: g["n"], SPRINT_WEIGHT_COL: g["w"], PROGRESS_COL: g["credited"] / g["w"] if g["w"] > 0 else None,
                SPRINT_DONE_COL: g["done"] / g["w"] if g["w"] > 0 else None, CARRIED_COUNT_COL: g["carried"], CARRIED_WEIGHT_COL: g["carried_w"]}
    rows = [build(name, groups[name]) for name in sorted(groups, key=A.natural_key)]
    if rows:
        rows.append(build(SUM_LABEL, {key: sum(g[key] for g in groups.values()) for key in ("n", "w", "credited", "done", "carried", "carried_w")}))
    return rows


JIRA_PROGRESS_COL, JIRA_DONE_COL, JIRA_LEFT_COL = "Jira: Fortschritt (%)", "Jira: abgeschlossen (SP)", "Jira: verbleibend (SP)"
OWN_DONE_COL, OWN_TOTAL_COL, GAP_COL = "Hier: Nur Done, nach Gewicht", "Hier: Total (ohne Rejected, SP)", "Abstand Jira − hier (Punkte)"


JIRA_TOLERANCE = 0.01      # erlaubter Abstand zwischen Jiras Fortschritt (%) und dem aus abgeschlossen und verbleibend berechneten: ein Prozentpunkt (Rundung auf ganze Prozent)
DERIVED_COL = "Aus abgeschlossen und verbleibend"


def jira_consistency(issues) -> tuple[int, list[dict]]:
    """Passen Jiras drei Fortschrittsspalten zusammen? Für jedes Ticket mit allen drei Werten wird „Fortschritt (%)“ mit abgeschlossen ÷ (abgeschlossen + verbleibend) verglichen. Rückgabe: Zahl der
    geprüften Tickets und die Tickets, deren Abstand über `JIRA_TOLERANCE` liegt (Zeilen mit Schlüssel, Jiras Werten, dem berechneten Wert und dem Abstand in Prozentpunkten)."""
    checked, bad = 0, []
    for t in issues:
        if t.jira_progress is None or t.jira_done is None or t.jira_left is None or t.jira_done + t.jira_left <= 0:
            continue
        checked += 1
        derived = t.jira_done / (t.jira_done + t.jira_left)
        if abs(t.jira_progress - derived) > JIRA_TOLERANCE + 1e-9:
            bad.append({ROW_COL: t.key, JIRA_PROGRESS_COL: t.jira_progress, JIRA_DONE_COL: t.jira_done, JIRA_LEFT_COL: t.jira_left, DERIVED_COL: derived, GAP_COL: 100 * (t.jira_progress - derived)})
    return checked, bad


def has_jira_progress(issues) -> bool:
    """Steht in den Daten Jiras eigener Fortschritt (Spalte „Fortschritt (%)“) bei mindestens einem Ticket?"""
    return any(t.jira_progress is not None for t in issues)


def jira_crosscheck(issues, a: Analysis) -> list[dict]:
    """Gegenprobe zu Jiras eigener Fortschrittsspalte: je Ticket direkt unter der Wurzel (dieselben Zeilen wie die Status-Matrix) Jiras Werte für dieses Ticket und der Wert „nur Done, nach
    Gewicht“ aus den zählenden Tickets darunter, dazu der Abstand in Prozentpunkten. Jiras Werte gelten für das Ticket selbst mit allem darunter; wie Jira rechnet, steht nicht in den Daten."""
    ticket_of, label = _row_tickets(issues, a)
    groups: dict[str, dict] = {}
    for pos, i in enumerate(a.atoms):
        t = ticket_of(i)
        g = groups.setdefault(label(t), {"ticket": t, "total": 0.0, "done": 0.0})
        g["total"] += float(a.w[pos])
        g["done"] += float(a.w[pos]) if a.done[pos] else 0.0
    rows = []
    for name in sorted(groups, key=A.natural_key):
        t, total = groups[name]["ticket"], groups[name]["total"]
        own = groups[name]["done"] / total if total > 0 else None
        jira = None if t is None else t.jira_progress
        rows.append({ROW_COL: name, JIRA_PROGRESS_COL: jira, JIRA_DONE_COL: None if t is None else t.jira_done, JIRA_LEFT_COL: None if t is None else t.jira_left,
                     OWN_DONE_COL: own, OWN_TOTAL_COL: total, GAP_COL: None if jira is None or own is None else 100 * (jira - own)})
    return rows


# ---------------------------------------------------------------- Ausgabe: CSV, Wiki-Markup, HTML

def format_cell(value, fmt=None) -> str:
    """Zelle als Text für Jira und Confluence (Dezimalpunkt): Streamlit-Formate „percent“, „%.0f“, „%.1f“, „%.2f“; Ganzzahlen ohne Nachkommastelle; fehlende Werte leer."""
    if value is None or (isinstance(value, float) and value != value):
        return ""
    if isinstance(value, bool):
        return "ja" if value else "nein"
    if isinstance(value, (int, float)):
        if fmt == "percent":
            return pct(value)
        digits = {"%.0f": 0, "%.1f": 1, "%.2f": 2}.get(fmt)
        if digits is None:
            return str(int(value)) if float(value).is_integer() else de(float(value), 2)
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


def unestimated_rule_comparison(issues, a: Analysis) -> list[dict]:
    """Wirkung der wählbaren Regeln für Tickets ohne Story Points auf die vorliegenden Daten: je Regel der Gesamtfortschritt, das Gesamtgewicht und die Zahl der Tickets ohne Story Points.
    Alles andere (Teilprojekt, Status-Gewichte) wie in der aktuellen Auswertung."""
    rows = []
    for rule in C.UNEST_RULES:
        progress, weight, n_unestimated, _ = headline(issues, replace(a.settings, unest_rule=rule), a.plan, a.ctx)
        rows.append({"Regel": rule, "Fortschritt": None if np.isnan(progress) else float(progress), "Gewicht gesamt": float(weight), "Tickets ohne Story Points": n_unestimated})
    return rows


def subtask_rule_comparison(issues, a: Analysis) -> list[dict]:
    """Wirkung der Regeln für Sub-Tasks auf die vorliegenden Daten: je Regel der Gesamtfortschritt, das Gesamtgewicht und die Zahl der zählenden Tickets. Alles andere wie in der aktuellen Auswertung."""
    rows = []
    for rule in C.SUB_RULES:
        progress, weight, _, n_atoms = headline(issues, replace(a.settings, sub_rule=rule), a.plan, a.ctx)
        rows.append({"Regel": rule, "Fortschritt": None if np.isnan(progress) else float(progress), "Gewicht gesamt": float(weight), "Zählende Tickets": n_atoms})
    return rows


def rows_to_csv(rows: list[dict]) -> bytes:
    """CSV für Excel in deutscher Sprache: Semikolon, Dezimalkomma (ein Dezimalpunkt würde dort als Text oder Datum gelesen), UTF-8 mit Kennung. Zahlen unverändert genau, leere Zellen für None, Semikolon in Text durch Komma ersetzt."""
    if not rows:
        return "".encode("utf-8-sig")

    def cell(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return ""
        if isinstance(v, float):
            return repr(v).replace(".", ",")
        text = str(v).replace(";", ",").replace("\n", " ")
        return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text          # Excel liest solche Zellen sonst als Formel (CSV-Injection)
    header = list(rows[0])
    lines = [";".join(h.replace(";", ",") for h in header)] + [";".join(cell(r.get(h)) for h in header) for r in rows]
    return ("\n".join(lines) + "\n").encode("utf-8-sig")
