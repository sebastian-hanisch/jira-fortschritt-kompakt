"""Diagramme: Plotly-Abbildungen entstehen für jedes Projekt und jede Ebene und tragen die Werte der Auswertung."""

import numpy as np
import pytest

import jira_constants as C
import jira_evaluation as ev
from conftest import random_project
from jira_core import Issue
from jira_charts import MAX_BARS, TILE_H, TILE_W, build_progress_bars, build_tiles, build_tree_graph, progress_color, selected_key, squarify, tile_layout


def test_progress_bars_show_one_bar_per_group_with_the_weights(mini):
    a = ev.analyse(mini)
    fig = build_progress_bars(a.stats, "SP")
    assert list(fig.data[0].y) == ["E1: Epic A", "E2: Epic B", "(ohne Epic)"]
    total = sum(np.array(t.x) for t in fig.data)
    assert total.tolist() == pytest.approx([5.0, 4.5, 1.0])                       # erledigt + angerechnet + offen = Gewicht der Gruppe
    assert len(fig.layout.annotations) == 3 and fig.layout.xaxis.fixedrange and fig.layout.yaxis.fixedrange


def test_progress_bars_show_at_most_the_heaviest_groups():
    items = tuple(Issue(key=f"S-{n}", points=float(n + 1), sprints=(f"Sprint {n}",)) for n in range(MAX_BARS + 10))
    a = ev.analyse(items, ev.Settings(dimension=C.DIM_SPRINT))
    assert len(a.stats.labels) == MAX_BARS + 10
    shown = list(build_progress_bars(a.stats, "SP").data[0].y)
    assert len(shown) == MAX_BARS and "Sprint 39" in shown and "Sprint 0" not in shown          # die schwersten Gruppen (Gewicht n + 1), in natürlicher Reihenfolge


def test_tree_graph_has_one_marker_per_node_and_names_unmeasurable_nodes_grey(mini):
    g = ev.analyse(mini, ev.Settings(unest_rule=C.UNEST_IGNORE)).tree
    fig = build_tree_graph(g, "SP")
    markers = sum(len(t.x) for t in fig.data[1:])
    assert markers == len(g.keys) and fig.layout.yaxis.autorange == "reversed"


@pytest.mark.parametrize("seed", range(6))
def test_all_charts_build_for_random_projects_in_every_dimension(seed):
    project = random_project(seed, n_epics=3 + seed)
    for dim in C.DIMENSIONS:
        a = ev.analyse(project, ev.Settings(dimension=dim, level=2, unest_rule=C.UNEST_RULES[seed % 3]))
        assert build_progress_bars(a.stats, "SP") is not None and build_tree_graph(a.tree, "SP") is not None and build_tiles(a.tree, "SP") is not None


# ---------------------------------------------------------------- Kachelansicht

def _no_overlap(rects, tol=1e-9):
    for n, (x1, y1, w1, h1) in enumerate(rects):
        for x2, y2, w2, h2 in rects[n + 1:]:
            assert x1 + w1 <= x2 + tol or x2 + w2 <= x1 + tol or y1 + h1 <= y2 + tol or y2 + h2 <= y1 + tol, ((x1, y1, w1, h1), (x2, y2, w2, h2))


def test_squarify_by_hand():
    assert squarify([1.0], 0, 0, 10, 5) == [(0, 0, 10, 5)]
    assert squarify([], 0, 0, 10, 5) == [] and squarify([1.0], 0, 0, 0, 5) == []
    rects = squarify([6.0, 6.0, 4.0, 3.0, 2.0, 2.0, 1.0], 0, 0, 6, 4)                    # das Beispiel der Veröffentlichung (Fläche 24)
    assert sum(w * h for _, _, w, h in rects) == pytest.approx(24.0)
    assert [w * h for _, _, w, h in rects] == pytest.approx([6.0, 6.0, 4.0, 3.0, 2.0, 2.0, 1.0])
    assert rects[0] == pytest.approx((0, 0, 3.0, 2.0)) and rects[1] == pytest.approx((0, 2.0, 3.0, 2.0))          # die beiden größten füllen die linke Hälfte


@pytest.mark.parametrize("seed", range(12))
def test_squarify_tiles_the_rectangle_without_overlap_in_the_order_of_the_values(seed):
    import random
    rng = random.Random(seed)
    values = [rng.choice((0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 13.0)) for _ in range(rng.randint(1, 25))]
    x, y, w, h = 3.0, 2.0, 100.0, 58.0
    rects = squarify(values, x, y, w, h)
    assert len(rects) == len(values) and sum(rw * rh for _, _, rw, rh in rects) == pytest.approx(w * h)
    assert [rw * rh / (w * h) for _, _, rw, rh in rects] == pytest.approx([v / sum(values) for v in values])      # Fläche proportional, Reihenfolge wie die Werte
    assert all(rx >= x - 1e-9 and ry >= y - 1e-9 and rx + rw <= x + w + 1e-9 and ry + rh <= y + h + 1e-9 for rx, ry, rw, rh in rects)
    _no_overlap(rects)


