"""Einlesen des CSV-Exports aus Jira Plans (deutsche oder englische Oberfläche, Semikolon oder Komma). Das Ergebnis ist eine Liste von `Issue`.

Fehlendes wird nicht erraten, sondern im `ImportReport` gemeldet. Gelesen werden Vorgangsschlüssel, Status, Titel, Hierarchie (als Ticket-Typ), Übergeordnetes Element,
Story Points, Sprint, Releases, Team, Bereich, Zugewiesene Person, Priorität, Stichwörter und Komponenten. Spalten mit „(hochrechnen)“ sind Summen über die
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
    ("sprint", "Sprint"), ("components", "Komponente"), ("labels", "Label"), ("assignee", "Bearbeiter"), ("versions", "Release"), ("team", "Team"), ("area", "Bereich"),
    ("priority", "Priorität"))
NOT_FOUND = "nicht gefunden"

_ALIASES = {
    "key": ("vorgangsschlüssel", "issue key", "key", "schlüssel"),
    "summary": ("titel", "summary", "zusammenfassung"),
    "type": ("hierarchie", "issue type", "vorgangstyp", "type", "typ"),
    "status": ("vorgangsstatus", "status"),
    "points": ("story points", "story point", "storypoints", "story point estimate", "storypunkte", "story-punkte", "story-points", "custom field (story points)"),
    "parent": ("übergeordnetes element", "parent", "parent key", "übergeordneter vorgang"),
    "sprint": ("sprint",),
    "components": ("komponenten", "component/s", "components"),
    "labels": ("stichwörter", "stichwoerter", "labels", "etiketten"),
    "assignee": ("zugewiesene person", "assignee", "bearbeiter"),
    "versions": ("releases", "fix versions", "fix version/s", "lösungsversion/en"),
    "team": ("team",),
    "area": ("bereich", "area"),
    "priority": ("priorität", "priority", "prioritaet"),
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
    """Spaltenindizes je Feld; mehrfach vorkommende Spalten (Sprint, Stichwörter, Komponenten) liefern alle Indizes."""
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
        "sprint": sum(bool(i.sprints) for i in issues), "components": sum(bool(i.components) for i in issues), "labels": sum(bool(i.labels) for i in issues),
        "assignee": sum(bool(i.assignee) for i in issues), "versions": sum(bool(i.versions) for i in issues), "team": sum(bool(i.team) for i in issues),
        "area": sum(bool(i.area) for i in issues), "priority": sum(bool(i.priority) for i in issues)}


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

    def cell(row, name, first_only=True):
        vals = [row[i].strip() for i in cols.get(name, []) if i < len(row) and row[i].strip()]
        return (vals[0] if vals else "") if first_only else vals

    issues, bad_points = [], 0
    for row in body:
        key = cell(row, "key")
        if not key:
            continue
        type_name = cell(row, "type") or "Story"
        raw_points = cell(row, "points")
        points = parse_number(raw_points)
        bad_points += bool(raw_points) and points is None
        issues.append(Issue(
            key=key, summary=cell(row, "summary"), type=type_name, is_subtask=_norm(type_name) in _SUBTASK_NAMES, status=cell(row, "status"), points=points,
            parent=cell(row, "parent"), sprints=tuple(p for v in cell(row, "sprint", False) for p in _split_list(v)), labels=tuple(p for v in cell(row, "labels", False) for p in _split_list(v)),
            components=tuple(p for v in cell(row, "components", False) for p in _split_list(v)), assignee=cell(row, "assignee"),
            versions=tuple(p for v in cell(row, "versions", False) for p in _split_list(v)), team=cell(row, "team"), area=cell(row, "area"), priority=cell(row, "priority")))
    with_parent = sum(bool(i.parent) for i in issues)
    issues = _resolve_parents(issues)
    lost_parents = with_parent - sum(bool(i.parent) for i in issues)
    report = ImportReport(issues=len(issues))
    report.columns = coverage_rows(issues, {name: ", ".join(dict.fromkeys(header[i].strip() for i in idx)) for name, idx in cols.items()})
    if "points" not in cols:
        days = [h.strip() for h in header if _norm(h) in DAY_ESTIMATE_HEADERS]
        unread = f" Die Schätzung in Tagen („{', '.join(days)}“) wird nicht gelesen." if days else ""
        report.notes.append(f"Keine Story-Points-Spalte gefunden.{unread} Alle Tickets gelten als ungeschätzt und wiegen gleich viel.")
    if "parent" not in cols:
        report.notes.append("Keine Spalte „Übergeordnetes Element“: Epics und Hierarchie lassen sich nicht zuordnen.")
    if "sprint" not in cols:
        report.notes.append("Keine Sprint-Spalte gefunden.")
    if lost_parents:
        report.notes.append(f"{lost_parents} Verweise auf übergeordnete Tickets konnten keinem Ticket der Datei zugeordnet werden (Eltern außerhalb der Datei, oder ein Titel statt eines Schlüssels, der nicht eindeutig ist).")
    if bad_points:
        report.notes.append(f"Nicht lesbare Story Points (keine Zahl): {bad_points}. Diese Tickets gelten als ungeschätzt.")
    return tuple(issues), report


def drop_titles(issues, keep_epics: bool = True) -> tuple[Issue, ...]:
    """Verwirft die Titel der Tickets (außer den der Epics, wenn `keep_epics`: sie benennen die Gruppen und stehen oft schon im Projektplan). Der Titel wird für keine
    Rechnung gebraucht; Titel enthalten erfahrungsgemäß am ehesten Namen von Kunden und Personen."""
    return tuple(i if (keep_epics and i.is_epic) else replace(i, summary="") for i in issues)


def pseudonymize_assignees(issues) -> tuple[Issue, ...]:
    """Ersetzt die Namen der Bearbeiter durch „Person 1“, „Person 2“ ... (nach Namen sortiert, also unabhängig von der Ticketreihenfolge). Ein leerer Name bleibt leer.
    Das betrifft nur die Anzeige und die Tabellen der App; die hochgeladene Datei hat den Server da schon erreicht."""
    names = sorted({i.assignee for i in issues if i.assignee})
    number = {name: f"Person {k}" for k, name in enumerate(names, start=1)}
    return tuple(replace(i, assignee=number.get(i.assignee, "")) for i in issues)
