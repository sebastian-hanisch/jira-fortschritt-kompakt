"""Tabellen von Hand: Status-Matrix je Parent, Gruppen, Status × Gruppe, Datenqualität, Liste ohne Schätzung und die Ausgabe als CSV, Wiki-Markup und HTML für Jira und Confluence."""

import pytest

import jira_constants as C
import jira_evaluation as ev
import jira_tables as T
from jira_core import Issue, scope_issues


def _story(key, status, points, parent):
    return Issue(key=key, status=status, points=points, parent=parent)


# E1 hat eine eigene Schätzung (20) und Stories in allen Status; E2 keine eigene Schätzung; E3 ist zurückgewiesen
ITEMS = (
    Issue(key="E1", type="Epic", summary="Eins", points=20.0, status="In Progress"),
    _story("S1", "Backlog", 5.0, "E1"), _story("S2", "Specification", 3.0, "E1"), _story("S3", "In Progress", 4.0, "E1"), _story("S4", "In Review", 2.0, "E1"),
    _story("S5", "Merged", 6.0, "E1"), _story("S6", "Ready4Test", 10.0, "E1"), _story("S7", "Ready4Prod", 8.0, "E1"), _story("S8", "Rejected", 7.0, "E1"),
    Issue(key="E2", type="Epic", summary="Zwei", status="In Progress"),
    _story("S9", "Ready4Prod", 4.0, "E2"), _story("S10", "In Progress", 6.0, "E2"), _story("S12", "Backlog", None, "E2"),
    Issue(key="E3", type="Epic", summary="Drei", status="Rejected"),
    _story("S11", "In Progress", 3.0, "E3"),
)
COMPLETED = "Completed (Ready4Test+Ready4Prod)/(Total−Rejected)"


def _matrix(**kw):
    a = ev.analyse(ITEMS, ev.Settings(**kw))
    rows, status_cols, completed = T.parent_status_matrix(ITEMS, a)
    return {r[T.PARENT_COL]: r for r in rows}, status_cols, completed, a


def test_columns_follow_the_schema_with_the_weight_in_the_header():
    by, status_cols, completed, _ = _matrix()
    assert status_cols == ["Backlog", "Specification", "In Progress", "In Review (0,8)", "Merged (0,8)", "Ready4Test (0,9)", "Ready4Prod (1,0)"]
    assert completed == COMPLETED
    assert list(by["E1: Eins"]) == [T.PARENT_COL, T.EPIC_COL, T.TOTAL_COL, T.EPIC_CHECK_COL, *status_cols, T.REJECTED_COL, T.TOTAL_NET_COL, completed, T.PROGRESS_COL]


def test_epic_one_by_hand():
    row = _matrix()[0]["E1: Eins"]
    assert [row[c] for c in ("Backlog", "Specification", "In Progress", "In Review (0,8)", "Merged (0,8)", "Ready4Test (0,9)", "Ready4Prod (1,0)")] == [5.0, 3.0, 4.0, 2.0, 6.0, 10.0, 8.0]
    assert row[T.REJECTED_COL] == 7.0 and row[T.TOTAL_NET_COL] == 38.0 and row[T.TOTAL_COL] == 45.0 and row[T.EPIC_COL] == 20.0
    assert row[T.EPIC_CHECK_COL] == "⚠ weicht ab (+25,0)"                                    # Total 45 gegen die eigene Schätzung 20
    assert row[COMPLETED] == pytest.approx(18 / 38)
    assert row[T.PROGRESS_COL] == pytest.approx((2 * 0.8 + 6 * 0.8 + 10 * 0.9 + 8 * 1.0) / 38)    # In Review zählt wie Merged: 23,4 / 38


def test_epic_two_uses_the_median_of_the_counted_tickets_for_the_unestimated_one():
    row = _matrix()[0]["E2: Zwei"]
    assert row["Backlog"] == 5.0 and row["Ready4Prod (1,0)"] == 4.0 and row["In Progress"] == 6.0       # Median der gezählten Tickets: 5 (das 7er-Rejected zählt nicht mit)
    assert row[T.TOTAL_NET_COL] == 15.0 and row[T.TOTAL_COL] == 15.0 and row[T.EPIC_COL] is None and row[T.EPIC_CHECK_COL] == ""
    assert row[COMPLETED] == pytest.approx(4 / 15) and row[T.PROGRESS_COL] == pytest.approx(4 / 15)


