"""Tabellarische Auswertungen: reine Funktionen, die aus einer `Analysis` Zeilen (Listen von Wörterbüchern) bauen.

Die Zeilen tragen Zahlen als Zahlen (kein Text); Formatierung übernimmt die Anzeige. `rows_to_csv` schreibt die Datei für Excel mit Dezimalkomma, `rows_to_wiki` und
`rows_to_html` bereiten dieselben Zeilen zum Einfügen in Jira und Confluence auf."""

import html

import numpy as np

import jira_constants as C
import jira_core as A
from jira_evaluation import Analysis, de, pct, status_list

METRIC_WEIGHT, METRIC_COUNT, METRIC_CREDITED = "Gewicht", "Tickets", "Angerechnet"
METRICS = (METRIC_WEIGHT, METRIC_COUNT, METRIC_CREDITED)
SUM_LABEL = "Summe"
MAX_LIST_ROWS = 200      # so viele Tickets nennt die Liste „ohne Story Points“ höchstens


def atom_statuses(issues, a: Analysis) -> list[str]:
    """Statusnamen der Atome in der Reihenfolge ihrer Gutschrift und ihres Namens (nur Status, die bei Atomen vorkommen)."""
    used = {issues[i].status for i in a.atoms}
    return [s for s in status_list(issues) if s in used]


def group_table(a: Analysis, dimension: str, unit: str) -> list[dict]:
    """Je Gruppe der gewählten Ebene: Gewicht, Fortschritt, nur Done nach Gewicht, Tickets und Tickets ohne Story Points."""
    s = a.stats
    return [{dimension: label, f"Gewicht ({unit})": float(w), "Fortschritt": None if p != p else float(p), "Nur Done (Gewicht)": None if d != d else float(d),
             "Tickets": float(n), "ohne Story Points": float(u)}
            for label, w, p, d, n, u in zip(s.labels, s.weight, s.progress, s.progress_done, s.count, s.unestimated)]


def status_by_group(issues, a: Analysis, metric: str) -> list[dict]:
    """Gruppen der gewählten Ebene als Zeilen, Status als Spalten; Zelle = Gewicht, Ticketzahl oder angerechnetes Gewicht (anteilig bei Mehrfachwerten).
    Dazu je Zeile die Summe und der Fortschritt der Gruppe, am Ende eine Summenzeile."""
    if metric not in METRICS:
        raise ValueError(f"unbekannte Kennzahl {metric!r}")
    statuses = atom_statuses(issues, a)
    pos = {s: k for k, s in enumerate(statuses)}
    status_of = np.array([pos[issues[i].status] for i in a.atoms], dtype=int)
    base = {METRIC_WEIGHT: a.w, METRIC_COUNT: np.ones(len(a.w)), METRIC_CREDITED: a.w * a.c}[metric]
    n_groups, n_status = len(a.assign.labels), len(statuses)
    cells = np.bincount(a.assign.group * n_status + status_of[a.assign.atom], weights=base[a.assign.atom] * a.assign.share,
                        minlength=n_groups * n_status).reshape(n_groups, n_status)
    rows = []
    for g, label in enumerate(a.assign.labels):
        row = {"Gruppe": label, **{s: float(cells[g, k]) for k, s in enumerate(statuses)}, SUM_LABEL: float(cells[g].sum())}
        row["Fortschritt"] = None if np.isnan(a.stats.progress[g]) else float(a.stats.progress[g])
        rows.append(row)
    if rows:
        total = {"Gruppe": SUM_LABEL, **{s: float(cells[:, k].sum()) for k, s in enumerate(statuses)}, SUM_LABEL: float(cells.sum())}
        total["Fortschritt"] = None if np.isnan(a.progress) else float(a.progress)
        rows.append(total)
    return rows


PARENT_COL, EPIC_COL, TOTAL_COL, EPIC_CHECK_COL = "Parent Ticket", "Epic-level Story Points", "Total", "Epic vs. Total"
REJECTED_COL, TOTAL_NET_COL, PROGRESS_COL = "Rejected", "Total (ohne Rejected)", "Fortschritt (gewichtet)"


