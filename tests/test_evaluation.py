"""Auswertung: Fortschritt von Hand an der Mini-Instanz, zurückgewiesene Tickets, Zeitraum, Teilprojekt als eigenständiger Datensatz, geänderte Gewichte und Eigenschaften
über viele Zufallsprojekte."""

import dataclasses
import math

import pytest

import jira_constants as C
import jira_core as A
import jira_evaluation as ev
from conftest import random_project
from jira_core import Issue
from test_status import TREE


def test_progress_of_the_mini_project_by_hand(mini):
    a = ev.analyse(mini)
    # Blätter S1 (3), S3 (2), S4 (ungeschätzt: Median der Stufe 2.5), B1 (1), T1 und T2 (Stufe ohne geschätztes Ticket: je 1); Gutschriften 1, 0, 0.8 (In Review), 1, 1, 0
    assert (a.n_atoms, a.weight, a.n_unestimated, a.n_excluded) == (6, 10.5, 3, 0)
    assert a.progress == pytest.approx(7 / 10.5) and a.progress_done == pytest.approx(5 / 10.5) and a.progress_count == pytest.approx(3 / 6)
    assert a.credits == {"In Progress": 0.0, "To Do": 0.0, "In Review": 0.8, "Done": 1.0}
    assert ev.check_consistency(a) == [] and [mini[i].key for i in a.atoms] == ["S1", "S3", "S4", "B1", "T1", "T2"]


def test_the_rule_for_unestimated_tickets_changes_the_progress_by_hand(mini):
    ignore = ev.analyse(mini, ev.Settings(unest_rule=C.UNEST_IGNORE))
    assert (ignore.n_atoms, ignore.weight, ignore.n_unestimated) == (6, 6.0, 3) and ignore.progress == pytest.approx(4 / 6)         # S4, T1, T2 wiegen 0: 3 + 1 von 6
    one = ev.analyse(mini, ev.Settings(unest_rule=C.UNEST_ONE))
    assert one.weight == 9.0 and one.progress == pytest.approx((3 + 0.8 + 1 + 1) / 9)
    assert ev.analyse(mini, ev.Settings(unest_rule=C.UNEST_MEDIAN)).progress == pytest.approx(7 / 10.5)
    for a in (ignore, one):
        assert ev.check_consistency(a) == []


def test_changed_status_weights_change_the_progress_by_hand(mini):
    a = ev.analyse(mini, ev.Settings(overrides=(("In Review", 0.5), ("To Do", 0.4))))
    assert a.progress == pytest.approx((3 + 2 * 0.4 + 2.5 * 0.5 + 1 + 1 + 1 * 0.4) / 10.5)
    assert a.progress_done == pytest.approx(5 / 10.5)                                # „nur Done“ hängt nicht von den Gewichten ab


def test_groups_by_hierarchy_level_are_part_of_the_analysis(mini):
    a = ev.analyse(mini, ev.Settings(level=1))
    assert a.stats.labels == ("B1", "E1: Epic A", "E2: Epic B") and a.stats.progress.tolist() == pytest.approx([1.0, 4 / 5, 2 / 4.5])
    assert ev.analyse(mini, ev.Settings(level=2)).stats.labels == ("S1", "S2", "S3", "S4", "(keine Stufe 2)")


def test_status_list_orders_by_credit_then_not_started_first(mini):
    assert ev.status_list(mini) == ["To Do", "In Progress", "In Review", "Done"]
    assert ev.status_list(()) == []


def test_formatting_helpers():
    assert ev.de(1234.5678, 2) == "1234.57" and ev.de(0.5, sign=True) == "+0.5" and ev.de(-0.5, sign=True) == "-0.5" and ev.pct(0.4444) == "44.4 %"


# ---------------------------------------------------------------- Zurückgewiesene Tickets

def test_progress_without_the_rejected_by_hand():
    a = ev.analyse(TREE)
    # gezählt werden die Blätter S1 (2), S3b (1, die Sub-Task von S3) und X (3, Merged); zurückgewiesen sind die Blätter S2, S3a und S4a
    assert (a.n_atoms, a.weight, a.n_excluded) == (3, 6.0, 3)
    assert [TREE[i].key for i in a.atoms] == ["S1", "S3b", "X"] and [TREE[i].key for i in a.rejected_atoms] == ["S2", "S3a", "S4a"]
    assert a.progress == pytest.approx((2 * 1.0 + 1 * 1.0 + 3 * 0.8) / 6) and ev.check_consistency(a) == []          # 5.4 / 6
    assert a.progress_count == pytest.approx(2 / 3)                                    # S1 und S3b sind erledigt, X ist nur Merged