def test_the_rule_for_unestimated_tickets_reaches_the_matrix():
    by, _, completed, _ = _matrix(unest_rule=C.UNEST_IGNORE)
    row = by["E2: Zwei"]
    assert row["Backlog"] == 0.0 and row[T.TOTAL_NET_COL] == 10.0 and row[T.PROGRESS_COL] == pytest.approx(4 / 10)           # S12 wiegt nichts
    one = _matrix(unest_rule=C.UNEST_ONE)[0]["E2: Zwei"]
    assert one["Backlog"] == 1.0 and one[T.TOTAL_NET_COL] == 11.0


def test_a_parent_that_is_rejected_puts_its_tickets_into_the_rejected_column():
    row = _matrix()[0]["E3: Drei"]
    assert row[T.REJECTED_COL] == 3.0 and row[T.TOTAL_NET_COL] == 0.0 and row[T.TOTAL_COL] == 3.0
    assert row[COMPLETED] is None and row[T.PROGRESS_COL] is None and all(row[c] == 0.0 for c in ("Backlog", "In Progress"))


def test_sum_row_adds_everything_and_compares_nothing():
    total = _matrix()[0][T.SUM_LABEL]
    assert total[T.TOTAL_NET_COL] == 53.0 and total[T.REJECTED_COL] == 10.0 and total[T.TOTAL_COL] == 63.0 and total[T.EPIC_COL] == 20.0 and total[T.EPIC_CHECK_COL] == ""
    assert total[COMPLETED] == pytest.approx(22 / 53) and total[T.PROGRESS_COL] == pytest.approx((23.4 + 4) / 53)
    assert total["Backlog"] == 10.0 and total["Ready4Prod (1,0)"] == 12.0


def test_a_matching_estimate_is_marked_as_equal():
    items = (Issue(key="E", type="Epic", points=9.0), _story("A", "Done", 4.0, "E"), _story("B", "To Do", 5.0, "E"))
    row = T.parent_status_matrix(items, ev.analyse(items))[0][0]
    assert row[T.EPIC_CHECK_COL] == "gleich" and row[T.TOTAL_COL] == 9.0 and row[T.PROGRESS_COL] == pytest.approx(4 / 9)


def test_the_matrix_follows_root_and_changed_weights():
    sub = scope_issues(ITEMS, "E2")
    sub_rows = T.parent_status_matrix(sub, ev.analyse(sub, ev.Settings(root="E2")))[0]
    assert {r[T.PARENT_COL] for r in sub_rows} == {"E2: Zwei", T.SUM_LABEL}
    changed = ev.analyse(ITEMS, ev.Settings(overrides=(("In Review", 0.0), ("Merged", 0.9))))
    rows, status_cols, completed = T.parent_status_matrix(ITEMS, changed)
    assert "In Review" in status_cols and "Merged (0,9)" in status_cols and completed.startswith("Completed (Merged+Ready4Test+Ready4Prod)")


def test_no_status_at_90_percent_gives_a_named_empty_completed_column():
    items = (Issue(key="E", type="Epic"), _story("A", "In Progress", 4.0, "E"), _story("B", "To Do", 2.0, "E"))
    rows, _, completed = T.parent_status_matrix(items, ev.analyse(items))
    assert completed == "Completed (kein Status ab 90 %)" and all(r[completed] is None for r in rows)


def test_a_plan_without_countable_tickets_gives_no_rows():
    only_epic = (Issue(key="E", type="Epic"),)
    assert T.parent_status_matrix(only_epic, ev.analyse(only_epic))[0] == []
    assert T.status_by_group(only_epic, ev.analyse(only_epic), T.METRIC_WEIGHT) == []


