"""End-to-end über Streamlits AppTest: ohne Datei, mit Datei, jede Auswahl jeder Option, Teilprojekt, Zeitraum, Fehlerfälle und geänderte Gewichte."""

import os

import pytest
from streamlit.testing.v1 import AppTest

import jira_constants as C
import jira_evaluation as ev
from conftest import make_mini, plan_csv, random_project

APP_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")
TIMEOUT = int(os.environ.get("APPTEST_TIMEOUT", "300"))      # unter Last (parallele Läufe) reichen 180 s nicht immer; Umgebungsvariable zum Anpassen


def _open(data=None, name="plan.csv"):
    at = AppTest.from_file(APP_PATH, default_timeout=TIMEOUT)
    at.run(timeout=TIMEOUT)
    if data is not None:
        at.file_uploader(key="upload_0").set_value((name, data, "text/csv")).run(timeout=TIMEOUT)
    return at


def _ok(at, *context):
    assert not at.exception, (context, [str(e) for e in at.exception])
    assert not [e for e in at.error if "Interne Prüfung" in e.value], (context, [e.value for e in at.error])


def test_without_a_file_the_app_asks_for_one_and_stops():
    at = _open()
    _ok(at)
    assert not at.metric and not at.sidebar.selectbox and any("Plans" in i.value for i in at.info)


def test_the_headline_numbers_of_the_mini_project():
    at = _open(plan_csv(make_mini()))
    _ok(at)
    assert [m.label for m in at.metric] == ["Fortschritt (nach Status gewichtet)", "Nur Done, nach Gewicht", "Nur Done, nach Ticketzahl", "Offenes Gewicht (SP, gesamt 13,5)"]
    assert [m.value for m in at.metric] == ["44,4 %", "29,6 %", "40,0 %", "7,5"]            # 6 / 13,5; 4 / 13,5; 2 von 5; 13,5 · (1 − 6/13,5)
    assert [w.value for w in at.warning if "Bitte vor dem Hochladen" not in w.value] == [ev.unestimated_note(1, 5)[1]] and any("9 Tickets" in e.label for e in at.expander)       # nur die Meldung zum ungeschätzten Ticket (1 von 5 = 20 %); die Zahl der Tickets steht im Erkennungsbericht


def test_the_treemap_and_the_hierarchy_graph_are_shown():
    at = _open(plan_csv(make_mini()))
    _ok(at)
    headings = [m.value for m in at.markdown]
    assert any("Flächenansicht" in h for h in headings) and any("Hierarchiegraph" in h for h in headings)
    only_unestimated = _open("Vorgangsschlüssel;Vorgangsstatus\nA-1;Done\n".encode())
    at = only_unestimated
    at.sidebar.selectbox(key="unest_rule").set_value(C.UNEST_IGNORE).run(timeout=TIMEOUT)
    _ok(at)
    assert any("Kein Ticket hat Gewicht" in i.value for i in at.info)


def test_the_sidebar_has_only_the_selections_and_no_weighting_options():
    at = _open(plan_csv(make_mini()))
    labels = [s.label for s in at.sidebar.selectbox]
    assert labels == ["Teilprojekt (Wurzel)", "Tickets ohne Story Points", "Zusammenfassen nach"]
    assert not at.sidebar.toggle and not at.sidebar.radio and not at.sidebar.slider
    assert not at.radio or [r.label for r in at.radio] == ["Kennzahl je Zelle"]


def test_the_rule_for_unestimated_tickets_is_visible_and_changes_the_numbers():
    at = _open(plan_csv(make_mini()))
    assert at.sidebar.selectbox(key="unest_rule").value == C.UNEST_MEDIAN and at.sidebar.selectbox(key="unest_rule").options == list(C.UNEST_RULES)
    expected = {C.UNEST_MEDIAN: "44,4 %", C.UNEST_ONE: "40,0 %", C.UNEST_IGNORE: "36,4 %"}          # 6 / 13,5; 4,8 / 12; 4 / 11
    for rule, value in expected.items():
        at.sidebar.selectbox(key="unest_rule").set_value(rule).run(timeout=TIMEOUT)
        _ok(at, rule)
        assert at.metric[0].value == value and any(f"Regel: {rule}" in w.value for w in at.warning)


