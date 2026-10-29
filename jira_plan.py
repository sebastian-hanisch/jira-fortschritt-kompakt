"""Einlesen des CSV-Exports aus Jira Plans (deutsche oder englische Oberfläche, Semikolon oder Komma). Das Ergebnis ist eine Liste von `Issue`.

Fehlendes wird nicht erraten, sondern im `ImportReport` gemeldet. Gelesen werden Vorgangsschlüssel, Status, Titel, Hierarchie (als Ticket-Typ), Übergeordnetes Element,
Story Points, Sprint und Team. Alle anderen Spalten (besonders Personen, Releases, Bereiche, Prioritäten, Stichwörter und Komponenten) werden nicht gelesen. Dazu Jiras eigene Fortschrittsspalten („Fortschritt (%)“, „Fortschritt
abgeschlossen (SP)“, „Verbleibender Fortschritt (SP)“), die nur der Gegenprobe dienen und in keine Rechnung eingehen. Spalten mit „(hochrechnen)“ sind Summen über die
Kinder und werden übergangen, ebenso alle weiteren Spalten des Exports."""

import csv
import io
import re
from dataclasses import dataclass, field, replace

import jira_constants as C
from jira_core import Issue


class PlanImportError(Exception):
    """Eingabe unbrauchbar (kein Schlüssel, kein Status, leere Datei); der Text ist für die Anzeige gedacht."""


@dataclass
class ImportReport:
    """Was beim Einlesen auffiel; die App zeigt es an, bevor eine Zahl gezeigt wird."""

    issues: int = 0
    notes: list[str] = field(default_factory=list)
    columns: list[dict] = field(default_factory=list)      # Erkennungsbericht: je Feld, wo es gefunden wurde und bei wie vielen Tickets ein Wert steht


FIELD_LABELS = (
    ("key", "Ticket-Schlüssel"), ("summary", "Titel"), ("type", "Ticket-Typ"), ("status", "Status"), ("points", "Story Points"), ("parent", "Übergeordnetes Ticket"),
    ("sprint", "Sprint"), ("team", "Team"), ("jira_progress", "Jira: Fortschritt (%)"), ("jira_done", "Jira: Fortschritt abgeschlossen (SP)"), ("jira_left", "Jira: Verbleibender Fortschritt (SP)"))
NOT_FOUND = "nicht gefunden"

_ALIASES = {
    "key": ("vorgangsschlüssel", "issue key", "key", "schlüssel"),
    "summary": ("titel", "summary", "zusammenfassung"),
    "type": ("hierarchie", "issue type", "vorgangstyp", "type", "typ"),
    "status": ("vorgangsstatus", "status"),
    "points": ("story points", "story point", "storypoints", "story point estimate", "storypunkte", "story-punkte", "story-points", "custom field (story points)"),
    "parent": ("übergeordnetes element", "parent", "parent key", "übergeordneter vorgang"),
    "sprint": ("sprint",),
    "team": ("team",),
    "jira_progress": ("fortschritt (%)",),
    "jira_done": ("fortschritt abgeschlossen (sp)",),
    "jira_left": ("verbleibender fortschritt (sp)",),
}
DAY_ESTIMATE_HEADERS = ("schätzung (t)", "schätzung (tage)", "schaetzung (t)")      # die Schätzung in Tagen des Plan-Exports: wird nicht gelesen, nur gemeldet
_SUBTASK_NAMES = {"sub-task", "subtask", "sub task", "teilaufgabe", "unteraufgabe", "untervorgang"}


def parse_number(text) -> float | None:
    """Story Points aus Text oder Zahl; Komma oder Punkt als Dezimaltrenner, leer oder unlesbar = None."""
    if text is None or isinstance(text, bool):
        return None
    if isinstance(text, (int, float)):
        return float(text)
    t = str(text).strip().replace(",", ".")
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def parse_percent(text) -> float | None:
    """Prozentwert aus Text („35“, „35,5“, „35 %“) als Anteil 0..1; leer oder unlesbar = None."""
    value = parse_number(str(text).replace("%", "")) if text is not None else None
    return None if value is None else value / 100


