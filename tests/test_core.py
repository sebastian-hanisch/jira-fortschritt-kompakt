"""Kern an der Mini-Instanz (tests/conftest.py), alle Zahlen von Hand: Atome, Gewichte, Gruppen, Teilprojekt, Zeitraum, Hierarchiestufen, Teilprojektbaum."""

import numpy as np
import pytest

import jira_constants as C
import jira_core as A
from jira_core import Issue

KEYS = ["E1", "E2", "S1", "S2", "S3", "S4", "B1", "T1", "T2"]


def keys(mini, found):
    return [mini[i].key for i in found]


def test_atoms_are_the_leaves_of_the_ticket_tree(mini):
    assert keys(mini, A.select_atoms(mini)) == ["S1", "S3", "S4", "B1", "T1", "T2"]            # S2 hat Sub-Tasks und zählt durch sie; E1 und E2 sind Epics
    layers = (Issue(key="I", type="Initiative"), Issue(key="E", type="Epic", parent="I"), Issue(key="S", parent="E"), Issue(key="K", type="Thema"),
              Issue(key="U", type="Teilaufgabe", is_subtask=True, parent="S"), Issue(key="T", type="Task"))
    assert [layers[i].key for i in A.select_atoms(layers)] == ["U", "T"]
    assert [layers[i].key for i in A.select_atoms(layers, skip=frozenset({4}))] == ["S", "T"]          # ist die einzige Sub-Task zurückgewiesen, ist die Story selbst ein Blatt
    assert A.select_atoms(()) == []


def test_unestimated_atoms_weigh_the_median_of_their_own_level(mini):
    atoms = A.select_atoms(mini)
    assert A.tree_depths(mini) == [0, 0, 1, 1, 1, 1, 0, 2, 2]                                   # E1, E2, S1, S2, S3, S4, B1 (ohne Eltern: Stufe 0), T1, T2
    # Stufe 1 (S1 = 3, S3 = 2, S4 ungeschätzt): Median 2,5; B1 steht auf Stufe 0; die Sub-Tasks auf Stufe 2 haben keine geschätzten Tickets: 1
    assert A.atom_weights(mini, atoms).tolist() == [3.0, 2.0, 2.5, 1.0, 1.0, 1.0]
    assert A.atom_weights(mini, [4, 5]).tolist() == [2.0, 2.0]                                   # nur S3 (2) und S4: Median der Stufe aus den übergebenen Atomen
    assert A.atom_weights(mini, atoms, basis=[2]).tolist() == [3.0, 2.0, 3.0, 1.0, 1.0, 1.0]       # Grundlage nur S1: S4 wiegt 3
    assert A.atom_weights(mini, atoms, basis=[]).tolist() == [3.0, 2.0, 1.0, 1.0, 1.0, 1.0]
    assert A.atom_weights(mini, []).tolist() == []


def test_the_rule_for_unestimated_atoms_sets_their_weight(mini):
    atoms = A.select_atoms(mini)
    assert A.atom_weights(mini, atoms, C.UNEST_ONE).tolist() == [3.0, 2.0, 1.0, 1.0, 1.0, 1.0]
    assert A.atom_weights(mini, atoms, C.UNEST_IGNORE).tolist() == [3.0, 2.0, 0.0, 1.0, 0.0, 0.0]
    assert A.atom_weights(mini, atoms, C.UNEST_MEDIAN).tolist() == [3.0, 2.0, 2.5, 1.0, 1.0, 1.0]
    with pytest.raises(KeyError):
        A.atom_weights(mini, atoms, "Unsinn")


def test_the_median_is_taken_per_level_not_over_the_whole_tree():
    items = (Issue(key="E", type="Epic"), Issue(key="S1", parent="E", points=8.0), Issue(key="S2", parent="E", points=2.0), Issue(key="S3", parent="E"),
             Issue(key="U1", type="Sub-task", is_subtask=True, parent="S1", points=1.0), Issue(key="U2", type="Sub-task", is_subtask=True, parent="S1"),
             Issue(key="U3", type="Sub-task", is_subtask=True, parent="S1", points=3.0))
    atoms = A.select_atoms(items)
    assert [items[i].key for i in atoms] == ["S2", "S3", "U1", "U2", "U3"]
    assert A.atom_weights(items, atoms).tolist() == [2.0, 2.0, 1.0, 2.0, 3.0]          # S3: Median der Stufe 1 (nur S2, da S1 Sub-Tasks hat) = 2; U2: Median von 1 und 3 = 2


