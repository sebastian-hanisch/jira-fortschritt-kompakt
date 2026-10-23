"""Tabellen von Hand: Status-Matrix je Ticket unter der Wurzel, Wirkung der Regeln und die Ausgabe als CSV, Wiki-Markup und HTML für Jira und Confluence."""

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
    rows, status_cols, completed = T.status_matrix(ITEMS, a)
    return {r[T.ROW_COL]: r for r in rows}, status_cols, completed, a


def test_columns_follow_the_schema_with_the_weight_in_the_header():
    by, status_cols, completed, _ = _matrix()
    assert status_cols == ["Backlog", "Specification", "In Progress", "In Review (0.8)", "Merged (0.8)", "Ready4Test (0.9)", "Ready4Prod (1.0)"]
    assert completed == COMPLETED
    assert list(by["E1: Eins"]) == [T.ROW_COL, *status_cols, T.REJECTED_COL, T.TOTAL_NET_COL, completed, T.PROGRESS_COL]


def test_epic_one_by_hand():
    row = _matrix()[0]["E1: Eins"]
    assert [row[c] for c in ("Backlog", "Specification", "In Progress", "In Review (0.8)", "Merged (0.8)", "Ready4Test (0.9)", "Ready4Prod (1.0)")] == [5.0, 3.0, 4.0, 2.0, 6.0, 10.0, 8.0]
    assert row[T.REJECTED_COL] == 7.0 and row[T.TOTAL_NET_COL] == 38.0
    assert row[COMPLETED] == pytest.approx(18 / 38)
    assert row[T.PROGRESS_COL] == pytest.approx((2 * 0.8 + 6 * 0.8 + 10 * 0.9 + 8 * 1.0) / 38)    # In Review zählt wie Merged: 23.4 / 38


def test_epic_two_uses_the_median_of_the_counted_tickets_for_the_unestimated_one():
    row = _matrix()[0]["E2: Zwei"]
    assert row["Backlog"] == 5.0 and row["Ready4Prod (1.0)"] == 4.0 and row["In Progress"] == 6.0       # Median der gezählten Tickets: 5 (das 7er-Rejected zählt nicht mit)
    assert row[T.TOTAL_NET_COL] == 15.0
    assert row[COMPLETED] == pytest.approx(4 / 15) and row[T.PROGRESS_COL] == pytest.approx(4 / 15)


def test_the_rule_for_unestimated_tickets_reaches_the_matrix():
    by, _, completed, _ = _matrix(unest_rule=C.UNEST_IGNORE)
    row = by["E2: Zwei"]
    assert row["Backlog"] == 0.0 and row[T.TOTAL_NET_COL] == 10.0 and row[T.PROGRESS_COL] == pytest.approx(4 / 10)           # S12 wiegt nichts
    one = _matrix(unest_rule=C.UNEST_ONE)[0]["E2: Zwei"]
    assert one["Backlog"] == 1.0 and one[T.TOTAL_NET_COL] == 11.0


def test_a_parent_that_is_rejected_puts_its_tickets_into_the_rejected_column():
    row = _matrix()[0]["E3: Drei"]
    assert row[T.REJECTED_COL] == 3.0 and row[T.TOTAL_NET_COL] == 0.0
    assert row[COMPLETED] is None and row[T.PROGRESS_COL] is None and all(row[c] == 0.0 for c in ("Backlog", "In Progress"))


def test_sum_row_adds_everything_and_compares_nothing():
    total = _matrix()[0][T.SUM_LABEL]
    assert total[T.TOTAL_NET_COL] == 53.0 and total[T.REJECTED_COL] == 10.0
    assert total[COMPLETED] == pytest.approx(22 / 53) and total[T.PROGRESS_COL] == pytest.approx((23.4 + 4) / 53)
    assert total["Backlog"] == 10.0 and total["Ready4Prod (1.0)"] == 12.0