def parent_status_matrix(issues, a: Analysis) -> tuple[list[dict], list[str], str]:
    """Matrix je übergeordnetem Ticket: Zeilen = Parent, Spalten = die Status des Teilbaums (nach Gewicht geordnet, das Gewicht im Kopf), Zelle = Gewicht (Story Points).
    Dazu die eigenen Story Points des Parents („Epic-level“) neben dem Total der Tickets darunter mit Markierung bei Abweichung, die zurückgewiesenen Tickets (auch die unter einem
    zurückgewiesenen Parent) in einer eigenen Spalte, das Total ohne sie, den Anteil der Status ab 90 % („Completed“) und den nach Status und Gewicht gewichteten Fortschritt. Die Matrix
    folgt Teilprojekt und Status-Gewichten der Auswertung. Rückgabe: Zeilen, die Statusspalten und der Name der Completed-Spalte."""
    keep, rej = list(a.atoms), list(a.rejected_atoms)
    w_rej = A.atom_weights(issues, rej, fill=A.unestimated_fill(issues, keep))
    statuses = sorted({issues[i].status for i in keep}, key=lambda st: (a.credits[st], A.new_rank(st), st.lower()))
    heads = {st: st + (f" ({de(a.credits[st])})" if a.credits[st] > 0 else "") for st in statuses}
    done_statuses = [st for st in statuses if a.credits[st] >= C.COMPLETED_MIN_CREDIT - 1e-9]
    completed_col = f"Completed ({'+'.join(done_statuses)})/(Total−Rejected)" if done_statuses else "Completed (kein Status ab 90 %)"
    by_key = {t.key: t for t in issues}

    def label(i):
        parent = by_key.get(issues[i].parent)
        return "(ohne Parent)" if parent is None else (f"{parent.key}: {parent.summary}" if parent.summary else parent.key)

    cells: dict[str, dict] = {}

    def entry(i):
        return cells.setdefault(label(i), {"by_status": {}, "rejected": 0.0, "credited": 0.0, "parent": by_key.get(issues[i].parent)})
    for pos, i in enumerate(keep):
        row = entry(i)
        row["by_status"][issues[i].status] = row["by_status"].get(issues[i].status, 0.0) + float(a.w[pos])
        row["credited"] += float(a.w[pos] * a.c[pos])
    for pos, i in enumerate(rej):
        entry(i)["rejected"] += float(w_rej[pos])

    def build(name, row, epic_points, check):
        net = sum(row["by_status"].values())
        done = sum(row["by_status"].get(st, 0.0) for st in done_statuses)
        out = {PARENT_COL: name, EPIC_COL: epic_points, TOTAL_COL: net + row["rejected"], EPIC_CHECK_COL: check}
        out.update({heads[st]: row["by_status"].get(st, 0.0) for st in statuses})
        out.update({REJECTED_COL: row["rejected"], TOTAL_NET_COL: net,
                    completed_col: (done / net if net > 0 and done_statuses else None), PROGRESS_COL: (row["credited"] / net if net > 0 else None)})
        return out

    rows = []
    for name in sorted(cells, key=A.natural_key):
        row = cells[name]
        parent = row["parent"]
        epic_points = parent.points if parent is not None else None
        total = sum(row["by_status"].values()) + row["rejected"]
        if epic_points is None:
            check = ""
        elif abs(total - epic_points) <= 1e-9:
            check = "gleich"
        else:
            check = f"⚠ weicht ab ({de(total - epic_points, sign=True)})"
        rows.append(build(name, row, epic_points, check))
    if rows:
        merged = {"by_status": {st: sum(c["by_status"].get(st, 0.0) for c in cells.values()) for st in statuses}, "rejected": sum(c["rejected"] for c in cells.values()),
                  "credited": sum(c["credited"] for c in cells.values())}
        own = [r[EPIC_COL] for r in rows if r[EPIC_COL] is not None]
        rows.append(build(SUM_LABEL, merged, sum(own) if own else None, ""))
    return rows, [heads[st] for st in statuses], completed_col


def data_quality(issues, a: Analysis) -> list[dict]:
    """Prüfungen der Eingangsdaten mit Anzahl, Anteil an den Atomen und dem Hinweis, wie sich der Befund auf die Zahl auswirkt."""
    atoms = list(a.atoms)
    n = len(atoms)
    by_key = {t.key: t for t in issues}
    epics = A.epic_of(issues)
    no_epic_names: dict[str, str] = {}
    checks = {
        "Ohne Story Points": sum(issues[i].points is None for i in atoms),
        "Story Points = 0": sum(issues[i].points == 0 for i in atoms),
        "Ohne Epic": sum(epics[i] == "" for i in atoms),
        "Ohne Sprint": sum(A.group_labels(by_key, issues[i], epics[i], no_epic_names, C.DIM_SPRINT) == ["(ohne Sprint)"] for i in atoms),
        "Status ohne erkannte Bedeutung (zählt 0)": sum(A.status_class(issues[i].status) == "other" for i in atoms),
    }
    hints = {
        "Ohne Story Points": "Wiegen den Median der geschätzten Tickets.",
        "Story Points = 0": "Zählen als geschätzt mit Gewicht 0: Das Ticket hat keinen Einfluss auf den Fortschritt.",
        "Ohne Epic": "Landen in der Gruppe „(ohne Epic)“ der Ebene Epic.",
        "Ohne Sprint": "Landen in der Gruppe „(ohne Sprint)“ der Ebene Sprint.",
        "Status ohne erkannte Bedeutung (zählt 0)": "Der Name klingt weder nach fertig noch nach Test, Merged oder Review (z. B. In Arbeit, To Do). Passt das nicht, die Gewichte der Status ändern.",
    }
    return [{"Prüfung": name, "Anzahl": count, "Anteil an den Tickets": count / n if n else None, "Wirkung": hints[name]} for name, count in checks.items()]


def unestimated_tickets(issues, a: Analysis, limit: int = MAX_LIST_ROWS) -> tuple[list[dict], int]:
    """Atome ohne Story Points als Liste (Schlüssel, Titel, Typ, Status, Epic), höchstens `limit`; dazu die Gesamtzahl."""
    epics = A.epic_of(issues)
    found = [i for i in a.atoms if issues[i].points is None]
    rows = [{"Schlüssel": issues[i].key, "Titel": issues[i].summary, "Typ": issues[i].type, "Status": issues[i].status, "Epic": epics[i]} for i in found[:limit]]
    return rows, len(found)


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