def test_group_by_level_one_by_hand(mini):
    atoms = A.select_atoms(mini)
    w = A.atom_weights(mini, atoms)
    c = np.array([1.0, 0.0, 0.8, 1.0, 1.0, 0.0])
    done = np.array([True, False, False, True, True, False])
    stats = A.aggregate(A.assign_groups(mini, atoms, 1), w, c, done, np.array([False, False, True, False, True, True]))
    assert stats.labels == ("B1", "E1: Epic A", "E2: Epic B")
    assert stats.weight.tolist() == [1.0, 5.0, 4.5] and stats.credited.tolist() == pytest.approx([1.0, 4.0, 2.0])          # E1: S1 (3) + T1 (1) + T2 (1)
    assert stats.progress.tolist() == pytest.approx([1.0, 4 / 5, 2 / 4.5]) and stats.unestimated.tolist() == [0.0, 2.0, 1.0]
    assert stats.done_weight.tolist() == [1.0, 4.0, 0.0] and stats.count.tolist() == [1.0, 3.0, 2.0]


def test_group_by_level_two_by_hand(mini):
    atoms = A.select_atoms(mini)
    w = A.atom_weights(mini, atoms)
    c = np.array([1.0, 0.0, 0.8, 1.0, 1.0, 0.0])
    stats = A.aggregate(A.assign_groups(mini, atoms, 2), w, c, np.zeros(6, dtype=bool), np.zeros(6, dtype=bool))
    assert stats.labels == ("S1", "S2", "S3", "S4", "(keine Stufe 2)")                         # S2 fasst T1 und T2 zusammen; B1 steht auf Stufe 1
    assert stats.weight.tolist() == [3.0, 2.0, 2.0, 2.5, 1.0] and stats.credited.tolist() == pytest.approx([3.0, 1.0, 0.0, 2.0, 1.0])
    assert stats.weight.sum() == pytest.approx(w.sum())                                         # die Summe über alle Gruppen bleibt die Gesamtsumme


def test_every_level_assigns_each_atom_exactly_once(mini):
    atoms = A.select_atoms(mini)
    for level in range(1, 6):
        assign = A.assign_groups(mini, atoms, level)
        assert assign.atom.tolist() == list(range(len(atoms))) and assign.share.tolist() == [1.0] * len(atoms)
    assert A.assign_groups(mini, [], 1).labels == ()


def test_natural_key_sorts_numbers_as_numbers_and_empty_groups_last():
    assert sorted(["Sprint 10", "Sprint 2", "(ohne Sprint)", "Sprint 1"], key=A.natural_key) == ["Sprint 1", "Sprint 2", "Sprint 10", "(ohne Sprint)"]


# ---------------------------------------------------------------- Teilprojekt

def test_subtree_and_scope_make_the_root_a_standalone_dataset(mini):
    assert A.subtree_keys(mini, "E1") == {"E1", "S1", "S2", "T1", "T2"}
    scoped = A.scope_issues(mini, "E2")
    assert [t.key for t in scoped] == ["E2", "S3", "S4"] and scoped[0].parent == ""
    assert A.scope_issues(mini, C.ROOT_ALL) == tuple(mini)
    story = A.scope_issues(mini, "S2")
    assert [t.key for t in story] == ["S2", "T1", "T2"] and story[0].parent == "" and A.level_labels(story, [1, 2], 1) == ["S2", "S2"]            # die Wurzel steht auf Stufe 1
    with pytest.raises(ValueError):
        A.subtree_keys(mini, "gibt-es-nicht")


def test_subtree_survives_a_cycle():
    loop = (Issue(key="A", parent="C"), Issue(key="B", parent="A"), Issue(key="C", parent="B"))
    assert A.subtree_keys(loop, "A") == {"A", "B", "C"}


def test_root_choices_are_containers_in_tree_order_with_their_depth(mini):
    assert A.root_choices(mini) == [("E1", 0), ("S2", 1), ("E2", 0)]


def test_tree_order_is_depth_first_and_scoped(mini):
    assert [(mini[i].key, d) for i, d, _ in A.tree_order(mini)] == [("E1", 0), ("S1", 1), ("S2", 1), ("T1", 2), ("T2", 2), ("E2", 0), ("S3", 1), ("S4", 1), ("B1", 0)]
    assert [(mini[i].key, d) for i, d, _ in A.tree_order(mini, "S2")] == [("S2", 0), ("T1", 1), ("T2", 1)]
    with pytest.raises(ValueError):
        A.tree_order(mini, "X")