def test_the_matrix_follows_root_and_changed_weights():
    sub = scope_issues(ITEMS, "E2")
    sub_rows = T.status_matrix(sub, ev.analyse(sub, ev.Settings(root="E2")))[0]
    assert [r[T.ROW_COL] for r in sub_rows] == ["S9", "S10", "S12", T.SUM_LABEL]                              # eine Zeile je Ticket unter der Wurzel E2
    changed = ev.analyse(ITEMS, ev.Settings(overrides=(("In Review", 0.0), ("Merged", 0.9))))
    rows, status_cols, completed = T.status_matrix(ITEMS, changed)
    assert "In Review" in status_cols and "Merged (0.9)" in status_cols and completed.startswith("Completed (Merged+Ready4Test+Ready4Prod)")


def test_no_status_at_90_percent_gives_a_named_empty_completed_column():
    items = (Issue(key="E", type="Epic"), _story("A", "In Progress", 4.0, "E"), _story("B", "To Do", 2.0, "E"))
    rows, _, completed = T.status_matrix(items, ev.analyse(items))
    assert completed == "Completed (kein Status ab 90 %)" and all(r[completed] is None for r in rows)


def test_a_plan_without_countable_tickets_gives_no_rows():
    only_epic = (Issue(key="E", type="Epic"),)
    assert T.status_matrix(only_epic, ev.analyse(only_epic))[0] == []


def test_tickets_without_a_parent_are_their_own_rows_in_natural_order():
    items = (Issue(key="E2", type="Epic", summary="B"), Issue(key="E10", type="Epic", summary="A"), _story("X", "Done", 1.0, "E10"), _story("Y", "Done", 1.0, "E2"), _story("Z", "Done", 1.0, ""))
    rows, _, _ = T.status_matrix(items, ev.analyse(items))
    assert [r[T.ROW_COL] for r in rows] == ["E2: B", "E10: A", "Z", T.SUM_LABEL]


def test_fractional_totals_below_one_still_give_the_shares():
    items = (Issue(key="E", type="Epic"), _story("A", "Ready4Prod", 0.5, "E"), _story("B", "Backlog", 0.25, "E"))
    rows, _, completed = T.status_matrix(items, ev.analyse(items))
    assert rows[0][T.TOTAL_NET_COL] == 0.75 and rows[0][completed] == pytest.approx(0.5 / 0.75) and rows[0][T.PROGRESS_COL] == pytest.approx(0.5 / 0.75)


# ---------------------------------------------------------------- Gruppen und Status

# ---------------------------------------------------------------- Datenqualität

# ---------------------------------------------------------------- Ausgabe

def test_format_cell():
    assert T.format_cell(None) == "" and T.format_cell(float("nan")) == "" and T.format_cell(True) == "ja" and T.format_cell(False) == "nein"
    assert T.format_cell(0.444, "percent") == "44.4 %" and T.format_cell(3.0) == "3" and T.format_cell(2.5) == "2.50" and T.format_cell(38.25) == "38.25" and T.format_cell(7) == "7"
    assert T.format_cell(4.0, "%.1f") == "4.0" and T.format_cell(4.0, "%.0f") == "4" and T.format_cell(1.5, "%.2f") == "1.50" and T.format_cell("Text") == "Text"


ROWS = [{"Gruppe": "A|B", "Gewicht": 1.5, "Fortschritt": 0.5}, {"Gruppe": "Summe", "Gewicht": 2.0, "Fortschritt": None}]
FORMATS = {"Gewicht": "%.1f", "Fortschritt": "percent"}


def test_wiki_markup_escapes_special_characters_and_bolds_the_sum_row():
    assert T.rows_to_wiki(ROWS, FORMATS).split("\n") == ["||Gruppe||Gewicht||Fortschritt||", "|A\\|B|1.5|50.0 %|", "|*Summe*|*2.0*| |"]
    assert T.rows_to_wiki([]) == "" and "\\*" in T.rows_to_wiki([{"x": "a*b"}])


