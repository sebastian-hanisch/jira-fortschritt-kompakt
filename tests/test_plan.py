"""Export aus Jira Plans (deutsche Oberfläche): Spalten des echten Exports, Hierarchie, Eltern, Schätzung in Tagen, Fehlermeldungen.

Die Kopfzeile unten ist die Spaltenliste, die ein echter Export meldete."""

import pytest

import jira_plan as J
from conftest import make_mini, plan_csv, random_project
from jira_core import Issue

REAL_HEADER = [
    "Hierarchie", "Titel", "Bereich", "Releases (hochrechnen)", "Releases", "Team (hochrechnen)", "Team", "Zugewiesene Person", "Autor", "Erstellt", "Aktualisiert",
    "Sprint (hochrechnen)", "Sprint", "Zielstartdatum (hochrechnen)", "Zielstartdatum", "Zielenddatum (hochrechnen)", "Zielenddatum", "Fälligkeitsdatum",
    "Schätzung (T) (hochrechnen)", "Schätzung (T)", "Story Points (hochrechnen)", "Story Points", "Übergeordnetes Element", "Priorität", "Stichwörter", "Komponenten", "Vorgangsschlüssel", "Vorgangsstatus", "Ziel",
    "Zielstatus", "Idee", "Fortschritt (%)", "Fortschritt abgeschlossen (T)", "Verbleibender Fortschritt (T)", "Fortschritt (%) Anzahl Vorgänge (AV)", "AV zu erledigen",
    "In Arbeit AV", "Erledigt AV", "AV insgesamt", "Startdatum", "Beteiligte Gesellschaften/Bereiche"]


def _row(**values):
    cells = {name: "" for name in REAL_HEADER}
    cells.update(values)
    return ";".join(cells[name] for name in REAL_HEADER)


def _csv(*rows):
    return ("\n".join([";".join(REAL_HEADER), *rows]) + "\n").encode("utf-8")


EPIC = _row(**{"Hierarchie": "Epic", "Titel": "Suche", "Bereich": "Bereich Nord", "Releases (hochrechnen)": "Release 1.0", "Team (hochrechnen)": "Team Alpha",
               "Sprint (hochrechnen)": "Sprint 3", "Schätzung (T) (hochrechnen)": "42", "Story Points (hochrechnen)": "8,5", "Vorgangsschlüssel": "P-1", "Vorgangsstatus": "In Arbeit", "Fortschritt (%)": "35",
               "AV insgesamt": "2", "Erledigt AV": "1"})
STORY_A = _row(**{"Hierarchie": "Story", "Titel": "Filter bauen", "Bereich": "Bereich Nord", "Releases": "Release 1.0", "Team": "Team Alpha", "Zugewiesene Person": "Person A",
                  "Autor": "Person B", "Erstellt": "01.09.2026", "Sprint": "Sprint 2, Sprint 3", "Schätzung (T)": "99", "Story Points": "5", "Übergeordnetes Element": "P-1", "Priorität": "Hoch",
                  "Stichwörter": "ux, quick-win", "Komponenten": "Frontend", "Vorgangsschlüssel": "P-2", "Vorgangsstatus": "In Test"})
STORY_B = _row(**{"Hierarchie": "Story", "Titel": "Index anlegen", "Bereich": "Bereich Nord", "Team": "Team Beta", "Erstellt": "02.09.2026", "Story Points": "3,5",
                  "Übergeordnetes Element": "P-1", "Priorität": "Mittel", "Vorgangsschlüssel": "P-3", "Vorgangsstatus": "Ready4Prod"})


def test_the_real_header_is_read_and_the_status_column_is_found():
    issues, report = J.read_plan(_csv(EPIC, STORY_A, STORY_B))
    assert [i.key for i in issues] == ["P-1", "P-2", "P-3"] and report.issues == 3
    assert [i.status for i in issues] == ["In Arbeit", "In Test", "Ready4Prod"]
    rows = {r["Feld"]: r["Gefunden in"] for r in report.columns}
    assert rows["Status"] == "Vorgangsstatus" and rows["Ticket-Schlüssel"] == "Vorgangsschlüssel" and rows["Titel"] == "Titel" and rows["Ticket-Typ"] == "Hierarchie"
    assert rows["Übergeordnetes Ticket"] == "Übergeordnetes Element" and rows["Story Points"] == "Story Points" and rows["Sprint"] == "Sprint" and rows["Team"] == "Team"
    assert rows["Bereich"] == "Bereich" and rows["Priorität"] == "Priorität" and rows["Label"] == "Stichwörter" and rows["Komponente"] == "Komponenten"
    assert rows["Release"] == "Releases" and rows["Bearbeiter"] == "Zugewiesene Person"
    counts = {r["Feld"]: r["Tickets mit Wert"] for r in report.columns}
    assert counts["Story Points"] == 2 and counts["Übergeordnetes Ticket"] == 2 and counts["Sprint"] == 1 and counts["Ticket-Schlüssel"] == 3