def test_tree_order_lists_every_ticket_once_even_in_a_cycle():
    loop = (Issue(key="A", parent="B"), Issue(key="B", parent="A"), Issue(key="C", parent="C"))
    assert sorted(i for i, _, _ in A.tree_order(loop)) == [0, 1, 2]


# ---------------------------------------------------------------- Hierarchiestufen

def test_levels_by_hand(mini):
    atoms = A.select_atoms(mini)
    assert A.level_labels(mini, atoms, 1) == ["E1: Epic A", "E2: Epic B", "E2: Epic B", "B1", "E1: Epic A", "E1: Epic A"]
    assert A.level_labels(mini, atoms, 2) == ["S1", "S3", "S4", "(keine Stufe 2)", "S2", "S2"]
    assert A.level_labels(mini, atoms, 3) == ["(keine Stufe 3)"] * 4 + ["T1", "T2"]
    assert A.assign_groups(mini, atoms, 1).labels == ("B1", "E1: Epic A", "E2: Epic B")
    assert A.level_labels((), [], 1) == []


def test_summary_level_is_always_the_tickets_directly_below_the_root(mini):
    assert A.summary_level(C.ROOT_ALL) == 1 and A.summary_level("E1") == 2 and A.summary_level("S2") == 2
    scoped = A.scope_issues(mini, "E1")
    atoms = A.select_atoms(scoped)
    assert sorted(set(A.level_labels(scoped, atoms, A.summary_level("E1")))) == ["S1", "S2"]            # die Kinder von E1; T1 und T2 zählen zu S2
    assert sorted(set(A.level_labels(mini, A.select_atoms(mini), A.summary_level(C.ROOT_ALL)))) == ["B1", "E1: Epic A", "E2: Epic B"]         # die obersten Tickets


# ---------------------------------------------------------------- Teilprojektbaum

def _graph(mini, **kw):
    atoms = A.select_atoms(mini)
    w = A.atom_weights(mini, atoms)
    c = np.array([1.0, 0.0, 0.8, 1.0, 1.0, 0.0])
    credit_of = {"Done": 1.0, "In Progress": 0.0, "To Do": 0.0, "In Review": 0.8}
    return A.tree_graph(mini, atoms, w, c, credit_of, **kw)


def test_graph_nodes_carry_the_sum_of_their_atoms_by_hand(mini):
    g = _graph(mini)
    assert g.keys == ("Projekt", "E1", "S1", "S2", "T1", "T2", "E2", "S3", "S4", "B1") and g.n_total == 10 and g.shown_depth == 3
    by = {k: (w, p, atom, leaf) for k, w, p, atom, leaf in zip(g.keys, g.weight.tolist(), g.progress.tolist(), g.is_atom.tolist(), g.is_leaf.tolist())}
    assert by["Projekt"][:2] == pytest.approx((10.5, 7 / 10.5)) and by["E1"][:2] == pytest.approx((5.0, 4 / 5)) and by["E2"][:2] == pytest.approx((4.5, 2 / 4.5))
    assert by["S2"] == (2.0, 0.5, False, False)                                          # S2 hat Sub-Tasks: kein Atom, trägt die Summe seiner Sub-Tasks (1 von 2)
    assert by["T1"] == (1.0, 1.0, True, True) and by["T2"] == (1.0, 0.0, True, True)
    assert g.parent.tolist() == [-1, 0, 1, 1, 3, 3, 0, 6, 6, 0] and g.x.tolist() == [0, 1, 2, 2, 3, 3, 1, 2, 2, 1]
    assert not g.ignored.any() and not g.hidden.any()


def test_graph_of_a_subproject_starts_at_its_root(mini):
    scoped = A.scope_issues(mini, "E2")
    atoms = A.select_atoms(scoped)
    g = A.tree_graph(scoped, atoms, A.atom_weights(scoped, atoms), np.array([0.0, 0.8]), {"To Do": 0.0, "In Review": 0.8}, "E2")
    assert g.keys == ("E2", "S3", "S4") and g.parent.tolist() == [-1, 0, 0] and g.weight.tolist() == [4.0, 2.0, 2.0] and g.progress[0] == pytest.approx(0.4)


