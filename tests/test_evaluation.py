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
    # Gewichte 3, 5, 2, 2,5 (Median), 1; Gutschriften 1, 0, 0, 0,8 (In Review), 1
    assert (a.n_atoms, a.weight, a.n_unestimated, a.n_outside, a.n_excluded) == (5, 13.5, 1, 0, 0)
    assert a.progress == pytest.approx(6 / 13.5) and a.progress_done == pytest.approx(4 / 13.5) and a.progress_count == pytest.approx(2 / 5)
    assert a.credits == {"In Progress": 0.0, "To Do": 0.0, "In Review": 0.8, "Done": 1.0}
    assert ev.check_consistency(a) == [] and [mini[i].key for i in a.atoms] == ["S1", "S2", "S3", "S4", "B1"]


def test_changed_status_weights_change_the_progress_by_hand(mini):
    a = ev.analyse(mini, ev.Settings(overrides=(("In Review", 0.5), ("In Progress", 0.4))))
    assert a.progress == pytest.approx((3 + 5 * 0.4 + 0 + 2.5 * 0.5 + 1) / 13.5)
    assert a.progress_done == pytest.approx(4 / 13.5)                                # „nur Done“ hängt nicht von den Gewichten ab


def test_group_by_dimension_is_part_of_the_analysis(mini):
    a = ev.analyse(mini, ev.Settings(dimension=C.DIM_EPIC))
    assert a.stats.labels == ("E1: Epic A", "E2: Epic B", "(ohne Epic)") and a.stats.progress.tolist() == pytest.approx([3 / 8, 2 / 4.5, 1.0])
    assert ev.analyse(mini, ev.Settings(dimension=C.DIM_ALL)).stats.labels == ("Gesamtes Projekt",)


def test_status_list_orders_by_credit_then_not_started_first(mini):
    assert ev.status_list(mini) == ["To Do", "In Progress", "In Review", "Done"]
    assert ev.status_list(()) == []


def test_formatting_helpers():
    assert ev.de(1234.5678, 2) == "1234,57" and ev.de(0.5, sign=True) == "+0,5" and ev.de(-0.5, sign=True) == "-0,5" and ev.pct(0.4444) == "44,4 %"


# ---------------------------------------------------------------- Zurückgewiesene Tickets

def test_progress_without_the_rejected_by_hand():
    a = ev.analyse(TREE)
    assert (a.n_atoms, a.weight, a.n_excluded) == (3, 9.0, 2)                       # S1, S3, X; S2 und S4 (unter dem zurückgewiesenen E2) fehlen
    assert [TREE[i].key for i in a.rejected_atoms] == ["S2", "S4"]
    assert a.progress == pytest.approx((2 * 1.0 + 4 * 0.0 + 3 * 0.8) / 9) and ev.check_consistency(a) == []          # 4,4 / 9
    assert a.progress_count == pytest.approx(1 / 3)                                    # nur S1 ist erledigt


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
    assert by["E1"][0] == pytest.approx(2 / 6) and by["S1"][1] is False


# ---------------------------------------------------------------- Zeitraum

def test_period_restricts_the_basis_and_the_median_by_hand(mini):
    a = ev.analyse(mini, ev.Settings(sprint_from="Sprint 2"))
    # im Zeitraum S2 (5), S4 (ungeschätzt: Median von 5 und 1 = 3), B1 (1); S1 (Sprint 1) und S3 (kein Sprint) liegen außerhalb
    assert (a.n_atoms, a.n_outside, a.weight) == (3, 2, 9.0)
    assert a.progress == pytest.approx((0 * 5 + 0.8 * 3 + 1 * 1) / 9) and ev.check_consistency(a) == []
    with_none = ev.analyse(mini, ev.Settings(sprint_from="Sprint 2", sprint_to="Sprint 2", include_no_sprint=True))
    assert (with_none.n_atoms, with_none.n_outside) == (4, 1)


def test_an_empty_period_gives_no_progress_and_no_crash(mini):
    a = ev.analyse(mini, ev.Settings(sprint_from="Sprint 2", sprint_to="Sprint 1"))
    assert a.n_atoms == 0 and a.n_outside == 5 and math.isnan(a.progress) and ev.check_consistency(a) == []


def test_period_and_rejected_combine():
    items = (Issue(key="A", points=2.0, status="Done", sprints=("S1",)), Issue(key="B", points=3.0, status="Rejected", sprints=("S1",)), Issue(key="C", points=4.0, status="Rejected", sprints=("S2",)),
             Issue(key="D", points=1.0, status="To Do", sprints=("S2",)))
    a = ev.analyse(items, ev.Settings(sprint_from="S2"))
    assert [items[i].key for i in a.atoms] == ["D"] and [items[i].key for i in a.rejected_atoms] == ["C"] and a.n_outside == 1


# ---------------------------------------------------------------- Teilprojekt

def test_a_subproject_is_a_standalone_dataset_by_hand(mini):
    e1 = ev.analyse(A.scope_issues(mini, "E1"), ev.Settings(root="E1"))
    assert (e1.n_atoms, e1.weight) == (2, 8.0) and e1.progress == pytest.approx(3 / 8)
    e2 = ev.analyse(A.scope_issues(mini, "E2"), ev.Settings(root="E2"))
    assert (e2.n_atoms, e2.weight, e2.n_unestimated) == (2, 4.0, 1) and e2.progress == pytest.approx(0.4)      # S4 wiegt den Median des Teilbaums (2), nicht den des ganzen Plans (2,5)
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
def test_random_projects_pass_the_internal_consistency_check_in_every_dimension(seed):
    project = random_project(seed, n_epics=2 + seed % 6)
    for dim in C.DIMENSIONS:
        a = ev.analyse(project, ev.Settings(dimension=dim, level=1 + seed % 3))
        assert ev.check_consistency(a) == [], (seed, dim)
        assert math.isnan(a.progress) or 0.0 <= a.progress <= 1.0
        assert a.progress_done <= a.progress + 1e-12 or math.isnan(a.progress)                 # fertig zählt 100 %: nie mehr als der gewichtete Fortschritt


@pytest.mark.parametrize("seed", range(10))
def test_random_projects_with_a_period_pass_the_check(seed):
    project = random_project(seed)
    order = A.sprint_order(project)
    for lo, hi in ((order[0], order[-1]), (order[len(order) // 2], ""), ("", order[len(order) // 2])):
        a = ev.analyse(project, ev.Settings(sprint_from=lo, sprint_to=hi))
        assert ev.check_consistency(a) == [] and a.n_atoms + a.n_outside == len([i for i in A.select_atoms(project) if i not in A.rejected_indices(project)])


def test_consistency_check_reports_a_broken_analysis(mini):
    a = ev.analyse(mini)
    broken = dataclasses.replace(a, progress=1.5, n_atoms=a.n_atoms + 1)
    problems = ev.check_consistency(broken)
    assert any("außerhalb von 0 bis 100 %" in p for p in problems) and any("Tickets, erwartet" in p for p in problems) and any("Beiträge der Gruppen" in p for p in problems)
    assert any("Gruppengewichte" in p for p in ev.check_consistency(dataclasses.replace(a, weight=a.weight + 1)))


def test_unestimated_note():
    assert ev.unestimated_note(0, 0)[0] == "warning" and ev.unestimated_note(0, 5) == ("success", "Alle 5 Tickets sind geschätzt.")
    kind, text = ev.unestimated_note(1, 10)
    assert kind == "info" and "1 von 10 Tickets (10,0 %)" in text and "Median" in text
    assert ev.unestimated_note(2, 10)[0] == "warning"                                      # ab 20 % ein Warnhinweis