def test_every_dimension_runs_without_error():
    at = _open(plan_csv(make_mini()))
    for dim in C.DIMENSIONS:
        at.sidebar.selectbox(key="dimension").set_value(dim).run(timeout=TIMEOUT)
        _ok(at, dim)
        assert at.metric[0].value == "44,4 %"                                                   # die Ebene ändert den Gesamtwert nicht
    at.sidebar.selectbox(key="dimension").set_value(C.DIM_LEVEL).run(timeout=TIMEOUT)
    for level in (1, 2, 3):
        at.sidebar.selectbox(key="level").set_value(level).run(timeout=TIMEOUT)
        _ok(at, level)


def test_the_subproject_selection_rescopes_the_numbers():
    at = _open(plan_csv(make_mini()))
    at.sidebar.selectbox(key="root").set_value("E2").run(timeout=TIMEOUT)
    _ok(at)
    assert at.metric[0].value == "40,0 %" and any("E2" in i.value and "2 zählende" in i.value for i in at.info)       # S3 (2, offen) und S4 (Median 2, Review): 1,6 / 4
    at.sidebar.selectbox(key="root").set_value("S2").run(timeout=TIMEOUT)
    _ok(at)
    assert at.metric[0].value == "0,0 %"                                                         # nur S2 (In Progress) mit zwei Sub-Tasks
    at.sidebar.selectbox(key="root").set_value("").run(timeout=TIMEOUT)
    assert at.metric[0].value == "44,4 %"


def test_changed_status_weights_change_the_numbers():
    at = _open(plan_csv(make_mini()))
    at.session_state["overrides"] = (("In Review", 0.5), ("In Progress", 0.4))
    at.run(timeout=TIMEOUT)
    _ok(at)
    assert at.metric[0].value == pct_by_hand((3 + 5 * 0.4 + 2.5 * 0.5 + 1) / 13.5)
    reset = [b for b in at.button if b.label.startswith("↩️")]
    assert reset
    reset[0].click().run(timeout=TIMEOUT)
    _ok(at)
    assert at.metric[0].value == "44,4 %" and not at.session_state["overrides"]


def pct_by_hand(x):
    return f"{100 * x:.1f}".replace(".", ",") + " %"


def test_unreadable_files_show_an_error_and_stop():
    at = _open(b"Spalte A;Spalte B\n1;2\n")
    assert not at.exception and any("Vorgangsschlüssel" in e.value for e in at.error) and not at.metric
    at = _open(b"")
    assert not at.exception and any("leer" in e.value for e in at.error)
    at = _open("Vorgangsschlüssel;Vorgangsstatus\n".encode())
    assert not at.exception and any("keine Tickets" in w.value for w in at.warning) and not at.metric


def test_a_file_without_estimates_weighs_every_ticket_the_same():
    at = _open("Vorgangsschlüssel;Vorgangsstatus\nA-1;Done\nA-2;To Do\nA-3;In Progress\n".encode())
    _ok(at)
    assert any("Story-Points-Spalte" in w.value for w in at.warning) and at.metric[0].value == "33,3 %"          # (1 + 0 + 0) / 3
    assert at.metric[3].label.startswith("Offenes Gewicht (SP,")


def test_all_tickets_rejected_shows_a_dash_and_no_error():
    at = _open("Vorgangsschlüssel;Vorgangsstatus;Hierarchie\nA-1;Rejected;Story\nA-2;Won't do;Story\n".encode())
    _ok(at)
    assert at.metric[0].value == "–" and any("zurückgewiesene Tickets" in c.value for c in at.caption)


@pytest.mark.parametrize("seed", [0, 3, 7])
def test_random_projects_render_in_every_dimension(seed):
    at = _open(plan_csv(random_project(seed, n_epics=6)))
    _ok(at, seed)
    for dim in C.DIMENSIONS:
        at.sidebar.selectbox(key="dimension").set_value(dim).run(timeout=TIMEOUT)
        _ok(at, seed, dim)
    for tab_metric in ("Gewicht", "Tickets", "Angerechnet"):
        at.radio(key="table_metric").set_value(tab_metric).run(timeout=TIMEOUT)
        _ok(at, seed, tab_metric)