def test_graph_beyond_the_limit_draws_the_heaviest_nodes_and_one_rest_node_per_parent(mini):
    g = _graph(mini, max_nodes=5)
    # Projekt, E1 (5.0), S1 (3.0); was bei E1 fehlt (S2 mit T1 und T2), und was beim Projekt fehlt (E2 mit S3 und S4, B1), steht je in einem Sammelknoten
    assert g.keys == ("Projekt", "E1", "S1", "Rest", "Rest") and g.is_rest.tolist() == [False, False, False, True, True] and g.n_total == 10 and g.shown_depth == 2
    assert g.titles[3:] == ("3 Tickets zusammengefasst", "4 Tickets zusammengefasst") and g.parent.tolist() == [-1, 0, 1, 1, 0]
    assert g.weight.tolist() == pytest.approx([10.5, 5.0, 3.0, 2.0, 5.5])                  # die Summe der gezeichneten Blätter ist das Gesamtgewicht
    assert g.progress.tolist() == pytest.approx([7 / 10.5, 0.8, 1.0, 0.5, 3 / 5.5])
    assert g.hidden.tolist() == [4, 3, 0, 0, 0] and g.is_leaf.tolist() == [False, False, True, True, True]
    assert g.y.tolist() == pytest.approx([1.25, 0.5, 0.0, 1.0, 2.0]) and g.x.tolist() == [0, 1, 2, 2, 1]


def test_the_budget_counts_rest_nodes_and_light_nodes_may_still_fit_after_a_heavy_one_did_not():
    parent = np.array([-1, 0, 0, 0, 1, 1])                 # 0 hat die Kinder 1, 2, 3; 1 hat die Kinder 4 und 5
    weight = np.array([10.0, 6.0, 3.0, 1.0, 4.0, 2.0])
    order, omitted = A.heaviest_nodes(parent, weight, limit=10)
    assert order == [0, 1, 4, 5, 2, 3] and omitted == {}
    order, omitted = A.heaviest_nodes(parent, weight, limit=5)         # 0 mit Rest, 1 (2 Plätze), 4; dann passt 5 noch hinein, weil es den Rest von 1 überflüssig macht; 2 und 3 stehen im Rest von 0
    assert order == [0, 1, 4, 5] and omitted == {0: [2, 3]}
    order, omitted = A.heaviest_nodes(parent, weight, limit=4)         # nur 0 mit Rest und 1 mit Rest: weder 4, 5 noch 2 oder 3 haben noch Platz
    assert order == [0, 1] and omitted == {0: [2, 3], 1: [4, 5]}
    order, omitted = A.heaviest_nodes(parent, weight, limit=1)
    assert order == [0] and omitted == {0: [1, 2, 3]}
    assert A.heaviest_nodes(np.array([-1]), np.array([5.0]), limit=3) == ([0], {})


def test_a_flat_plan_beyond_the_limit_keeps_all_of_its_weight_between_the_drawn_nodes_and_the_rest_node():
    issues = tuple(Issue(key=f"P-{n}", status="Done" if n % 2 else "Backlog", points=float(1 + n % 7)) for n in range(600))
    atoms = A.select_atoms(issues)
    w = A.atom_weights(issues, atoms)
    c = np.array([1.0 if issues[i].status == "Done" else 0.0 for i in atoms])
    g = A.tree_graph(issues, atoms, w, c, {"Done": 1.0, "Backlog": 0.0})
    assert len(g.keys) <= C.GRAPH_MAX_NODES and g.keys.count("Rest") == 1 and g.is_rest.sum() == 1
    drawn_leaves = g.weight[(g.parent == 0) & ~g.is_rest]
    assert float(drawn_leaves.sum() + g.weight[g.is_rest][0]) == pytest.approx(float(w.sum())) and g.weight[0] == pytest.approx(float(w.sum()))
    omitted_weights = sorted((issues[i].points for i in atoms), reverse=True)[len(drawn_leaves):]
    assert drawn_leaves.min() >= max(omitted_weights)                                      # gezeichnet sind die schwersten, im Rest die leichteren
    assert g.hidden[0] == 600 - (len(g.keys) - 2)                                         # alle nicht gezeichneten Tickets stehen im Rest



