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
    counts = {r["Feld"]: r["Tickets mit Wert"] for r in report.columns}
    assert counts["Story Points"] == 2 and counts["Übergeordnetes Ticket"] == 2 and counts["Sprint"] == 1 and counts["Ticket-Schlüssel"] == 3


def test_rollup_columns_are_ignored_and_the_values_of_the_ticket_itself_are_read():
    epic, story_a, story_b = J.read_plan(_csv(EPIC, STORY_A, STORY_B))[0]
    assert epic.points is None and epic.sprints == () and epic.team == ""        # die „(hochrechnen)“-Werte der Zeile zählen nicht
    assert epic.type == "Epic" and epic.is_epic
    assert story_a.points == 5.0 and story_b.points == 3.5                                                  # Dezimalkomma
    assert story_a.sprints == ("Sprint 2", "Sprint 3") and story_a.team == "Team Alpha" and story_a.parent == "P-1"


def test_all_columns_of_the_real_export_are_known_or_deliberately_skipped():
    used = {REAL_HEADER[i] for idx in J._columns(REAL_HEADER).values() for i in idx}
    assert used == {"Hierarchie", "Titel", "Team", "Sprint", "Story Points", "Übergeordnetes Element", "Vorgangsschlüssel", "Vorgangsstatus", "Fortschritt (%)"}


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
    issues = (Issue(key="E", type="Epic", summary="E"), Issue(key="A", parent="E", points=2.0, team="T1", sprints=("S1",)),
              Issue(key="B", parent="E", points=1.5, team="T2", sprints=("S1", "S2")), Issue(key="C", parent="E"))
    rows = plan_csv(issues).decode("utf-8-sig").split("\n")
    header = rows[0].split(";")
    epic = dict(zip(header, rows[1].split(";")))
    assert epic["Story Points (hochrechnen)"] == "3,5" and epic["Team (hochrechnen)"] == "T1, T2" and epic["Sprint (hochrechnen)"] == "S1, S2"
    story = dict(zip(header, rows[2].split(";")))
    assert story["Story Points (hochrechnen)"] == "" and story["Story Points"] == "2"


# ---------------------------------------------------------------- Datenschutz beim Laden

def test_people_releases_areas_priorities_labels_and_components_are_not_read_at_all():
    """Die Spalten stehen in der Datei (mit Namen und Werten), landen aber in keinem Ticket und nicht im Erkennungsbericht."""
    issues, report = J.read_plan(_csv(EPIC, STORY_A, STORY_B))
    assert not any(hasattr(i, name) for i in issues for name in ("assignee", "versions", "area", "priority", "labels", "components"))
    assert [row["Feld"] for row in report.columns] == ["Ticket-Schlüssel", "Titel", "Ticket-Typ", "Status", "Story Points", "Übergeordnetes Ticket", "Sprint", "Team", "Jira: Fortschritt (%)",
                                                       "Jira: Fortschritt abgeschlossen (SP)", "Jira: Verbleibender Fortschritt (SP)"]
    assert "Person A" not in repr(issues) and "ux" not in repr(issues)


SP_HEADER = [h.replace("Schätzung (T)", "Story Points").replace("(T)", "(SP)") for h in REAL_HEADER if not h.startswith("Schätzung (T)")]


def test_export_header_with_story_points_as_the_estimate_unit_finds_all_fields():
    """Kopfzeile eines Exports, dessen Schätzung in Story Points läuft (Fortschritt abgeschlossen (SP)): alle Felder werden gefunden, die Hochrechnungs-Spalten nicht gelesen."""
    cells = dict.fromkeys(SP_HEADER, "")
    cells.update({"Hierarchie": "Story", "Vorgangsschlüssel": "A-2", "Vorgangsstatus": "Done", "Story Points": "3,5", "Story Points (hochrechnen)": "99", "Übergeordnetes Element": "A-1"})
    parent = dict.fromkeys(SP_HEADER, "")
    parent.update({"Hierarchie": "Epic", "Vorgangsschlüssel": "A-1", "Vorgangsstatus": "In Arbeit"})
    data = ("\n".join(";".join(r[h] for h in SP_HEADER) for r in ({h: h for h in SP_HEADER}, parent, cells)) + "\n").encode("utf-8")
    issues, report = J.read_plan(data)
    story = next(i for i in issues if i.key == "A-2")
    assert story.points == 3.5 and story.parent == "A-1" and next(i for i in issues if i.key == "A-1").points is None
    assert all(row["Gefunden in"] != J.NOT_FOUND for row in report.columns) and report.notes == []


def _sp_csv(*rows):
    """CSV mit der Kopfzeile `SP_HEADER`; jede Zeile ist ein Wörterbuch Spaltenkopf -> Wert."""
    return ("\n".join(";".join(r[h] for h in SP_HEADER) for r in rows) + "\n").encode("utf-8")


def test_jiras_own_progress_columns_are_read_for_the_comparison_only():
    cells = dict.fromkeys(SP_HEADER, "")
    cells.update({"Hierarchie": "Epic", "Vorgangsschlüssel": "A-1", "Vorgangsstatus": "In Arbeit", "Fortschritt (%)": "35,5", "Fortschritt abgeschlossen (SP)": "7", "Verbleibender Fortschritt (SP)": "13"})
    plain = dict.fromkeys(SP_HEADER, "")
    plain.update({"Hierarchie": "Story", "Vorgangsschlüssel": "A-2", "Vorgangsstatus": "Done", "Story Points": "3", "Übergeordnetes Element": "A-1"})
    data = _sp_csv(dict(zip(SP_HEADER, SP_HEADER, strict=True)), cells, plain)
    issues, report = J.read_plan(data)
    epic, story = issues
    assert (epic.jira_progress, epic.jira_done, epic.jira_left) == (pytest.approx(0.355), 7.0, 13.0) and (story.jira_progress, story.jira_done, story.jira_left) == (None, None, None)
    found = {row["Feld"]: (row["Gefunden in"], row["Tickets mit Wert"]) for row in report.columns}
    assert found["Jira: Fortschritt (%)"] == ("Fortschritt (%)", 1) and found["Jira: Fortschritt abgeschlossen (SP)"] == ("Fortschritt abgeschlossen (SP)", 1)
    assert found["Jira: Verbleibender Fortschritt (SP)"] == ("Verbleibender Fortschritt (SP)", 1)
    assert story.points == 3.0                                                                          # die Spalten verändern keine Rechnung


@pytest.mark.parametrize("text, expected", [("35", 0.35), ("35,5", 0.355), ("35 %", 0.35), (" 100% ", 1.0), ("0", 0.0), ("", None), ("viel", None), (None, None)])
def test_percent_values_are_read_as_shares(text, expected):
    assert J.parse_percent(text) == pytest.approx(expected) if expected is not None else J.parse_percent(text) is None
