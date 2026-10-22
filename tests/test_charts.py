"""Diagramme: Plotly-Abbildungen entstehen für jedes Projekt und jede Ebene und tragen die Werte der Auswertung."""

import numpy as np
import pytest

import jira_constants as C
import jira_evaluation as ev
from conftest import random_project
from jira_core import Issue
from jira_charts import MAX_BARS, build_progress_bars, build_tree_graph, build_treemap


def test_progress_bars_show_one_bar_per_group_with_the_weights(mini):
    a = ev.analyse(mini)
    fig = build_progress_bars(a.stats, "SP")
    assert list(fig.data[0].y) == ["E1: Epic A", "E2: Epic B", "(ohne Epic)"]
    total = sum(np.array(t.x) for t in fig.data)
    assert total.tolist() == pytest.approx([8.0, 4.5, 1.0])                       # erledigt + angerechnet + offen = Gewicht der Gruppe
    assert len(fig.layout.annotations) == 3 and fig.layout.xaxis.fixedrange and fig.layout.yaxis.fixedrange


def test_progress_bars_show_at_most_the_heaviest_groups():
    items = tuple(Issue(key=f"S-{n}", points=float(n + 1), sprints=(f"Sprint {n}",)) for n in range(MAX_BARS + 10))
    a = ev.analyse(items, ev.Settings(dimension=C.DIM_SPRINT))
    assert len(a.stats.labels) == MAX_BARS + 10
    shown = list(build_progress_bars(a.stats, "SP").data[0].y)
    assert len(shown) == MAX_BARS and "Sprint 39" in shown and "Sprint 0" not in shown          # die schwersten Gruppen (Gewicht n + 1), in natürlicher Reihenfolge


def test_treemap_carries_the_hierarchy(mini):
    h = ev.analyse(mini).hierarchy
    trace = build_treemap(h).data[0]
    assert list(trace.ids) == list(h.ids) and list(trace.values) == list(h.values) and trace.branchvalues == "total"
    assert list(trace.marker.colors) == list(h.progress)


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
        assert build_progress_bars(a.stats, "SP") is not None and build_tree_graph(a.tree, "SP") is not None and build_treemap(a.hierarchy) is not None