def test_html_table_has_a_header_aligned_numbers_and_escaped_text():
    html = T.rows_to_html(ROWS + [{"Gruppe": "<b>", "Gewicht": 1.0, "Fortschritt": 0.1}], FORMATS)
    assert html.startswith("<table") and html.count("<th ") == 3 and "&lt;b&gt;" in html and "<strong>Summe</strong>" in html
    assert 'text-align:right;">1.5<' in html and 'text-align:left;">A|B<' in html and T.rows_to_html([]) == ""


def test_csv_for_excel_uses_semicolon_decimal_comma_and_a_byte_order_mark():
    raw = T.rows_to_csv([{"Gruppe": "a;b", "Gewicht": 0.5, "Fortschritt": None, "Tickets": 3}])
    assert raw.startswith(b"\xef\xbb\xbf") and raw.decode("utf-8-sig") == "Gruppe;Gewicht;Fortschritt;Tickets\na,b;0.5;;3\n"
    assert T.rows_to_csv([]) == b"\xef\xbb\xbf"
    assert T.rows_to_csv([{"x": float("nan"), "y": "z\nw"}]).decode("utf-8-sig") == "x;y\n;z w\n"


def test_status_rules_text_lists_the_credits_and_the_examples():
    import jira_core as A
    text = T.status_rules_markdown()
    assert "**Fertig → 100 %.**" in text and "**Test → 90 %.**" in text and "**Merged → 80 %.**" in text and "**Review → 80 %.**" in text and "**Alles andere → 0 %**" in text
    assert text.index("Zurückgewiesen → zählt nicht") < text.index("Verneinung") < text.index("Fertig → 100") < text.index("Merged → 80") < text.index("Test → 90") < text.index("Review → 80")
    for names in A.STATUS_EXAMPLES.values():
        for name in names:
            assert name in text, name
    assert "| 100 % | Done," in text and "| zählt nicht | Rejected," in text


def test_rule_comparison_by_hand(mini):
    rows = T.unestimated_rule_comparison(mini, ev.analyse(mini))
    assert [r["Regel"] for r in rows] == list(C.UNEST_RULES) and len(rows) == 8
    assert [r["Fortschritt"] for r in rows] == pytest.approx([7 / 10.5, 7 / 10.5, 7 / 10.5, 6.6 / 10, 7.6 / 12, 7.6 / 12, 5.8 / 9, 4 / 6])
    assert [r["Gewicht gesamt"] for r in rows] == pytest.approx([10.5, 10.5, 10.5, 10.0, 12.0, 12.0, 9.0, 6.0]) and [r["Tickets ohne Story Points"] for r in rows] == [3] * 8


def test_rule_comparison_keeps_root_and_status_weights_and_handles_no_weight():
    from jira_core import scope_issues
    sub = scope_issues(ITEMS, "E2")
    rows = T.unestimated_rule_comparison(sub, ev.analyse(sub, ev.Settings(root="E2")))
    assert rows[0]["Gewicht gesamt"] == 15.0 and rows[-1]["Gewicht gesamt"] == 10.0          # Median 5 für S12 gegen „nicht zählen“
    none = (Issue(key="A", status="Done"),)
    assert [r["Fortschritt"] for r in T.unestimated_rule_comparison(none, ev.analyse(none))] == [pytest.approx(1.0)] * 7 + [None]
    changed = ev.analyse(ITEMS, ev.Settings(overrides=(("Backlog", 0.5),)))
    assert T.unestimated_rule_comparison(ITEMS, changed)[0]["Fortschritt"] == ev.analyse(ITEMS, ev.Settings(overrides=(("Backlog", 0.5),))).progress


def test_the_options_text_names_every_variant_with_pros_and_cons_and_its_status():
    text = T.UNEST_OPTIONS_MARKDOWN
    for letter in "ABCDEFGHI":
        assert f"**{letter}. " in text, letter
    for letter in "abc":
        assert f"**{letter}. " in text, letter
    assert text.count("wählbar") >= 3 and "Vorschlag" in text and "Vorteile" in text and "Nachteile" in text and "Einschätzung" in text and "keine Messungen" in text