def _split_list(text: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in re.split(r"[,;]", text) if p.strip()) if text else ()


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _columns(header: list[str]) -> dict[str, list[int]]:
    """Spaltenindizes je Feld; mehrfach vorkommende Spalten (Sprint) liefern alle Indizes."""
    normed = [_norm(h) for h in header]
    found: dict[str, list[int]] = {}
    for fieldname, names in _ALIASES.items():
        idx = [n for n, h in enumerate(normed) if h in names]
        if idx:
            found[fieldname] = idx
    return found


def field_counts(issues) -> dict[str, int]:
    """Bei wie vielen Tickets steht je Feld ein Wert (Story Points: eine Zahl, Eltern: ein Ticket, das im Bestand steht)."""
    return {
        "key": sum(bool(i.key) for i in issues), "summary": sum(bool(i.summary) for i in issues), "type": sum(bool(i.type) for i in issues),
        "status": sum(bool(i.status) for i in issues), "points": sum(i.points is not None for i in issues), "parent": sum(bool(i.parent) for i in issues),
        "sprint": sum(bool(i.sprints) for i in issues), "team": sum(bool(i.team) for i in issues), "jira_progress": sum(i.jira_progress is not None for i in issues),
        "jira_done": sum(i.jira_done is not None for i in issues), "jira_left": sum(i.jira_left is not None for i in issues)}


def coverage_rows(issues, found_in: dict[str, str]) -> list[dict]:
    """Erkennungsbericht als Zeilen: Feld, Fundstelle (Spaltenkopf) und Zahl der Tickets mit Wert. Ein Feld ohne Fundstelle steht als „nicht gefunden“."""
    counts = field_counts(issues)
    return [{"Feld": label, "Gefunden in": found_in.get(name, NOT_FOUND), "Tickets mit Wert": counts[name] if name in found_in else 0, "von": len(issues)}
            for name, label in FIELD_LABELS]


_KEY_AT_START = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_]*-\d+)\b")


def _resolve_parents(issues: list[Issue]) -> list[Issue]:
    """Elternverweis als Schlüssel auflösen: ein Wert, der ein Ticketschlüssel der Datei ist, bleibt; sonst zählen in dieser Reihenfolge ein Schlüssel am Anfang des Werts
    („ABC-12 Titel“) und ein eindeutiger Titel. Alles andere (Eltern außerhalb der Datei, mehrdeutiger Titel) wird gelöscht, damit nichts ins Leere zeigt."""
    keys = {i.key for i in issues}
    by_title: dict[str, list[str]] = {}
    for i in issues:
        if i.summary.strip():
            by_title.setdefault(i.summary.strip().lower(), []).append(i.key)
    out = []
    for issue in issues:
        p = issue.parent
        if p and p not in keys:
            m = _KEY_AT_START.match(p)
            found = m.group(1) if m and m.group(1) in keys else ""
            if not found:
                titled = by_title.get(p.strip().lower(), [])
                found = titled[0] if len(titled) == 1 else ""
            p = found
        out.append(issue if p == issue.parent else replace(issue, parent=p))
    return out


def _cell(row: list[str], cols: dict[str, list[int]], name: str) -> str:
    """Erster nicht leere Wert der Spalte(n) `name` in der Zeile, sonst leer."""
    return next((row[i].strip() for i in cols.get(name, []) if i < len(row) and row[i].strip()), "")


def _cells(row: list[str], cols: dict[str, list[int]], name: str) -> list[str]:
    """Alle nicht leeren Werte der Spalten `name` (der Sprint kommt mehrfach vor)."""
    return [row[i].strip() for i in cols.get(name, []) if i < len(row) and row[i].strip()]


def _listed(row: list[str], cols: dict[str, list[int]], name: str) -> tuple[str, ...]:
    return tuple(part for value in _cells(row, cols, name) for part in _split_list(value))