def test_rollup_columns_are_ignored_and_the_values_of_the_ticket_itself_are_read():
    epic, story_a, story_b = J.read_plan(_csv(EPIC, STORY_A, STORY_B))[0]
    assert epic.points is None and epic.versions == () and epic.sprints == () and epic.team == ""        # die „(hochrechnen)“-Werte der Zeile zählen nicht
    assert epic.area == "Bereich Nord" and epic.type == "Epic" and epic.is_epic
    assert story_a.points == 5.0 and story_b.points == 3.5                                                  # Dezimalkomma
    assert story_a.sprints == ("Sprint 2", "Sprint 3") and story_a.labels == ("ux", "quick-win") and story_a.components == ("Frontend",)
    assert (story_a.team, story_a.area, story_a.priority, story_a.assignee) == ("Team Alpha", "Bereich Nord", "Hoch", "Person A") and story_a.parent == "P-1"


def test_all_columns_of_the_real_export_are_known_or_deliberately_skipped():
    used = {REAL_HEADER[i] for idx in J._columns(REAL_HEADER).values() for i in idx}
    assert used == {"Hierarchie", "Titel", "Bereich", "Releases", "Team", "Zugewiesene Person", "Sprint", "Story Points", "Übergeordnetes Element", "Priorität", "Stichwörter",
                    "Komponenten", "Vorgangsschlüssel", "Vorgangsstatus"}


def test_the_day_estimate_is_never_read_and_a_file_with_only_days_says_so():
    issues, report = J.read_plan("Vorgangsschlüssel;Vorgangsstatus;Schätzung (T)\nA-1;Done;5\nA-2;Done;4\n".encode("utf-8"))
    assert [i.points for i in issues] == [None, None] and any("Keine Story-Points-Spalte" in n and "Schätzung (T)" in n and "nicht gelesen" in n for n in report.notes)
    both, both_report = J.read_plan("Vorgangsschlüssel;Vorgangsstatus;Schätzung (T);Story Points\nA-1;Done;5;3\nA-2;Done;4;\n".encode("utf-8"))
    assert [i.points for i in both] == [3.0, None] and not any("Story-Points-Spalte" in n for n in both_report.notes)            # die Tage bleiben unbenutzt, ohne Rückfall je Ticket


def test_english_header_with_commas_is_read_too():
    raw = b"Issue key,Issue Type,Status,Parent,Sprint,Sprint,Story Points\nE-1,Epic,In Progress,,,,\nS-1,Story,Done,E-1,Sprint 1,Sprint 2,3\n"
    epic, story = J.read_plan(raw)[0]
    assert epic.is_epic and story.parent == "E-1" and story.sprints == ("Sprint 1", "Sprint 2") and story.points == 3.0


def test_cp1252_encoded_files_are_decoded():
    raw = "Vorgangsschlüssel;Vorgangsstatus;Titel\nA-1;Zurückgewiesen;Größe\n".encode("cp1252")
    issue = J.read_plan(raw)[0][0]
    assert issue.status == "Zurückgewiesen" and issue.summary == "Größe"


# ---------------------------------------------------------------- Fehler und Hinweise

def test_unusable_files_raise_a_readable_error():
    with pytest.raises(J.PlanImportError, match="leer"):
        J.read_plan(b"")
    with pytest.raises(J.PlanImportError, match="Vorgangsschlüssel"):
        J.read_plan(b"Spalte A;Spalte B\n1;2\n")
    with pytest.raises(J.PlanImportError, match="Vorgangsstatus"):
        J.read_plan("Vorgangsschlüssel;Titel\nA-1;x\n".encode())
    with pytest.raises(J.PlanImportError, match="Obergrenze"):
        J.read_plan("Vorgangsschlüssel;Vorgangsstatus\nA-1;Done\nA-2;Done\nA-3;Done\n".encode(), max_issues=2)


def test_blank_rows_and_rows_without_a_key_are_skipped():
    issues = J.read_plan("Vorgangsschlüssel;Vorgangsstatus\nA-1;Done\n;;\n;To Do\nA-2;To Do\n".encode())[0]
    assert [i.key for i in issues] == ["A-1", "A-2"]


def test_a_file_without_estimate_parent_and_sprint_columns_warns_instead_of_guessing():
    notes = J.read_plan("Vorgangsschlüssel;Vorgangsstatus\nA-1;Done\n".encode())[1].notes
    assert any("Story-Points-Spalte" in n for n in notes) and any("Übergeordnetes Element" in n for n in notes) and any("Sprint-Spalte" in n for n in notes)


def test_unreadable_estimates_count_as_unestimated_and_are_reported():
    issues, report = J.read_plan("Vorgangsschlüssel;Vorgangsstatus;Story Points\nA-1;Done;5\nA-2;Done;viel\nA-3;Done;1,5\n".encode())
    assert [i.points for i in issues] == [5.0, None, 1.5] and any("Nicht lesbare Story Points (keine Zahl): 1" in n for n in report.notes)
    assert J.parse_number(None) is None and J.parse_number(True) is None and J.parse_number(2) == 2.0 and J.parse_number(" 3,5 ") == 3.5 and J.parse_number("") is None