def test_graph_marks_excluded_nodes_as_not_measurable(mini):
    g = _graph(mini, excluded=frozenset({3}))
    assert g.ignored.tolist() == [False, False, False, True, False, False, False, False, False, False] and np.isnan(g.progress[3])


def test_graph_survives_a_cycle():
    loop = (Issue(key="A", parent="B", points=1.0), Issue(key="B", parent="A", points=1.0))
    assert A.select_atoms(loop) == []                                                  # in einem Kreis hat kein Ticket kein Kind: kein Blatt
    atoms = [0, 1]
    g = A.tree_graph(loop, atoms, A.atom_weights(loop, atoms), np.array([1.0, 0.0]), {"To Do": 0.0})
    assert len(g.keys) == 3 and g.weight[0] == 2.0


# ---------------------------------------------------------------- Gesamtfortschritt

def test_overall_by_hand_and_without_weight():
    assert A.overall(np.array([3.0, 1.0]), np.array([1.0, 0.0]), np.array([True, False])) == pytest.approx((0.75, 0.75))
    p_w, p_d = A.overall(np.array([]), np.array([]), np.array([], dtype=bool))
    assert np.isnan(p_w) and np.isnan(p_d)
    p_w, p_d = A.overall(np.array([0.0, 0.0]), np.array([1.0, 1.0]), np.array([True, False]))
    assert np.isnan(p_w) and np.isnan(p_d)


def test_parent_root_goes_one_level_up_to_a_ticket_that_can_be_a_root(mini):
    assert A.parent_root(mini, "S2") == "E1"                 # die Story mit Sub-Tasks steht unter E1
    assert A.parent_root(mini, "E1") == C.ROOT_ALL           # E1 hat keine Eltern: das ganze Projekt
    assert A.parent_root(mini, C.ROOT_ALL) == C.ROOT_ALL
    deep = (Issue(key="I", type="Initiative"), Issue(key="E", type="Epic", parent="I"), Issue(key="S", parent="E"), Issue(key="U", type="Sub-task", is_subtask=True, parent="S"),
            Issue(key="O", parent="Fremd"), Issue(key="P", parent="O"))
    assert [A.parent_root(deep, k) for k in ("S", "E", "I", "O")] == ["E", "I", C.ROOT_ALL, C.ROOT_ALL]          # „Fremd“ steht nicht in den Daten


def test_root_for_click_accepts_containers_and_the_whole_project_only(mini):
    assert A.root_for_click(mini, "E2") == "E2" and A.root_for_click(mini, "S2") == "S2" and A.root_for_click(mini, C.ROOT_ALL) == C.ROOT_ALL
    assert A.root_for_click(mini, "S1") is None and A.root_for_click(mini, "T1") is None and A.root_for_click(mini, "Projekt") is None and A.root_for_click(mini, "gibt-es-nicht") is None          # Blätter bewirken nichts


RULE_ITEMS = (
    Issue(key="E1", type="Epic"), Issue(key="E2", type="Epic"),
    Issue(key="A1", type="Story", parent="E1", points=8.0, team="Alpha"), Issue(key="A2", type="Story", parent="E1", points=2.0, team="Alpha"),
    Issue(key="A3", type="Story", parent="E1", team="Alpha"),
    Issue(key="B1", type="Bug", parent="E1", points=1.0, team="Beta"), Issue(key="B2", type="Bug", parent="E1", team="Beta"),
    Issue(key="C1", type="Story", parent="E2", points=20.0, team="Beta"), Issue(key="C2", type="Story", parent="E2", team="Beta"),
)


@pytest.mark.parametrize("rule,expected", [
    (C.UNEST_MEDIAN, [5.0, 5.0, 5.0]),                  # Stufe 1 im Teilbaum: Median von 8, 2, 1, 20
    (C.UNEST_PLAN, [5.0, 5.0, 5.0]),                    # ohne Teilprojekt dieselbe Datenbasis
    (C.UNEST_TYPE, [8.0, 1.0, 8.0]),                    # Stories 8, 2, 20 → 8; Bugs: nur 1
    (C.UNEST_SIBLINGS, [2.0, 2.0, 20.0]),               # unter E1: 8, 2, 1 → 2 (auch für den Bug); unter E2: nur 20
    (C.UNEST_TEAM, [5.0, 10.5, 10.5]),                  # Alpha: 8, 2 → 5; Beta: 1, 20 → 10,5
    (C.UNEST_CHAIN, [2.0, 2.0, 20.0]),                  # Geschwister kommen zuerst
    (C.UNEST_ONE, [1.0, 1.0, 1.0]),
    (C.UNEST_IGNORE, [0.0, 0.0, 0.0])])