def _issue_from_row(row: list[str], cols: dict[str, list[int]]) -> tuple[Issue, bool]:
    """Ein Ticket aus einer Zeile des Exports; der zweite Wert sagt, ob die Story Points einen Text enthielten, der keine Zahl ist."""
    type_name = _cell(row, cols, "type") or "Story"
    raw_points = _cell(row, cols, "points")
    points = parse_number(raw_points)
    issue = Issue(
        key=_cell(row, cols, "key"), summary=_cell(row, cols, "summary"), type=type_name, is_subtask=_norm(type_name) in _SUBTASK_NAMES, status=_cell(row, cols, "status"), points=points,
        parent=_cell(row, cols, "parent"), sprints=_listed(row, cols, "sprint"), team=_cell(row, cols, "team"),
        jira_progress=parse_percent(_cell(row, cols, "jira_progress")), jira_done=parse_number(_cell(row, cols, "jira_done")), jira_left=parse_number(_cell(row, cols, "jira_left")))
    return issue, bool(raw_points) and points is None


def _report_notes(cols: dict[str, list[int]], header: list[str], lost_parents: int, bad_points: int) -> list[str]:
    """Was dem Nutzer vor der ersten Zahl gesagt werden muss: fehlende Spalten, verlorene Eltern, unlesbare Story Points."""
    notes = []
    if "points" not in cols:
        days = [h.strip() for h in header if _norm(h) in DAY_ESTIMATE_HEADERS]
        unread = f" Die Schätzung in Tagen („{', '.join(days)}“) wird nicht gelesen." if days else ""
        notes.append(f"Keine Story-Points-Spalte gefunden.{unread} Alle Tickets gelten als ungeschätzt und wiegen gleich viel.")
    if "parent" not in cols:
        notes.append("Keine Spalte „Übergeordnetes Element“: Epics und Hierarchie lassen sich nicht zuordnen.")
    if "sprint" not in cols:
        notes.append("Keine Sprint-Spalte gefunden.")
    if lost_parents:
        notes.append(f"{lost_parents} Verweise auf übergeordnete Tickets konnten keinem Ticket der Datei zugeordnet werden (Eltern außerhalb der Datei, oder ein Titel statt eines Schlüssels, der nicht eindeutig ist).")
    if bad_points:
        notes.append(f"Nicht lesbare Story Points (keine Zahl): {bad_points}. Diese Tickets gelten als ungeschätzt.")
    return notes


def read_plan(data: bytes, max_issues: int = C.MAX_IMPORT_ISSUES) -> tuple[tuple[Issue, ...], ImportReport]:
    """Liest den CSV-Export aus Jira Plans (Trennzeichen Semikolon oder Komma). Pflicht sind Schlüssel und Status; alles andere ist optional."""
    text = _decode(data)
    sample = text[:4096]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    if not rows:
        raise PlanImportError("Die Datei ist leer.")
    header = rows[0]
    cols = _columns(header)
    for needed, label in (("key", "Vorgangsschlüssel"), ("status", "Vorgangsstatus")):
        if needed not in cols:
            raise PlanImportError(f"Die Spalte „{label}“ fehlt. Gefunden: {', '.join(h for h in header if h) or '(keine Kopfzeile)'}. Erwartet wird der CSV-Export aus Jira Plans.")
    body = [r for r in rows[1:] if any(c.strip() for c in r)]
    if len(body) > max_issues:
        raise PlanImportError(f"{len(body)} Tickets sind mehr als die Obergrenze von {max_issues}. Bitte den Plan einschränken (Filter in Jira Plans) und neu exportieren.")

    issues, bad_points = [], 0
    for row in body:
        if not _cell(row, cols, "key"):
            continue
        issue, unreadable = _issue_from_row(row, cols)
        issues.append(issue)
        bad_points += unreadable
    with_parent = sum(bool(i.parent) for i in issues)
    issues = _resolve_parents(issues)
    lost_parents = with_parent - sum(bool(i.parent) for i in issues)
    report = ImportReport(issues=len(issues))
    report.columns = coverage_rows(issues, {name: ", ".join(dict.fromkeys(header[i].strip() for i in idx)) for name, idx in cols.items()})
    report.notes = _report_notes(cols, header, lost_parents, bad_points)
    return tuple(issues), report