def test_median_uses_only_counted_tickets():
    items = (Issue(key="A", points=2.0, status="Done"), Issue(key="B", points=100.0, status="Rejected"), Issue(key="C", points=None, status="To Do"))
    a = ev.analyse(items)
    assert a.weight == 4.0                                                           # Median 2 (C wiegt 2), nicht 51


def test_all_tickets_rejected_gives_no_progress_and_no_crash():
    items = (Issue(key="A", status="Rejected", points=3.0), Issue(key="B", status="Won't do", points=1.0))
    a = ev.analyse(items)
    assert a.n_atoms == 0 and a.n_excluded == 2 and math.isnan(a.progress) and ev.check_consistency(a) == []


def test_graph_marks_rejected_nodes_as_not_measurable():
    g = ev.analyse(TREE).tree
    by = {k: (p, ign) for k, p, ign in zip(g.keys, g.progress.tolist(), g.ignored.tolist())}
    assert by["S2"][1] and math.isnan(by["S2"][0]) and by["E2"][1] and math.isnan(by["E2"][0]) and by["S4a"][1] and by["S3a"][1]
    assert by["E1"][0] == pytest.approx(1.0) and by["S1"][1] is False


# ---------------------------------------------------------------- Teilprojekt

def test_a_subproject_is_a_standalone_dataset_by_hand(mini):
    e1 = ev.analyse(A.scope_issues(mini, "E1"), ev.Settings(root="E1"))
    assert (e1.n_atoms, e1.weight) == (3, 5.0) and e1.progress == pytest.approx(4 / 5)             # S1 (3) und die Sub-Tasks T1, T2 (je 1)
    e2 = ev.analyse(A.scope_issues(mini, "E2"), ev.Settings(root="E2"))
    assert (e2.n_atoms, e2.weight, e2.n_unestimated) == (2, 4.0, 1) and e2.progress == pytest.approx(0.4)      # S4 wiegt den Median des Teilbaums (2), nicht den des ganzen Plans (2.5)
    assert e2.tree.keys[0] == "E2" and e2.credits == {"To Do": 0.0, "In Review": 0.8}                              # nur die Status des Teilbaums


def test_subproject_equals_the_full_analysis_restricted_to_its_atoms_when_everything_is_estimated():
    for seed in range(12):
        project = tuple(dataclasses.replace(t, points=t.points if t.points is not None else 1.0) for t in random_project(seed))
        full = ev.analyse(project)
        for root, _ in A.root_choices(project):
            sub = ev.analyse(A.scope_issues(project, root), ev.Settings(root=root))
            keys = A.subtree_keys(project, root)
            mine = [k for k, i in enumerate(full.atoms) if project[i].key in keys]
            assert sub.weight == pytest.approx(float(full.w[mine].sum()), abs=1e-9)
            assert sub.progress == pytest.approx(float((full.w[mine] * full.c[mine]).sum() / full.w[mine].sum())) if len(mine) and full.w[mine].sum() > 0 else math.isnan(sub.progress)


# ---------------------------------------------------------------- Eigenschaften über Zufallsprojekte

@pytest.mark.parametrize("seed", range(30))
def test_random_projects_pass_the_internal_consistency_check_on_every_level(seed):
    project = random_project(seed, n_epics=2 + seed % 6)
    for level in range(1, 6):
        a = ev.analyse(project, ev.Settings(level=level, unest_rule=C.UNEST_RULES[seed % 3]))
        assert ev.check_consistency(a) == [], (seed, level)
        assert math.isnan(a.progress) or 0.0 <= a.progress <= 1.0
        assert a.progress_done <= a.progress + 1e-12 or math.isnan(a.progress)                 # fertig zählt 100 %: nie mehr als der gewichtete Fortschritt


def test_consistency_check_reports_a_broken_analysis(mini):
    a = ev.analyse(mini)
    broken = dataclasses.replace(a, progress=1.5, n_atoms=a.n_atoms + 1)
    problems = ev.check_consistency(broken)
    assert any("außerhalb von 0 bis 100 %" in p for p in problems) and any("Tickets, erwartet" in p for p in problems) and any("Beiträge der Gruppen" in p for p in problems)
    assert any("Gruppengewichte" in p for p in ev.check_consistency(dataclasses.replace(a, weight=a.weight + 1)))


