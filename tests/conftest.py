"""Gemeinsame Fixtures: die Mini-Instanz, an der jede Einheit von Hand geprüft wird, ein Schreiber für den Plan-Export und ein Erzeuger zufälliger Projekte (nur für Tests).

Mini-Projekt (alle Zahlen von Hand gerechnet, siehe die Tests):

    E1 Epic A   |  S1 Story  3 T  Done         Sprint 1
                |  S2 Story  5 T  In Progress  Sprint 1, Sprint 2     Sub-Tasks T1 (Done), T2 (To Do), ohne Schätzung
    E2 Epic B   |  S3 Story  2 T  To Do        (kein Sprint)
                |  S4 Story  ? T  In Review    Sprint 2
    ohne Epic   |  B1 Bug    1 T  Done         Sprint 2
"""

import csv
import io
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jira_core import Issue  # noqa: E402


def make_mini() -> tuple[Issue, ...]:
    return (
        Issue(key="E1", summary="Epic A", type="Epic", status="In Progress"),
        Issue(key="E2", summary="Epic B", type="Epic", status="To Do"),
        Issue(key="S1", type="Story", status="Done", points=3.0, parent="E1", sprints=("Sprint 1",), components=("Backend", "Frontend")),
        Issue(key="S2", type="Story", status="In Progress", points=5.0, parent="E1", sprints=("Sprint 1", "Sprint 2"), components=("Backend",)),
        Issue(key="S3", type="Story", status="To Do", points=2.0, parent="E2"),
        Issue(key="S4", type="Story", status="In Review", points=None, parent="E2", sprints=("Sprint 2",), components=("Frontend",)),
        Issue(key="B1", type="Bug", status="Done", points=1.0, sprints=("Sprint 2",), components=("Backend",)),
        Issue(key="T1", type="Sub-task", is_subtask=True, status="Done", parent="S2"),
        Issue(key="T2", type="Sub-task", is_subtask=True, status="To Do", parent="S2"),
    )


PLAN_HEADER = ("Hierarchie", "Titel", "Bereich", "Releases (hochrechnen)", "Releases", "Team (hochrechnen)", "Team", "Zugewiesene Person", "Erstellt", "Sprint (hochrechnen)", "Sprint",
               "Schätzung (T) (hochrechnen)", "Schätzung (T)", "Übergeordnetes Element", "Priorität", "Stichwörter", "Komponenten", "Vorgangsschlüssel", "Vorgangsstatus")


def plan_csv(issues) -> bytes:
    """Tickets im Aufbau des Plan-Exports (deutsche Oberfläche, Semikolon, Schätzung in Tagen mit Dezimalkomma, Mehrfachwerte mit Komma getrennt). Die Spalten „… (hochrechnen)“
    tragen bei Epics die Summen bzw. Mengen ihrer Kinder."""
    children: dict[str, list[Issue]] = {}
    for i in issues:
        if i.parent:
            children.setdefault(i.parent, []).append(i)

    def number(x):
        return "" if x is None else f"{x:g}".replace(".", ",")

    def joined(values):
        return ", ".join(dict.fromkeys(v for v in values if v))
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=";", lineterminator="\n")
    writer.writerow(PLAN_HEADER)
    for i in issues:
        kids = children.get(i.key, []) if i.is_epic else []
        total = sum(k.points for k in kids if k.points is not None)
        writer.writerow([
            i.type, i.summary, i.area, joined(v for k in kids for v in k.versions), joined(i.versions), joined(k.team for k in kids), i.team, i.assignee, "",
            joined(s for k in kids for s in k.sprints), joined(i.sprints), number(total) if kids else "", number(i.points), i.parent, i.priority, joined(i.labels), joined(i.components),
            i.key, i.status])
    return buffer.getvalue().encode("utf-8-sig")


STATUSES = ("Backlog", "Specification", "In Arbeit", "In Review", "Merged", "Ready4Test", "Ready4Prod", "Rejected")


def random_project(seed: int, n_epics: int = 5) -> tuple[Issue, ...]:
    """Zufälliges Projekt mit Epics, Stories, Bugs und Sub-Tasks, ein Teil ungeschätzt, ein Teil zurückgewiesen. Nur für Tests der Rechenregeln (Summen, Grenzen)."""
    rng = random.Random(seed)
    issues, n = [], 0
    for e in range(n_epics):
        n += 1
        epic = f"P-{n}"
        issues.append(Issue(key=epic, summary=f"Epic {e}", type="Epic", status="In Arbeit", points=None, area=rng.choice(("Nord", "Süd"))))
        for _ in range(rng.randint(2, 8)):
            n += 1
            key = f"P-{n}"
            issues.append(Issue(
                key=key, summary=f"Story {key}", type=rng.choice(("Story", "Story", "Bug", "Task")), status=rng.choice(STATUSES), parent=epic,
                points=None if rng.random() < 0.2 else float(rng.choice((0.5, 1, 2, 3, 5, 8))), sprints=tuple(f"Sprint {s}" for s in sorted(rng.sample(range(1, 12), rng.randint(0, 2)))),
                components=tuple(rng.sample(("Frontend", "Backend", "Daten"), rng.randint(0, 2))), team=rng.choice(("Alpha", "Beta", "")), priority=rng.choice(("Hoch", "Mittel", ""))))
            if rng.random() < 0.3:
                n += 1
                issues.append(Issue(key=f"P-{n}", type="Sub-task", is_subtask=True, status=rng.choice(STATUSES), parent=key))
    return tuple(issues)


@pytest.fixture
def mini():
    return make_mini()
