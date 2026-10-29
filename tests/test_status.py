"""Status nach Namen (fertig 100 / Test 90 / Merged oder Review 80, deutsch und englisch, sonst 0), zurückgewiesene Tickets und die Tabelle der Status-Gewichte."""

import pytest

import jira_core as A
from jira_core import Issue

CLASSES = {
    "done": ["Done", "Closed", "Resolved", "Fertig", "Erledigt", "Abgeschlossen", "Geschlossen", "Released", "Deployed", "Live", "Ready4Prod", "In Production", "Produktion", "Completed",
             "Finished", "Fertiggestellt", "Done (QA ok)", "In Prod"],
    "merged": ["Merged", "Gemerged", "Merged to main", "Zusammengeführt", "MERGED"],
    "test": ["In Test", "Testing", "Ready4Test", "Ready for Test", "QA", "UAT", "Abnahme", "In Abnahme", "Verification", "Verifiziert", "Getestet", "Test", "In QA", "Test Review",
             "Abnahmeprüfung"],
    "rejected": ["Rejected", "Zurückgewiesen", "Won't do", "Wont do", "Won’t Do", "Will not do", "Abgelehnt", "Cancelled", "Canceled", "Abgebrochen", "Duplicate", "Duplikat",
                 "Obsolete", "Invalid", "Declined", "Abandoned", "Verworfen", "Won't fix", "ZURÜCKGEWIESEN"],
    "review": ["In Review", "Review", "Code Review", "Ready for Review", "Reviewed", "Product Review", "Wird überprüft", "Überprüfung", "Zu überprüfen", "Geprüft", "In Prüfung", "Prüfung",
               "Begutachtung", "IN REVIEW"],
    "other": ["To Do", "Backlog", "In Progress", "In Arbeit", "On Hold", "Specification", "Open", "Product Backlog", "Not done", "Nicht fertig", "Unreviewed", "Nicht überprüft", "Ungeprüft",
              "Untested", "Ungetestet", "Incomplete", "Unresolved", "Blocked", "Ready for Development", "Estimate", "Reopened", "Olive", "Nicht abgeschlossen", "Undone", ""],
}


@pytest.mark.parametrize("expected,name", [(c, n) for c, names in CLASSES.items() for n in names])
def test_status_class_by_name(expected, name):
    assert A.status_class(name) == expected


def test_name_key_drops_case_accents_and_punctuation():
    assert A.name_key("Won't do") == "wontdo" and A.name_key("Zurückgewiesen") == "zuruckgewiesen" and A.name_key("  In  Test! ") == "intest" and A.name_key(None) == ""


def test_credits_by_name_by_hand():
    assert A.status_credits(["Done", "Ready4Prod", "Merged", "In Test", "Testing", "In Progress", "To Do", "Won't do", "In Review", "Wird überprüft", "Geprüft"]) == {
        "Done": 1.0, "Ready4Prod": 1.0, "Merged": 0.8, "In Test": 0.9, "Testing": 0.9, "In Progress": 0.0, "To Do": 0.0, "Won't do": 0.0,
        "In Review": 0.8, "Wird überprüft": 0.8, "Geprüft": 0.8}
    assert A.status_credits(["Fertig", "Getestet", "Gemerged", "Offen"]) == {"Fertig": 1.0, "Getestet": 0.9, "Gemerged": 0.8, "Offen": 0.0}


def test_overrides_replace_single_values_and_leave_the_rest():
    credits = A.status_credits(["Done", "In Review", "To Do"], (("In Review", 0.5), ("Unbekannt", 1.0)))
    assert credits == {"Done": 1.0, "In Review": 0.5, "To Do": 0.0}


def test_done_status_is_the_done_class_only():
    assert A.is_done_status("Ready4Prod") and A.is_done_status("Fertig") and not A.is_done_status("In Test") and not A.is_done_status("Rejected") and not A.is_done_status("Not done")
    assert A.is_rejected_status("Zurückgewiesen") and not A.is_rejected_status("Done")


# ---------------------------------------------------------------- Zurückgewiesene Tickets

# Epic E1 -> S1 Done, S2 „Won't do“, S3 In Progress mit Sub-Tasks S3a Zurückgewiesen und S3b Done;  Epic E2 „Rejected“ -> S4 In Progress mit Sub-Task S4a;  Story X Merged
TREE = (
    Issue(key="E1", type="Epic", status="In Arbeit"),
    Issue(key="S1", status="Done", points=2.0, parent="E1"),
    Issue(key="S2", status="Won't do", points=3.0, parent="E1"),
    Issue(key="S3", status="In Progress", points=4.0, parent="E1"),
    Issue(key="S3a", type="Sub-task", is_subtask=True, status="Zurückgewiesen", points=1.0, parent="S3"),
    Issue(key="S3b", type="Sub-task", is_subtask=True, status="Done", points=1.0, parent="S3"),
    Issue(key="E2", type="Epic", status="Rejected"),
    Issue(key="S4", status="In Progress", points=5.0, parent="E2"),
    Issue(key="S4a", type="Sub-task", is_subtask=True, status="To Do", points=1.0, parent="S4"),
    Issue(key="X", status="Merged", points=3.0),
)