def test_unestimated_note():
    assert ev.unestimated_note(0, 0)[0] == "warning" and ev.unestimated_note(0, 5) == ("success", "Alle 5 Tickets haben Story Points.")
    kind, text = ev.unestimated_note(1, 10)
    assert kind == "info" and "1 von 10 Tickets (10.0 %)" in text and "Median" in text
    assert ev.unestimated_note(2, 10)[0] == "warning"                                      # ab 20 % ein Warnhinweis
    assert "Regel: H. als 1 Story Point" in ev.unestimated_note(1, 10, C.UNEST_ONE)[1] and "im Fortschritt nicht auf" not in ev.unestimated_note(1, 10, C.UNEST_ONE)[1]
    assert "Regel: I. nicht zählen" in ev.unestimated_note(1, 10, C.UNEST_IGNORE)[1] and "im Fortschritt nicht auf" in ev.unestimated_note(1, 10, C.UNEST_IGNORE)[1]


def test_every_rule_changes_weight_and_progress_by_hand(mini):
    expected = {                                       # Regel: (Gesamtgewicht, angerechnet); Gutschriften S1 1, S3 0, S4 0.8, B1 1, T1 1, T2 0
        C.UNEST_MEDIAN: (10.5, 7.0), C.UNEST_PLAN: (10.5, 7.0), C.UNEST_TYPE: (10.5, 7.0), C.UNEST_SIBLINGS: (10.0, 6.6), C.UNEST_TEAM: (12.0, 7.6), C.UNEST_CHAIN: (12.0, 7.6),
        C.UNEST_ONE: (9.0, 5.8), C.UNEST_IGNORE: (6.0, 4.0)}
    assert list(expected) == list(C.UNEST_RULES)
    for rule, (weight, credited) in expected.items():
        a = ev.analyse(mini, ev.Settings(unest_rule=rule))
        assert a.weight == pytest.approx(weight) and a.progress == pytest.approx(credited / weight) and a.n_unestimated == 3 and ev.check_consistency(a) == [], rule


def test_a_subproject_uses_the_whole_plan_for_the_plan_rules(mini):
    sub = A.scope_issues(mini, "E2")
    own = ev.analyse(sub, ev.Settings(root="E2", unest_rule=C.UNEST_PLAN))                       # ohne Plan: nur der Teilbaum (S3 = 2)
    with_plan = ev.analyse(sub, ev.Settings(root="E2", unest_rule=C.UNEST_PLAN), mini)         # Stufe 1 des ganzen Plans: Median von 3 und 2 = 2.5
    assert own.weight == 4.0 and with_plan.weight == 4.5 and with_plan.plan == tuple(mini)
    assert ev.analyse(sub, ev.Settings(root="E2")).plan == tuple(sub)


def test_every_sub_task_rule_by_hand(mini):
    # a: S2 zählt durch T1 (Done) und T2; b: T1 und T2 teilen sich die 5 Story Points von S2; c: S2 zählt selbst (In Progress, 5), T1 und T2 bleiben außen vor
    expected = {C.SUB_RULE: (6, 10.5, 7.0), C.SUB_SHARE: (6, 13.5, 8.5), C.SUB_SELF: (5, 14.0, 6.4)}          # (zählende Tickets, Gesamtgewicht, angerechnet); bei c wiegt S4 den Median 3 von S1, S2, S3
    assert list(expected) == list(C.SUB_RULES)
    for rule, (n, weight, credited) in expected.items():
        a = ev.analyse(mini, ev.Settings(sub_rule=rule))
        assert (a.n_atoms, a.weight) == (n, pytest.approx(weight)) and a.progress == pytest.approx(credited / weight) and ev.check_consistency(a) == [], rule
    c = ev.analyse(mini, ev.Settings(sub_rule=C.SUB_SELF))
    assert [mini[i].key for i in c.atoms] == ["S1", "S2", "S3", "S4", "B1"] and c.progress_done == pytest.approx(4 / 14) and c.progress_count == pytest.approx(2 / 5)
    with pytest.raises(KeyError):
        ev.analyse(mini, ev.Settings(sub_rule="Unsinn"))


def test_the_sub_task_rule_c_keeps_the_rejected_logic():
    a = ev.analyse(TREE, ev.Settings(sub_rule=C.SUB_SELF))
    # S3 zählt selbst (4, In Progress), seine Sub-Tasks bleiben außen vor; S2 und S4 (unter dem zurückgewiesenen E2) sind die zurückgewiesenen Blätter
    assert [TREE[i].key for i in a.atoms] == ["S1", "S3", "X"] and [TREE[i].key for i in a.rejected_atoms] == ["S2", "S4"]
    assert a.weight == 9.0 and a.progress == pytest.approx((2 * 1.0 + 4 * 0.0 + 3 * 0.8) / 9)


