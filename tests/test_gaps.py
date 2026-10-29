"""Randfälle und Stellen, an denen ein kleiner Fehler im Code bisher keinen Test rot machte (Grenzen, Gleichstände, Zeilenlage, Toleranzen). Jeder Test beschreibt, was die Stelle leistet.

Nicht abgedeckt sind bewusst die reinen Darstellungsmaße der Diagramme (Höhen, Schriftgrößen, Abstände von Beschriftungen, Schwelle der Schriftfarbe): Ein anderer Wert dort ändert
nichts, was sich prüfen ließe, außer dem Aussehen."""

import types

import numpy as np
import pytest

import jira_charts as CH
import jira_core as A
import jira_evaluation as ev
import jira_plan as J
from conftest import make_mini
from jira_core import Issue

# ---------------------------------------------------------------- Teilprojektbaum: Zeilen und Fortschritt


def _graph_of(issues, w, c, credit_of, **kw):
    atoms = A.select_atoms(issues)
    return A.tree_graph(issues, atoms, np.array(w, dtype=float), np.array(c, dtype=float), credit_of, **kw)


def test_graph_rows_put_leaves_one_below_the_other_and_parents_in_the_middle_of_their_children():
    mini = make_mini()
    atoms = A.select_atoms(mini)
    g = A.tree_graph(mini, atoms, A.atom_weights(mini, atoms), np.array([1.0, 0.0, 0.8, 1.0, 1.0, 0.0]), {})
    assert g.keys == ("Projekt", "E1", "S1", "S2", "T1", "T2", "E2", "S3", "S4", "B1")
    # Blätter S1, T1, T2, S3, S4, B1 in den Zeilen 0 bis 5; S2 mitten über T1 und T2, E1 mitten über S1 und S2, E2 über S3 und S4, das Projekt über E1 und B1
    assert g.y.tolist() == [2.875, 0.75, 0.0, 1.5, 1.0, 2.0, 3.5, 3.0, 4.0, 5.0]


def test_graph_shows_the_credit_of_the_status_only_for_a_leaf_without_weight():
    issues = (Issue(key="A", status="Done"),                                       # Blatt ohne Gewicht, an der ersten Stelle: zeigt die Gutschrift seines Status
              Issue(key="B", status="To Do", points=1.0),                          # Blatt mit Gewicht: zeigt sein eigenes Verhältnis, nicht die Gutschrift des Status
              Issue(key="E", type="Epic", status="To Do"),                         # Epic ohne Kinder: nichts messbar
              Issue(key="P", status="In Review", points=2.0),
              Issue(key="Q", status="Done", is_subtask=True, parent="P"))          # Kind von P ohne Gewicht
    g = _graph_of(issues, [0.0, 1.0, 0.0], [1.0, 0.3, 1.0], {"Done": 1.0, "To Do": 0.9, "In Review": 0.8})
    by = dict(zip(g.keys, g.progress.tolist(), strict=True))
    assert by["A"] == 1.0 and by["Q"] == 1.0
    assert by["B"] == pytest.approx(0.3) and by["Projekt"] == pytest.approx(0.3)
    assert np.isnan(by["E"]) and np.isnan(by["P"])                                  # ein Knoten mit Kindern ohne Gewicht zeigt nichts, auch wenn sein Status etwas gutschreibt


def test_graph_of_nothing_has_only_the_project_node_without_progress():
    g = A.tree_graph((), [], np.array([]), np.array([]), {})
    assert g.keys == ("Projekt",) and np.isnan(g.progress[0]) and g.weight[0] == 0.0


def test_graph_with_exactly_the_node_limit_is_drawn_completely():
    mini = make_mini()
    atoms = A.select_atoms(mini)
    g = A.tree_graph(mini, atoms, A.atom_weights(mini, atoms), np.array([1.0, 0.0, 0.8, 1.0, 1.0, 0.0]), {}, max_nodes=10)
    assert g.n_total == 10 and g.shown_depth == 3 and not g.hidden.any()


def test_tree_order_makes_a_parent_listed_after_its_child_the_root():
    issues = (Issue(key="S", parent="E"), Issue(key="E"))
    assert [(issues[i].key, d, p) for i, d, p in A.tree_order(issues)] == [("E", 0, -1), ("S", 1, 1)]


def test_ratio_is_nan_without_a_positive_denominator_and_the_quotient_otherwise():
    out = A.ratio(np.array([1.0, 2.0, 0.0, 3.0]), np.array([2.0, 0.0, 0.0, -1.0]))
    assert out[0] == 0.5 and np.isnan(out[1:]).all()


# ---------------------------------------------------------------- Prüfer und Meldungen


def _fake_analysis(progress=0.5, weight=10.0, group_weight=10.0, n_atoms=4, group_count=4.0, credited=5.0):
    stats = types.SimpleNamespace(weight=np.array([group_weight]), count=np.array([group_count]), credited=np.array([credited]))
    return types.SimpleNamespace(progress=progress, progress_done=progress, stats=stats, weight=weight, n_atoms=n_atoms)


