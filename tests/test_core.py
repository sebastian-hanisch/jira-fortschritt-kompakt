"""Kern an der Mini-Instanz (tests/conftest.py), alle Zahlen von Hand: Atome, Gewichte, Gruppen, Teilprojekt, Zeitraum, Hierarchiestufen, Hierarchiegraph."""

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
    for level in range(1, A.max_level(mini) + 2):
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
    assert [t.key for t in story] == ["S2", "T1", "T2"] and story[0].parent == "" and A.max_level(story) == 2            # die Wurzel steht auf Stufe 1
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
    assert A.max_level(mini) == 3
    atoms = A.select_atoms(mini)
    assert A.level_labels(mini, atoms, 1) == ["E1: Epic A", "E2: Epic B", "E2: Epic B", "B1", "E1: Epic A", "E1: Epic A"]
    assert A.level_labels(mini, atoms, 2) == ["S1", "S3", "S4", "(keine Stufe 2)", "S2", "S2"]
    assert A.level_labels(mini, atoms, 3) == ["(keine Stufe 3)"] * 4 + ["T1", "T2"]
    assert A.assign_groups(mini, atoms, 1).labels == ("B1", "E1: Epic A", "E2: Epic B")
    assert A.max_level(()) == 1
    deep = tuple(Issue(key=f"N{k}", parent=f"N{k - 1}" if k else "") for k in range(12))
    assert A.max_level(deep) == C.MAX_LEVELS


# ---------------------------------------------------------------- Hierarchiegraph

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


def test_graph_summarises_the_deepest_levels_beyond_the_node_limit(mini):
    g = _graph(mini, max_nodes=5)
    assert g.keys == ("Projekt", "E1", "E2", "B1") and g.shown_depth == 1 and g.n_total == 10
    assert g.hidden.tolist() == [0, 4, 2, 0] and g.is_leaf.tolist() == [False, True, True, True]
    assert g.weight.tolist() == pytest.approx([10.5, 5.0, 4.5, 1.0])                     # die Summen enthalten auch die nicht gezeichneten Tickets


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
    assert A.overall(np.array([3.0, 1.0]), np.array([1.0, 0.0]), np.array([True, False])) == pytest.approx((0.75, 0.75, 0.5))
    p_w, p_d, p_n = A.overall(np.array([]), np.array([]), np.array([], dtype=bool))
    assert np.isnan(p_w) and np.isnan(p_d) and np.isnan(p_n)
    p_w, p_d, p_n = A.overall(np.array([0.0, 0.0]), np.array([1.0, 1.0]), np.array([True, False]))
    assert np.isnan(p_w) and np.isnan(p_d) and p_n == 0.5


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


def test_default_level_is_the_top_level_that_splits_the_atoms(mini):
    atoms = A.select_atoms(mini)
    assert A.default_level(mini, atoms) == 1                                                   # B1, E1 und E2 sind drei Gruppen
    e1 = A.scope_issues(mini, "E1")
    assert A.default_level(e1, A.select_atoms(e1)) == 2                                        # die Wurzel E1 ist auf Stufe 1 eine einzige Gruppe, auf Stufe 2 sind es S1 und S2
    s2 = A.scope_issues(mini, "S2")
    assert A.default_level(s2, A.select_atoms(s2)) == 2
    single = (Issue(key="A"),)
    assert A.default_level(single, A.select_atoms(single)) == 1 and A.default_level((), []) == 1