# ---------------------------------------------------------------- Eltern

def _parents(*pairs):
    rows = [_row(**{"Hierarchie": "Epic", "Titel": "Mein Epic", "Vorgangsschlüssel": "E-1", "Vorgangsstatus": "In Arbeit"}),
            _row(**{"Hierarchie": "Epic", "Titel": "Doppelt", "Vorgangsschlüssel": "E-2", "Vorgangsstatus": "In Arbeit"}),
            _row(**{"Hierarchie": "Epic", "Titel": "Doppelt", "Vorgangsschlüssel": "E-3", "Vorgangsstatus": "In Arbeit"})]
    rows += [_row(**{"Hierarchie": "Story", "Vorgangsschlüssel": f"S-{n}", "Vorgangsstatus": "In Test", "Übergeordnetes Element": parent}) for n, parent in enumerate(pairs, start=1)]
    issues, report = J.read_plan(_csv(*rows))
    return [i.parent for i in issues if i.key.startswith("S-")], report


def test_parent_as_key_as_key_with_title_or_as_unique_title():
    parents, report = _parents("E-1", "E-1 Mein Epic", "E-1: Mein Epic", "Mein Epic", "mein epic ")
    assert parents == ["E-1"] * 5 and not any("übergeordnete" in n for n in report.notes)


def test_ambiguous_missing_and_foreign_parents_are_dropped_and_counted():
    parents, report = _parents("Doppelt", "X-9", "Unbekannt", "")
    assert parents == ["", "", "", ""]
    assert any("3 Verweise" in n for n in report.notes)            # der leere Verweis zählt nicht


# ---------------------------------------------------------------- Rundlauf

def test_sub_task_names_in_german_and_english_are_recognised():
    issues = J.read_plan("Vorgangsschlüssel;Vorgangsstatus;Hierarchie\nA;Done;Teilaufgabe\nB;Done;Sub-task\nC;Done;Story\nD;Done;\n".encode("utf-8"))[0]
    assert [i.is_subtask for i in issues] == [True, True, False, False] and issues[3].type == "Story"


def test_plan_csv_has_the_columns_of_the_real_export():
    header = plan_csv(make_mini()).decode("utf-8-sig").split("\n")[0].split(";")
    assert set(header) <= set(REAL_HEADER)


def test_roundtrip_of_the_mini_project_and_of_random_projects():
    mini = make_mini()
    assert J.read_plan(plan_csv(mini))[0] == mini
    for seed in range(8):
        project = random_project(seed)
        assert J.read_plan(plan_csv(project))[0] == project


def test_rollup_cells_of_the_epic_are_sums_of_its_children_by_hand():
    issues = (Issue(key="E", type="Epic", summary="E"), Issue(key="A", parent="E", points=2.0, team="T1", sprints=("S1",), versions=("R1",)),
              Issue(key="B", parent="E", points=1.5, team="T2", sprints=("S1", "S2"), versions=("R1",)), Issue(key="C", parent="E"))
    rows = plan_csv(issues).decode("utf-8-sig").split("\n")
    header = rows[0].split(";")
    epic = dict(zip(header, rows[1].split(";")))
    assert epic["Story Points (hochrechnen)"] == "3,5" and epic["Releases (hochrechnen)"] == "R1" and epic["Team (hochrechnen)"] == "T1, T2" and epic["Sprint (hochrechnen)"] == "S1, S2"
    story = dict(zip(header, rows[2].split(";")))
    assert story["Story Points (hochrechnen)"] == "" and story["Story Points"] == "2"


# ---------------------------------------------------------------- Datenschutz beim Laden

def test_drop_titles_keeps_the_titles_of_epics_and_higher_levels_only():
    issues = (Issue(key="I", type="Initiative", summary="Programm"), Issue(key="E", type="Epic", summary="Kundenprojekt Alpha", parent="I"),
              Issue(key="S", summary="Geheimer Kundenname", parent="E"), Issue(key="T", type="Thema", summary="Thema X"))
    assert [i.summary for i in J.drop_titles(issues)] == ["Programm", "Kundenprojekt Alpha", "", "Thema X"]
    assert [i.summary for i in J.drop_titles(issues, keep_epics=False)] == ["", "", "", ""]
    assert J.drop_titles(()) == ()


def test_pseudonymize_assignees_numbers_by_sorted_name_and_keeps_empty_names():
    issues = (Issue(key="A", assignee="Zoe"), Issue(key="B", assignee="Anna"), Issue(key="C"), Issue(key="D", assignee="Zoe"))
    assert [i.assignee for i in J.pseudonymize_assignees(issues)] == ["Person 2", "Person 1", "", "Person 2"]          # unabhängig von der Reihenfolge der Tickets
    assert [i.assignee for i in J.pseudonymize_assignees(tuple(reversed(issues)))] == ["Person 2", "", "Person 1", "Person 2"]