def test_consistency_accepts_a_project_that_is_one_hundred_percent_done():
    assert ev.check_consistency(_fake_analysis(progress=1.0, credited=10.0)) == []


def test_consistency_scales_the_tolerance_with_the_weight():
    big = 1.0e6
    assert ev.check_consistency(_fake_analysis(weight=big, group_weight=big + 1e-4, credited=big / 2)) == []          # Abweichung 1e-4 bei Gewicht 1e6: innerhalb der relativen Toleranz
    assert ev.check_consistency(_fake_analysis(n_atoms=10**6, group_count=10**6 + 1e-4, credited=5.0)) == []
    assert len(ev.check_consistency(_fake_analysis(weight=big, group_weight=big + 1.0, credited=big / 2))) == 1       # 1.0 ist es nicht


def test_consistency_names_each_violation():
    assert len(ev.check_consistency(_fake_analysis(progress=1.5))) >= 1                                    # außerhalb von 0 bis 100 %
    assert len(ev.check_consistency(_fake_analysis(group_weight=9.0))) >= 1                                # Gruppengewichte summieren sich nicht zum Gesamtgewicht
    assert len(ev.check_consistency(_fake_analysis(group_count=3.0))) >= 1
    assert len(ev.check_consistency(_fake_analysis(credited=4.0))) >= 1                                    # Beiträge passen nicht zum Gesamtfortschritt


def test_credit_for_a_weightless_project_is_checked_against_zero_weight_without_division():
    assert ev.check_consistency(_fake_analysis(progress=float("nan"), weight=0.0, group_weight=0.0, n_atoms=0, group_count=0.0, credited=0.0)) == []


def test_the_unestimated_note_turns_from_info_to_warning_at_twenty_percent():
    assert ev.unestimated_note(19, 100)[0] == "info" and ev.unestimated_note(20, 100)[0] == "warning"


def test_delta_points_needs_both_values():
    assert ev.delta_points(0.6, 0.5) == "+10.0 Punkte" and ev.delta_points(0.4, 0.5) == "-10.0 Punkte"
    assert ev.delta_points(float("nan"), 0.5) is None and ev.delta_points(0.5, float("nan")) is None and ev.delta_points(float("nan"), float("nan")) is None


# ---------------------------------------------------------------- Einlesen


def _csv(*lines):
    return ("\n".join(lines) + "\n").encode("utf-8")


def test_a_short_row_and_empty_cells_do_not_fail_and_give_empty_values():
    data = _csv("Vorgangsschlüssel;Vorgangsstatus;Titel;Story Points", "A-1;Done;Titel;3", "A-2;To Do")
    issues, _ = J.read_plan(data)
    assert [(i.key, i.status, i.summary, i.points) for i in issues] == [("A-1", "Done", "Titel", 3.0), ("A-2", "To Do", "", None)]


def test_a_cell_only_counts_with_text_and_every_filled_column_of_a_repeated_field_is_read():
    data = _csv("Vorgangsschlüssel;Vorgangsstatus;Sprint;Sprint", "A-1;Done;;Sprint 2", "A-2;Done;Sprint 1;Sprint 2")
    issues, _ = J.read_plan(data)
    assert issues[0].sprints == ("Sprint 2",) and issues[1].sprints == ("Sprint 1", "Sprint 2")


def test_the_delimiter_with_more_occurrences_wins_and_a_tie_means_comma():
    assert [i.key for i in J.read_plan(_csv("Vorgangsschlüssel,Vorgangsstatus", "A-1,Done"))[0]] == ["A-1"]
    assert [i.key for i in J.read_plan(_csv("Vorgangsschlüssel;Vorgangsstatus", "A-1;Done"))[0]] == ["A-1"]
    tie = J.read_plan(_csv("Vorgangsschlüssel,Vorgangsstatus,Titel", "A-1,Done,a;b;c;d;e"))[0]          # je 4 Kommas und Semikola: bei Gleichstand gilt das Komma
    assert tie[0].summary == "a;b;c;d;e"


def test_the_first_filled_column_of_a_field_with_several_columns_wins():
    issues, _ = J.read_plan(_csv("Vorgangsschlüssel;Vorgangsstatus;Team;Team", "A-1;Done;;Alpha", "A-2;Done;Beta;Alpha"))
    assert [i.team for i in issues] == ["Alpha", "Beta"]


def test_exactly_the_maximum_number_of_tickets_is_accepted_and_one_more_is_not():
    rows = [f"A-{n};Done" for n in range(5)]
    data = _csv("Vorgangsschlüssel;Vorgangsstatus", *rows)
    assert len(J.read_plan(data, max_issues=5)[0]) == 5
    with pytest.raises(J.PlanImportError):
        J.read_plan(data, max_issues=4)


# ---------------------------------------------------------------- Diagramme: Auswahl und Kachelmaße


def test_a_selection_without_a_text_key_gives_no_key():
    assert CH.selected_key([{"customdata": [5]}]) == "" and CH.selected_key([{"customdata": [""]}]) == "" and CH.selected_key([{"customdata": ["A"]}]) == "A"