def test_tickets_without_a_parent_form_their_own_row_after_the_parents_in_natural_order():
    items = (Issue(key="E2", type="Epic", summary="B"), Issue(key="E10", type="Epic", summary="A"), _story("X", "Done", 1.0, "E10"), _story("Y", "Done", 1.0, "E2"), _story("Z", "Done", 1.0, ""))
    rows, _, _ = T.parent_status_matrix(items, ev.analyse(items))
    assert [r[T.PARENT_COL] for r in rows] == ["E2: B", "E10: A", "(ohne Parent)", T.SUM_LABEL]


def test_fractional_totals_below_one_still_give_the_shares():
    items = (Issue(key="E", type="Epic"), _story("A", "Ready4Prod", 0.5, "E"), _story("B", "Backlog", 0.25, "E"))
    rows, _, completed = T.parent_status_matrix(items, ev.analyse(items))
    assert rows[0][T.TOTAL_NET_COL] == 0.75 and rows[0][completed] == pytest.approx(0.5 / 0.75) and rows[0][T.PROGRESS_COL] == pytest.approx(0.5 / 0.75)


# ---------------------------------------------------------------- Gruppen und Status

def test_group_table_by_hand(mini):
    rows = T.group_table(ev.analyse(mini), "Epic", "T")
    assert [r["Epic"] for r in rows] == ["E1: Epic A", "E2: Epic B", "(ohne Epic)"] and list(rows[0]) == ["Epic", "Gewicht (T)", "Fortschritt", "Nur Done (Gewicht)", "Tickets", "ohne Story Points"]
    assert [r["Gewicht (T)"] for r in rows] == [8.0, 4.5, 1.0] and [r["Tickets"] for r in rows] == [2.0, 2.0, 1.0] and [r["ohne Story Points"] for r in rows] == [0.0, 1.0, 0.0]
    assert [r["Fortschritt"] for r in rows] == pytest.approx([3 / 8, 2 / 4.5, 1.0]) and [r["Nur Done (Gewicht)"] for r in rows] == pytest.approx([3 / 8, 0.0, 1.0])


def test_group_without_weight_has_no_progress():
    items = (Issue(key="A", points=0.0, labels=("x",)),)
    assert T.group_table(ev.analyse(items, ev.Settings(dimension="Label")), "Label", "T")[0]["Fortschritt"] is None


def test_status_by_group_by_hand(mini):
    a = ev.analyse(mini)
    rows = T.status_by_group(mini, a, T.METRIC_WEIGHT)
    assert T.atom_statuses(mini, a) == ["To Do", "In Progress", "In Review", "Done"]
    assert [r["Gruppe"] for r in rows] == ["E1: Epic A", "E2: Epic B", "(ohne Epic)", "Summe"]
    assert [rows[0][s] for s in ("To Do", "In Progress", "In Review", "Done")] == [0.0, 5.0, 0.0, 3.0] and rows[0]["Summe"] == 8.0 and rows[0]["Fortschritt"] == pytest.approx(3 / 8)
    assert [rows[1][s] for s in ("To Do", "In Progress", "In Review", "Done")] == [2.0, 0.0, 2.5, 0.0]
    assert [rows[3][s] for s in ("To Do", "In Progress", "In Review", "Done")] == [2.0, 5.0, 2.5, 4.0] and rows[3]["Summe"] == 13.5 and rows[3]["Fortschritt"] == pytest.approx(6 / 13.5)
    assert [rows[3][s] for s in ("To Do", "In Progress", "In Review", "Done", "Summe")] == [2.0, 5.0, 2.5, 4.0, 13.5]
    assert T.status_by_group(mini, a, T.METRIC_COUNT)[3]["Summe"] == 5.0 and T.status_by_group(mini, a, T.METRIC_COUNT)[0]["Done"] == 1.0
    credited = T.status_by_group(mini, a, T.METRIC_CREDITED)
    assert credited[1]["In Review"] == pytest.approx(2.0) and credited[3]["Summe"] == pytest.approx(6.0)
    with pytest.raises(ValueError):
        T.status_by_group(mini, a, "Unsinn")