def test_tile_layout_of_the_mini_project_by_hand(mini):
    g = ev.analyse(mini).tree
    tiles = tile_layout(g)
    level1 = [t for t in tiles if t.level == 1]
    assert [t.key for t in level1] == ["E1", "E2", "B1"] and [t.weight for t in level1] == [5.0, 4.5, 1.0]            # nach Gewicht, Kinder der Wurzel (Projekt)
    assert sum(t.w * t.h for t in level1) == pytest.approx(TILE_W * TILE_H) and [t.framed for t in level1] == [True, True, False]
    level2 = {(t.key): t for t in tiles if t.level == 2}
    assert sorted(level2) == ["S1", "S2", "S3", "S4"] and level2["S2"].weight == 2.0 and level2["S2"].progress == pytest.approx(0.5)
    for t in level2.values():                                                                                         # die kleinen Kacheln liegen in ihrer großen
        outer = next(o for o in level1 if o.key == ("E1" if t.key in ("S1", "S2") else "E2"))
        assert outer.x <= t.x + 1e-9 and outer.y <= t.y + 1e-9 and t.x + t.w <= outer.x + outer.w + 1e-9 and t.y + t.h <= outer.y + outer.h + 1e-9
    _no_overlap([(t.x, t.y, t.w, t.h) for t in level1])
    _no_overlap([(t.x, t.y, t.w, t.h) for t in tiles if t.level == 2])


def test_tile_layout_of_a_subproject_starts_below_its_root(mini):
    from jira_core import scope_issues
    sub = scope_issues(mini, "E1")
    g = ev.analyse(sub, ev.Settings(root="E1")).tree
    tiles = tile_layout(g)
    assert [t.key for t in tiles if t.level == 1] == ["S1", "S2"] and [t.key for t in tiles if t.level == 2] == ["T1", "T2"]


def test_tile_layout_leaves_out_tiles_without_weight(mini):
    g = ev.analyse(mini, ev.Settings(unest_rule=C.UNEST_IGNORE)).tree
    keys = {t.key for t in tile_layout(g)}
    assert "S4" not in keys and "T1" not in keys and {"E1", "E2", "B1", "S1", "S3"} <= keys
    empty = ev.analyse((Issue(key="A", status="Done"),), ev.Settings(unest_rule=C.UNEST_IGNORE)).tree
    assert tile_layout(empty) == []


def test_build_tiles_makes_every_tile_a_clickable_bar_with_its_key(mini):
    g = ev.analyse(mini).tree
    fig = build_tiles(g, "SP")
    assert [t.type for t in fig.data] == ["bar", "bar"] and fig.layout.barmode == "overlay"
    assert [d[0] for d in fig.data[0].customdata] == ["E1", "E2", "B1"] and sorted(d[0] for d in fig.data[1].customdata) == ["S1", "S2", "S3", "S4"]
    assert fig.layout.yaxis.range == (TILE_H, 0) and "Klick: als Teilprojekt öffnen" in fig.data[0].hovertext[0] and "Klick" not in fig.data[0].hovertext[2]          # B1 hat keine Kinder
    assert [a.text for a in fig.layout.annotations][0].startswith("<b>E1</b>") and len(fig.layout.annotations) == 2          # Kopfzeilen der beiden Kacheln mit Kindern


def test_build_tiles_without_weight_is_an_empty_figure():
    fig = build_tiles(ev.analyse((Issue(key="A", status="Done"),), ev.Settings(unest_rule=C.UNEST_IGNORE)).tree, "SP")
    assert len(fig.data) == 0


def test_progress_color_runs_from_red_over_yellow_to_green():
    assert progress_color(0.0) == "rgba(201,83,75,1.0)" and progress_color(0.5) == "rgba(242,213,126,1.0)" and progress_color(1.0) == "rgba(47,107,101,1.0)"
    assert progress_color(2.0) == progress_color(1.0) and progress_color(-1.0) == progress_color(0.0) and progress_color(float("nan"), 0.5) == "rgba(190,190,190,0.5)"
    assert progress_color(0.25, 0.35).endswith(",0.35)")


def test_only_tiles_with_children_are_drillable(mini):
    tiles = {t.key: t for t in tile_layout(ev.analyse(mini).tree)}
    assert [tiles[k].drillable for k in ("E1", "E2", "B1")] == [True, True, False] and tiles["S2"].drillable and not tiles["S1"].drillable          # S2 hat Sub-Tasks, S1 und B1 sind Blätter


def test_selected_key_reads_the_key_from_the_customdata_of_a_clicked_point():
    assert selected_key([{"customdata": ["S2"], "x": 1}]) == "S2" and selected_key([{"customdata": "S2"}]) == "S2"
    assert selected_key([]) == "" and selected_key(None) == "" and selected_key([{"x": 1}]) == "" and selected_key([{"customdata": []}]) == ""
    assert selected_key([{"customdata": None}, {"customdata": ["E1"]}]) == "E1" and selected_key([{"customdata": ["E1"]}, {"customdata": ["E1"]}]) == "E1"
    assert selected_key([{"customdata": ["E1"]}, {"customdata": ["E2"]}]) == ""                    # ein aufgezogener Rahmen über mehrere Kacheln wählt nichts


def test_graph_markers_carry_the_keys_for_clicks(mini):
    g = ev.analyse(mini).tree
    keys = [k for t in build_tree_graph(g, "SP").data[1:] for k in t.customdata]
    assert sorted(keys) == sorted(g.keys)