def test_squarify_of_a_square_puts_the_first_row_as_a_column_on_the_left():
    assert CH.squarify([3.0, 1.0], 0.0, 0.0, 10.0, 10.0) == [(0.0, 0.0, 7.5, 10.0), (7.5, 0.0, 2.5, 10.0)]


def test_squarify_of_nothing_or_of_an_empty_rectangle_is_empty():
    assert CH.squarify([], 0, 0, 5, 5) == [] and CH.squarify([1.0], 0, 0, 0, 5) == [] and CH.squarify([1.0], 0, 0, 5, 0) == []


@pytest.mark.parametrize("seed", range(6))
def test_squarify_stays_inside_the_rectangle_and_keeps_the_rectangles_reasonably_square(seed):
    rng = np.random.default_rng(seed)
    values = [float(v) for v in rng.integers(1, 40, size=int(rng.integers(3, 14)))]
    w, h = float(rng.integers(20, 120)), float(rng.integers(20, 120))
    rects = CH.squarify(values, 5.0, 7.0, w, h)
    for x, y, rw, rh in rects:
        assert x >= 5.0 - 1e-9 and y >= 7.0 - 1e-9 and x + rw <= 5.0 + w + 1e-9 and y + rh <= 7.0 + h + 1e-9
    assert sum(rw * rh for _, _, rw, rh in rects) == pytest.approx(w * h)
    assert max(max(rw / rh, rh / rw) for _, _, rw, rh in rects) < 12            # eine falsch gewählte Seite ergäbe schmale Streifen mit Verhältnissen weit darüber


def test_inner_tiles_lie_inside_the_frame_of_their_outer_tile(mini):
    atoms = A.select_atoms(mini)
    g = A.tree_graph(mini, atoms, A.atom_weights(mini, atoms), np.array([1.0, 0.0, 0.8, 1.0, 1.0, 0.0]), {})
    tiles = CH.tile_layout(g)
    outer = {t.node: t for t in tiles if t.level == 1}
    for t in (t for t in tiles if t.level == 2):
        o = outer[int(g.parent[t.node])]
        assert t.x >= o.x + CH.TILE_PAD - 1e-9 and t.y >= o.y + CH.TILE_HEAD - 1e-9
        assert t.x + t.w <= o.x + o.w - CH.TILE_PAD + 1e-9 and t.y + t.h <= o.y + o.h - CH.TILE_PAD + 1e-9
    for o in (o for o in outer.values() if o.framed):
        inner = [t for t in tiles if t.level == 2 and int(g.parent[t.node]) == o.node]
        assert sum(t.w * t.h for t in inner) == pytest.approx((o.w - 2 * CH.TILE_PAD) * (o.h - CH.TILE_HEAD - CH.TILE_PAD))


def test_a_tile_without_drawn_children_but_with_hidden_tickets_can_be_opened():
    g = types.SimpleNamespace(
        keys=("Projekt", "A"), titles=("", ""), parent=np.array([-1, 0]), weight=np.array([1.0, 1.0]), progress=np.array([0.5, 0.5]), is_leaf=np.array([False, True]), hidden=np.array([0, 1]))
    assert [(t.key, t.drillable) for t in CH.tile_layout(g)] == [("A", True)]


def test_node_hover_names_what_is_missing_and_what_is_left_out(mini):
    g = types.SimpleNamespace(
        keys=("A", "B"), titles=("Titel", ""), types=("Story", ""), statuses=("Done", ""), weight=np.array([0.0, 2.0]), progress=np.array([1.0, float("nan")]),
        is_atom=np.array([False, True]), is_leaf=np.array([True, True]), hidden=np.array([0, 3]), ignored=np.array([True, False]))
    a, b = CH._node_hover(g, 0, "SP"), CH._node_hover(g, 1, "SP")
    assert a == "A: Titel<br>Story · Done<br>kein Gewicht<br>Fortschritt 100 %<br>zählt nicht selbst (Zählebene)<br>ausgeschlossen: zählt nicht (zurückgewiesen)"
    assert b == "B<br>Gewicht 2.00 SP<br>kein Fortschritt messbar<br>3 Tickets darunter sind im Sammelknoten „Rest“ zusammengefasst"


def test_node_hover_does_not_call_a_weighted_or_partial_atom_not_counting():
    g = types.SimpleNamespace(
        keys=("A", "B", "C"), titles=("", "", ""), types=("", "", ""), statuses=("", "", ""), weight=np.array([1.0, 0.0, 0.0]), progress=np.array([0.5, 0.5, 0.5]),
        is_atom=np.array([False, True, False]), is_leaf=np.array([True, True, False]), hidden=np.array([0, 0, 0]), ignored=None)
    assert "zählt nicht selbst" not in CH._node_hover(g, 0, "SP")           # hat Gewicht
    assert "zählt nicht selbst" not in CH._node_hover(g, 1, "SP")           # ist selbst ein Atom
    assert "zählt nicht selbst" not in CH._node_hover(g, 2, "SP")           # hat Kinder