def test_credit_text_shows_one_decimal_and_two_when_needed():
    assert [ev.credit_text(c) for c in (0.8, 0.85, 1.0, 0.9, 0.125, 0.05)] == ["0.8", "0.85", "1.0", "0.9", "0.12", "0.05"]


@pytest.mark.parametrize("seed", range(4))
def test_headline_equals_the_numbers_of_the_full_analysis_for_every_rule(seed):
    """Der Vergleich der Regeln rechnet mit `headline` ohne Gruppen und Graph; die vier Zahlen müssen genau die von `analyse` sein."""
    issues = random_project(seed)
    for unest_rule in C.UNEST_RULES:
        for sub_rule in C.SUB_RULES:
            settings = ev.Settings(unest_rule=unest_rule, sub_rule=sub_rule)
            a = ev.analyse(issues, settings)
            progress, weight, n_unestimated, n_atoms = ev.headline(issues, settings)
            assert (weight, n_unestimated, n_atoms) == (a.weight, a.n_unestimated, a.n_atoms)
            assert progress == a.progress or (math.isnan(progress) and math.isnan(a.progress))


@pytest.mark.parametrize("seed", range(3))
def test_shared_intermediate_results_do_not_change_any_number(seed):
    """Mit dem Zwischenspeicher der Analyse (`ctx`) kommt dasselbe heraus wie bei jedem Aufruf allein: Baumreihenfolge, Tiefen, Ketten und die Zahlen der Regelvergleiche."""
    issues = random_project(seed)
    ctx: dict = {}
    assert A.tree_order(issues, C.ROOT_ALL, ctx) == A.tree_order(issues) and A.tree_order(issues, C.ROOT_ALL, ctx) is A.tree_order(issues, C.ROOT_ALL, ctx)
    assert A.tree_depths(issues, ctx) == A.tree_depths(issues) and A.hierarchy_chains(issues, ctx) == A.hierarchy_chains(issues)
    a = ev.analyse(issues)
    for rule in C.UNEST_RULES:
        alone = ev.headline(issues, dataclasses.replace(a.settings, unest_rule=rule), a.plan)
        shared = ev.headline(issues, dataclasses.replace(a.settings, unest_rule=rule), a.plan, a.ctx)
        assert shared[1:] == alone[1:] and (shared[0] == alone[0] or (math.isnan(shared[0]) and math.isnan(alone[0])))


def test_an_intermediate_store_of_other_tickets_is_refused():
    ctx: dict = {}
    ev.headline(random_project(0), ev.Settings(), None, ctx)
    with pytest.raises(ValueError):
        ev.headline(random_project(0, n_epics=2), ev.Settings(), None, ctx)


def test_statuses_without_a_known_meaning_are_reported_with_tickets_and_weight():
    items = (Issue(key="E", type="Epic"), Issue(key="A", parent="E", status="Freigegeben", points=3.0), Issue(key="B", parent="E", status="Freigegeben", points=2.0),
             Issue(key="C", parent="E", status="Phase 2", points=1.0), Issue(key="D", parent="E", status="In Arbeit", points=4.0), Issue(key="F", parent="E", status="Done", points=5.0))
    a = ev.analyse(items)
    assert ev.unrecognized_statuses(items, a) == [("Freigegeben", 2, 5.0), ("Phase 2", 1, 1.0)]
    text = ev.unrecognized_note(ev.unrecognized_statuses(items, a), a.weight)
    assert "3 zählende Tickets (40.0 % des Gewichts)" in text and "„Freigegeben“ (2)" in text and "„Phase 2“ (1)" in text and "Gewichte der Status" in text
    assert ev.unrecognized_note([], a.weight) == ""


def test_a_status_whose_weight_was_changed_in_the_table_is_no_longer_reported():
    items = (Issue(key="A", status="Freigegeben", points=3.0), Issue(key="B", status="Phase 2", points=1.0))
    a = ev.analyse(items, ev.Settings(overrides=(("Freigegeben", 1.0),)))
    assert [row[0] for row in ev.unrecognized_statuses(items, a)] == ["Phase 2"]


def test_the_note_names_at_most_six_statuses_and_counts_the_rest():
    rows = [(f"S{n}", 1, float(10 - n)) for n in range(8)]
    text = ev.unrecognized_note(rows, 100.0)
    assert "„S5“ (1)" in text and "„S6“" not in text and "und 2 weitere" in text