def test_every_rule_for_unestimated_tickets_by_hand(rule, expected):
    atoms = A.select_atoms(RULE_ITEMS)
    assert [RULE_ITEMS[i].key for i in atoms] == ["A1", "A2", "A3", "B1", "B2", "C1", "C2"]
    w = A.atom_weights(RULE_ITEMS, atoms, rule)
    assert w[[0, 1, 3, 5]].tolist() == [8.0, 2.0, 1.0, 20.0]                                    # geschätzte Tickets behalten ihre Story Points
    assert w[[2, 4, 6]].tolist() == expected


def test_the_median_of_the_whole_plan_differs_from_the_subtree_only_for_a_subproject():
    scoped = A.scope_issues(RULE_ITEMS, "E1")
    atoms = A.select_atoms(scoped)
    assert A.atom_weights(scoped, atoms, C.UNEST_MEDIAN)[[2]].tolist() == [2.0]                            # im Teilbaum: Median von 8, 2, 1
    assert A.atom_weights(scoped, atoms, C.UNEST_PLAN, plan=RULE_ITEMS)[[2]].tolist() == [5.0]            # Stufe 1 des ganzen Plans: Median von 8, 2, 1, 20
    assert A.atom_weights(scoped, atoms, C.UNEST_PLAN)[[2]].tolist() == [2.0]                             # ohne `plan` gilt der Teilbaum selbst


def test_the_fallback_chain_goes_from_siblings_to_type_to_level_to_the_plan_to_one():
    plan = (Issue(key="E", type="Epic"), Issue(key="F", type="Epic"),
            Issue(key="S1", type="Story", parent="E"), Issue(key="K1", type="Bug", parent="E", points=3.0), Issue(key="K2", type="Bug", parent="E"),
            Issue(key="T1", type="Task", parent="E", points=7.0), Issue(key="O1", type="Story", parent="F", points=10.0), Issue(key="U1", type="Sub-task", is_subtask=True, parent="T1"))
    scoped = A.scope_issues(plan, "E")
    atoms = A.select_atoms(scoped)
    keys = [scoped[i].key for i in atoms]
    w = dict(zip(keys, A.atom_weights(scoped, atoms, C.UNEST_CHAIN, plan=plan).tolist()))
    assert keys == ["S1", "K1", "K2", "U1"]
    assert w["K2"] == 3.0 and w["S1"] == 3.0                    # die geschätzten Geschwister unter E sind nur K1 (3): T1 hat Kinder und zählt nicht selbst; sie kommen vor Typ und Stufe
    assert w["U1"] == 6.5                    # keine geschätzten Geschwister, kein Sub-Task, keine geschätzte Stufe 2 im Teilbaum: der Median aller geschätzten Blätter des Plans (K1 = 3, O1 = 10; T1 hat Kinder)
    empty = (Issue(key="A"),)
    assert A.atom_weights(empty, [0], C.UNEST_CHAIN).tolist() == [1.0]                                    # nirgends etwas geschätzt: 1


def test_story_points_of_a_story_are_distributed_over_its_unestimated_sub_tasks(mini):
    atoms = A.select_atoms(mini)
    assert A.atom_weights(mini, atoms, C.UNEST_MEDIAN, distribute=True).tolist() == [3.0, 2.0, 2.5, 1.0, 2.5, 2.5]          # S2 (5) teilt sich auf T1 und T2
    assert A.atom_weights(mini, atoms, C.UNEST_MEDIAN).tolist() == [3.0, 2.0, 2.5, 1.0, 1.0, 1.0]                              # ohne: Regel der Stufe