def test_status_by_group_with_multi_valued_dimension_keeps_the_total(mini):
    a = ev.analyse(mini, ev.Settings(dimension="Komponente"))
    rows = T.status_by_group(mini, a, T.METRIC_WEIGHT)
    assert rows[-1]["Summe"] == pytest.approx(13.5) and sum(r["Summe"] for r in rows[:-1]) == pytest.approx(13.5)


# ---------------------------------------------------------------- Datenqualität

def test_data_quality_by_hand(mini):
    rows = {r["Prüfung"]: r for r in T.data_quality(mini, ev.analyse(mini))}
    assert {k: v["Anzahl"] for k, v in rows.items()} == {
        "Ohne Story Points": 1, "Story Points = 0": 0, "Ohne Epic": 1, "Ohne Sprint": 1, "Status ohne erkannte Bedeutung (zählt 0)": 2}       # S4; B1; S3; S2 (In Progress) und S3 (To Do)
    assert rows["Ohne Story Points"]["Anteil an den Tickets"] == pytest.approx(0.2) and all(r["Wirkung"] for r in rows.values())


def test_data_quality_without_tickets_has_no_shares():
    only_epic = (Issue(key="E", type="Epic"),)
    assert all(r["Anzahl"] == 0 and r["Anteil an den Tickets"] is None for r in T.data_quality(only_epic, ev.analyse(only_epic)))


def test_unestimated_list(mini):
    a = ev.analyse(mini)
    assert T.unestimated_tickets(mini, a) == ([{"Schlüssel": "S4", "Titel": "", "Typ": "Story", "Status": "In Review", "Epic": "E2"}], 1)
    assert T.unestimated_tickets(mini, a, limit=0) == ([], 1)


# ---------------------------------------------------------------- Ausgabe

def test_format_cell():
    assert T.format_cell(None) == "" and T.format_cell(float("nan")) == "" and T.format_cell(True) == "ja" and T.format_cell(False) == "nein"
    assert T.format_cell(0.444, "percent") == "44,4 %" and T.format_cell(3.0) == "3" and T.format_cell(2.5) == "2,5" and T.format_cell(7) == "7"
    assert T.format_cell(4.0, "%.1f") == "4,0" and T.format_cell(4.0, "%.0f") == "4" and T.format_cell(1.5, "%.2f") == "1,50" and T.format_cell("Text") == "Text"


ROWS = [{"Gruppe": "A|B", "Gewicht": 1.5, "Fortschritt": 0.5}, {"Gruppe": "Summe", "Gewicht": 2.0, "Fortschritt": None}]
FORMATS = {"Gewicht": "%.1f", "Fortschritt": "percent"}


def test_wiki_markup_escapes_special_characters_and_bolds_the_sum_row():
    assert T.rows_to_wiki(ROWS, FORMATS).split("\n") == ["||Gruppe||Gewicht||Fortschritt||", "|A\\|B|1,5|50,0 %|", "|*Summe*|*2,0*| |"]
    assert T.rows_to_wiki([]) == "" and "\\*" in T.rows_to_wiki([{"x": "a*b"}])


def test_html_table_has_a_header_aligned_numbers_and_escaped_text():
    html = T.rows_to_html(ROWS + [{"Gruppe": "<b>", "Gewicht": 1.0, "Fortschritt": 0.1}], FORMATS)
    assert html.startswith("<table") and html.count("<th ") == 3 and "&lt;b&gt;" in html and "<strong>Summe</strong>" in html
    assert 'text-align:right;">1,5<' in html and 'text-align:left;">A|B<' in html and T.rows_to_html([]) == ""


def test_csv_for_excel_uses_semicolon_decimal_comma_and_a_byte_order_mark():
    raw = T.rows_to_csv([{"Gruppe": "a;b", "Gewicht": 0.5, "Fortschritt": None, "Tickets": 3}])
    assert raw.startswith(b"\xef\xbb\xbf") and raw.decode("utf-8-sig") == "Gruppe;Gewicht;Fortschritt;Tickets\na,b;0,5;;3\n"
    assert T.rows_to_csv([]) == b"\xef\xbb\xbf"
    assert T.rows_to_csv([{"x": float("nan"), "y": "z\nw"}]).decode("utf-8-sig") == "x;y\n;z w\n"
