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


def test_epic_of_follows_the_parent_chain_and_survives_cycles(mini):
    assert A.epic_of(mini) == ["E1", "E2", "E1", "E1", "E2", "E2", "", "E1", "E1"]
    loop = (Issue(key="A", parent="B"), Issue(key="B", parent="A"))
    assert A.epic_of(loop) == ["", ""]


def test_group_by_epic_by_hand(mini):
    atoms = A.select_atoms(mini)
    w = A.atom_weights(mini, atoms)
    c = np.array([1.0, 0.0, 0.8, 1.0, 1.0, 0.0])
    done = np.array([True, False, False, True, True, False])
    stats = A.aggregate(A.assign_groups(mini, atoms, C.DIM_EPIC), w, c, done, np.array([False, False, True, False, True, True]))
    assert stats.labels == ("E1: Epic A", "E2: Epic B", "(ohne Epic)")
    assert stats.weight.tolist() == [5.0, 4.5, 1.0] and stats.credited.tolist() == pytest.approx([4.0, 2.0, 1.0])          # E1: S1 (3) + T1 (1) + T2 (1)
    assert stats.progress.tolist() == pytest.approx([4 / 5, 2 / 4.5, 1.0]) and stats.unestimated.tolist() == [2.0, 1.0, 0.0]
    assert stats.done_weight.tolist() == [4.0, 0.0, 1.0] and stats.count.tolist() == [3.0, 2.0, 1.0]


def test_multi_valued_dimension_splits_a_ticket_evenly(mini):
    atoms = A.select_atoms(mini)
    w = A.atom_weights(mini, atoms)
    c = np.array([1.0, 0.0, 0.8, 1.0, 1.0, 0.0])
    stats = A.aggregate(A.assign_groups(mini, atoms, C.DIM_COMPONENT), w, c, np.zeros(6, dtype=bool), np.zeros(6, dtype=bool))
    by = dict(zip(stats.labels, zip(stats.weight.tolist(), stats.credited.tolist())))
    assert by["Backend"] == pytest.approx((4.5, 3.5)) and by["Frontend"] == pytest.approx((4.0, 3.5)) and by["(ohne Komponente)"] == pytest.approx((2.0, 0.0))        # die Sub-Tasks erben Backend von S2
    assert stats.weight.sum() == pytest.approx(w.sum())                               # die Summe über alle Gruppen bleibt die Gesamtsumme


def test_sprint_dimension_uses_the_last_sprint(mini):
    atoms = A.select_atoms(mini)
    assign = A.assign_groups(mini, atoms, C.DIM_SPRINT)
    assert assign.labels == ("Sprint 1", "Sprint 2", "(ohne Sprint)")
    assert [assign.labels[g] for g in assign.group] == ["Sprint 1", "(ohne Sprint)", "Sprint 2", "Sprint 2", "Sprint 2", "Sprint 2"]          # die Sub-Tasks erben den letzten Sprint von S2


def test_every_dimension_assigns_each_atom_with_shares_summing_to_one(mini):
    atoms = A.select_atoms(mini)
    for dim in C.DIMENSIONS:
        assign = A.assign_groups(mini, atoms, dim, 2)
        per_atom = np.bincount(assign.atom, weights=assign.share, minlength=len(atoms))
        assert per_atom.tolist() == pytest.approx([1.0] * len(atoms)), dim
    with pytest.raises(ValueError):
        A.assign_groups(mini, atoms, "Unsinn")


def test_other_dimensions_by_hand():
    items = (Issue(key="A", team="Alpha", area="Nord", priority="Hoch", type="Story", status="Done", labels=("x", "y"), versions=("R1",), assignee="P"),
             Issue(key="B", type="Bug"))
    atoms = [0, 1]
    labels = lambda dim: [A.assign_groups(items, atoms, dim).labels[g] for g in A.assign_groups(items, atoms, dim).group]       # noqa: E731
    assert labels(C.DIM_TEAM) == ["Alpha", "(ohne Team)"] and labels(C.DIM_AREA) == ["Nord", "(ohne Bereich)"] and labels(C.DIM_PRIORITY) == ["Hoch", "(ohne Priorität)"]
    assert labels(C.DIM_TYPE) == ["Story", "Bug"] and labels(C.DIM_STATUS) == ["Done", "To Do"] and labels(C.DIM_ASSIGNEE) == ["P", "(nicht zugewiesen)"]
    assert labels(C.DIM_RELEASE) == ["R1", "(ohne Release)"] and labels(C.DIM_LABEL) == ["x", "y", "(ohne Label)"]


def test_natural_key_sorts_numbers_as_numbers_and_empty_groups_last():
    assert sorted(["Sprint 10", "Sprint 2", "(ohne Sprint)", "Sprint 1"], key=A.natural_key) == ["Sprint 1", "Sprint 2", "Sprint 10", "(ohne Sprint)"]


# ---------------------------------------------------------------- Teilprojekt

def test_subtree_and_scope_make_the_root_a_standalone_dataset(mini):
    assert A.subtree_keys(mini, "E1") == {"E1", "S1", "S2", "T1", "T2"}
    scoped = A.scope_issues(mini, "E2")
    assert [t.key for t in scoped] == ["E2", "S3", "S4"] and scoped[0].parent == ""
    assert A.scope_issues(mini, C.ROOT_ALL) == tuple(mini)
    story = A.scope_issues(mini, "S2")
    assert [t.key for t in story] == ["S2", "T1", "T2"] and story[0].parent == "" and A.epic_of(story) == ["", "", ""]
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
    assert A.assign_groups(mini, atoms, C.DIM_LEVEL, 1).labels == ("B1", "E1: Epic A", "E2: Epic B")
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