def test_distribution_needs_an_estimated_story_and_no_estimated_sub_task():
    def weights(*items):
        atoms = A.select_atoms(items)
        return {items[i].key: w for i, w in zip(atoms, A.atom_weights(items, atoms, C.UNEST_MEDIAN, distribute=True).tolist())}
    sub = lambda key, parent, points=None: Issue(key=key, type="Sub-task", is_subtask=True, parent=parent, points=points)       # noqa: E731
    assert weights(Issue(key="S", points=6.0), sub("U1", "S"), sub("U2", "S"), sub("U3", "S")) == {"U1": 2.0, "U2": 2.0, "U3": 2.0}
    assert weights(Issue(key="S", points=5.0), sub("U1", "S", 2.0), sub("U2", "S")) == {"U1": 2.0, "U2": 2.0}                 # gemischt: die Regel (Median der Stufe 2)
    assert weights(Issue(key="S"), sub("U1", "S"), sub("U2", "S")) == {"U1": 1.0, "U2": 1.0}                                    # die Story ist ungeschätzt: die Regel
    assert weights(Issue(key="E", type="Epic", points=10.0), Issue(key="S1", parent="E"), Issue(key="S2", parent="E")) == {"S1": 1.0, "S2": 1.0}      # ein Epic verteilt nichts


# ---------------------------------------------------------------- Sprints

def test_a_ticket_without_sprint_takes_the_sprints_of_its_nearest_ancestor_with_one(mini):
    sprints = A.ticket_sprints(mini)
    keys = [t.key for t in mini]
    assert sprints[keys.index("S1")] == ("Sprint 1",) and sprints[keys.index("S2")] == ("Sprint 1", "Sprint 2")
    assert sprints[keys.index("T1")] == ("Sprint 1", "Sprint 2") and sprints[keys.index("S3")] == () and sprints[keys.index("E1")] == ()          # Sub-Tasks erben von ihrer Story, Epics ohne Sprint bleiben leer


def test_sprints_are_inherited_across_several_levels_and_survive_a_cycle():
    chain = (Issue(key="A", sprints=("Sprint 7",)), Issue(key="B", parent="A"), Issue(key="C", parent="B"))
    assert A.ticket_sprints(chain) == [("Sprint 7",)] * 3
    loop = (Issue(key="A", parent="B"), Issue(key="B", parent="A"))
    assert A.ticket_sprints(loop) == [(), ()]


def test_the_sprint_of_a_counting_ticket_is_its_last_one_or_the_group_without_sprint(mini):
    atoms = A.select_atoms(mini)
    assert A.sprint_labels(mini, atoms) == ["Sprint 1", C.NO_SPRINT, "Sprint 2", "Sprint 2", "Sprint 2", "Sprint 2"]       # S1, S3, S4, B1, T1, T2


def test_assigning_labels_splits_a_ticket_with_several_labels_into_equal_shares():
    first = A.assign_labels([["Sprint 10"], ["Sprint 2", "Sprint 10"], ["(ohne Sprint)"]])
    assert first.labels == ("Sprint 2", "Sprint 10", "(ohne Sprint)") and first.share.tolist() == [1.0, 0.5, 0.5, 1.0]


def test_cycle_members_are_the_tickets_on_a_loop_of_parent_references_and_nothing_else():
    issues = (Issue(key="A", parent="B"), Issue(key="B", parent="A"), Issue(key="C", parent="A"),        # A und B bilden den Zyklus, C hängt daran
              Issue(key="D", parent="D"), Issue(key="E"), Issue(key="F", parent="E"), Issue(key="G", parent="X"))
    assert A.cycle_members(issues) == [0, 1, 3] and A.cycle_members(()) == [] and A.cycle_members(make_mini_for_cycles()) == []


def make_mini_for_cycles():
    return (Issue(key="E"), Issue(key="S", parent="E"), Issue(key="T", parent="S"))


@pytest.mark.parametrize("seed", range(8))
def test_median_table_equals_the_statistics_median_per_group(seed):
    """Die Mediane je Gruppe (NumPy, sortiert) sind dieselben wie `statistics.median` je Gruppe, auch bei gerader Anzahl, Gleichständen und Gruppen mit einem Wert."""
    import random
    import statistics
    rng = random.Random(seed)
    issues = tuple(Issue(key=f"X-{n}", parent=rng.choice(["", "A", "B", "C", "D"]), points=float(rng.choice((0.5, 1, 1, 2, 3, 5, 8, 13)))) for n in range(rng.randint(1, 60)))
    members = [i for i in range(len(issues)) if rng.random() < 0.8]
    got = A._median_table(issues, members, lambda i: issues[i].parent)
    groups: dict = {}
    for i in members:
        groups.setdefault(issues[i].parent, []).append(issues[i].points)
    assert got == {k: float(statistics.median(v)) for k, v in groups.items()}
    assert A._median_table(issues, [], lambda i: 0) == {}