def test_rejected_indices_include_what_hangs_below_a_rejected_ticket():
    assert sorted(TREE[i].key for i in A.rejected_indices(TREE)) == ["E2", "S2", "S3a", "S4", "S4a"]


def test_rejected_indices_survive_a_cycle():
    loop = (Issue(key="A", parent="B", status="Rejected"), Issue(key="B", parent="A"), Issue(key="C", parent="B"))
    assert A.rejected_indices(loop) == frozenset({0, 1, 2})
    no_rejected = (Issue(key="A", parent="B"), Issue(key="B", parent="A"), Issue(key="C", parent="B"))
    assert A.rejected_indices(no_rejected) == frozenset()


def test_rejected_ancestors_are_followed_twenty_levels_up_and_no_further():
    chain = [Issue(key="N0", status="Rejected")] + [Issue(key=f"N{k}", parent=f"N{k - 1}") for k in range(1, 26)]
    found = A.rejected_indices(chain)
    assert 20 in found and 21 not in found and 1 in found and 0 in found


# ---------------------------------------------------------------- Tabelle der Gewichte

def test_apply_credit_edits_converts_percent_clamps_and_ignores_empty_cells():
    shown = (("A", 0.0), ("B", 0.8), ("C", 1.0))
    assert A.apply_credit_edits(shown, {0: {"Gewicht (%)": 50}, 1: {"Gewicht (%)": 150}, 2: {"Gewicht (%)": None}}) == (("A", 0.5), ("B", 1.0), ("C", 1.0))
    assert A.apply_credit_edits(shown, {1: {"Gewicht (%)": -5}}) == (("A", 0.0), ("B", 0.0), ("C", 1.0))
    assert A.apply_credit_edits(shown, {}) == shown


def test_credit_overrides_keep_only_deviations_from_the_name():
    base = (("Done", 1.0), ("In Review", 0.8), ("To Do", 0.0))
    assert A.credit_overrides(base, (("Done", 1.0), ("In Review", 0.5), ("To Do", 0.0), ("Fremd", 0.3))) == (("In Review", 0.5),)
    assert A.credit_overrides(base, base) == ()


def test_edited_overrides_replace_shown_statuses_and_keep_the_hidden_ones():
    base = (("Done", 1.0), ("In Review", 0.8))
    shown = (("Done", 1.0), ("In Review", 0.5))                    # In Review war schon geändert
    old = (("In Review", 0.5), ("Hidden", 0.3))                  # „Hidden“ steht im gewählten Teilprojekt nicht in der Tabelle
    again = A.edited_overrides(old, base, shown, {1: {"Gewicht (%)": 80}})        # zurück auf den Namen: 80 % = die Vorgabe
    assert dict(again) == {"Hidden": 0.3}
    other = A.edited_overrides(old, base, shown, {0: {"Gewicht (%)": 90}})
    assert dict(other) == {"Hidden": 0.3, "Done": 0.9, "In Review": 0.5}


def test_new_rank_puts_not_yet_started_names_first_and_orders_statuses_of_equal_credit():
    assert [A.new_rank(n) for n in ("Backlog", "To Do", "Specification", "Estimate", "Ready for Development", "Offen")] == [0] * 6
    assert [A.new_rank(n) for n in ("In Progress", "In Arbeit", "On Hold")] == [1] * 3
    assert [A.new_rank(n) for n in ("Ready4Test", "Ready4Prod", "Ready for Review")] == [1, 1, 1]                 # „ready“ allein macht einen Namen noch nicht zum Start des Workflows


def test_the_example_names_of_the_description_fall_into_their_class():
    assert set(A.STATUS_EXAMPLES) == {"done", "test", "merged", "review", "other", "rejected"}
    for kind, names in A.STATUS_EXAMPLES.items():
        for name in names:
            assert A.status_class(name) == kind, (kind, name)


def test_every_example_name_has_a_recognized_meaning_and_names_nobody_knows_do_not():
    for names in A.STATUS_EXAMPLES.values():
        for name in names:
            assert A.status_recognized(name), name
    for name in ("Ready for Dev", "On Hold", "In Entwicklung", "Waiting for customer", "Not done", "In Arbeit"):
        assert A.status_recognized(name), name
    for name in ("Freigegeben", "Entfällt", "Zur Klärung", "Phase 2", ""):
        assert not A.status_recognized(name), name