def test_sub_task_rule_comparison_by_hand(mini):
    rows = T.subtask_rule_comparison(mini, ev.analyse(mini))
    assert [r["Regel"] for r in rows] == list(C.SUB_RULES)
    assert [r["Fortschritt"] for r in rows] == pytest.approx([7 / 10.5, 8.5 / 13.5, 6.4 / 14]) and [r["Gewicht gesamt"] for r in rows] == pytest.approx([10.5, 13.5, 14.0])
    assert [r["Zählende Tickets"] for r in rows] == [6, 6, 5]
    other = T.subtask_rule_comparison(mini, ev.analyse(mini, ev.Settings(unest_rule=C.UNEST_ONE)))
    assert other[0]["Gewicht gesamt"] == pytest.approx(9.0)                                       # die gewählte Regel für Tickets ohne Story Points gilt mit


def test_the_rows_are_the_tickets_directly_below_the_root_with_everything_below_them(mini):
    rows, status_cols, completed = T.status_matrix(mini, ev.analyse(mini))
    assert status_cols == ["To Do", "In Review (0.8)", "Done (1.0)"] and completed == "Completed (Done)/(Total−Rejected)"
    by = {r[T.ROW_COL]: r for r in rows}
    assert list(by) == ["B1", "E1: Epic A", "E2: Epic B", T.SUM_LABEL]
    e1, e2, b1 = by["E1: Epic A"], by["E2: Epic B"], by["B1"]
    assert (e1["To Do"], e1["Done (1.0)"], e1[T.TOTAL_NET_COL]) == (1.0, 4.0, 5.0)                       # T2; S1 (3) und T1 (1): alles unter E1 steht in der Zeile von E1
    assert e1[T.PROGRESS_COL] == pytest.approx(4 / 5)
    assert (e2["To Do"], e2["In Review (0.8)"]) == (2.0, 2.5) and e2[T.PROGRESS_COL] == pytest.approx(2 / 4.5)
    assert b1["Done (1.0)"] == 1.0
    below = scope_issues(mini, "E1")
    rows, _, _ = T.status_matrix(below, ev.analyse(below, ev.Settings(root="E1")))
    by = {r[T.ROW_COL]: r for r in rows}
    assert list(by) == ["S1", "S2", T.SUM_LABEL]                                                      # eine Stufe tiefer: die Kinder von E1; T1 und T2 stehen in der Zeile von S2
    assert by["S1"]["Done (1.0)"] == 3.0 and by["S2"]["Done (1.0)"] == 1.0 and by["S2"]["To Do"] == 1.0


def test_matrix_weights_are_written_with_two_decimals_for_jira_and_confluence():
    items = (Issue(key="E", type="Epic"), _story("A", "Done", 0.25, "E"), _story("B", "To Do", 38.0, "E"))
    rows, status_cols, completed = T.status_matrix(items, ev.analyse(items))
    formats = {name: "%.2f" for name in (*status_cols, T.REJECTED_COL, T.TOTAL_NET_COL)}
    assert rows[0][T.TOTAL_NET_COL] == 38.25
    assert "|38.25|" in T.rows_to_wiki(rows, formats) and "38.25" in T.rows_to_html(rows, formats) and "38.3" not in T.rows_to_wiki(rows, formats)


def test_assumptions_text_has_the_three_parts_and_matches_the_readme():
    import pathlib
    text = T.ASSUMPTIONS_MARKDOWN
    for part in ("### Annahmen", "### Grenzen", "### Bekannte Probleme und Unsicherheiten", "Nur ein Stichtag", "Tiefe im Baum, nicht Typ", "Obergrenzen", "Spaltennamen des Exports sind erschlossen", "Klick in die Diagramme"):
        assert part in text, part
    readme = (pathlib.Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert text.strip() in readme                                                                  # die README gibt denselben Text wieder
