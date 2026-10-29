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
    assert [m.label for m in at.metric] == ["Fortschritt (nach Status gewichtet)", "Nur Done, nach Gewicht", "Offenes Gewicht (SP, gesamt 10.50)"]
    assert [m.value for m in at.metric] == ["66.7 %", "47.6 %", "3.50"]            # 7 / 10.5; 5 / 10.5; 10.5 · (1 − 7/10.5)
    assert [w.value for w in at.warning if "Bitte vor dem Hochladen" not in w.value] == [ev.unestimated_note(3, 6)[1]] and any("9 Tickets" in e.label for e in at.expander)       # nur die Meldung zum ungeschätzten Ticket (3 von 6 = 50 %); die Zahl der Tickets steht im Erkennungsbericht


def test_the_treemap_and_the_hierarchy_graph_are_shown():
    at = _open(plan_csv(make_mini()))
    _ok(at)
    headings = [m.value for m in at.markdown]
    assert any("Kachelansicht" in h for h in headings) and any("Teilprojektbaum" in h for h in headings)
    only_unestimated = _open("Vorgangsschlüssel;Vorgangsstatus\nA-1;Done\n".encode())
    at = only_unestimated
    at.sidebar.selectbox(key="unest_rule").set_value(C.UNEST_IGNORE).run(timeout=TIMEOUT)
    _ok(at)
    assert any("Kein Ticket hat Gewicht" in i.value for i in at.info)


def test_the_sidebar_has_only_the_selections_and_no_weighting_options():
    at = _open(plan_csv(make_mini()))
    labels = [s.label for s in at.sidebar.selectbox]
    assert labels == ["Teilprojekt (Wurzel)", "Tickets ohne Story Points", "Sub-Tasks einer Story"]
    assert not at.sidebar.toggle and not at.sidebar.radio and not at.sidebar.slider
    assert not at.radio or [r.label for r in at.radio] == ["Kennzahl je Zelle"]


def test_the_rule_for_unestimated_tickets_is_visible_and_changes_the_numbers():
    at = _open(plan_csv(make_mini()))
    assert at.sidebar.selectbox(key="unest_rule").value == C.UNEST_MEDIAN and at.sidebar.selectbox(key="unest_rule").options == list(C.UNEST_RULES)
    expected = {C.UNEST_MEDIAN: ("66.7 %", "10.50"), C.UNEST_PLAN: ("66.7 %", "10.50"), C.UNEST_TYPE: ("66.7 %", "10.50"), C.UNEST_SIBLINGS: ("66.0 %", "10.00"), C.UNEST_TEAM: ("63.3 %", "12.00"),
                C.UNEST_CHAIN: ("63.3 %", "12.00"), C.UNEST_ONE: ("64.4 %", "9.00"), C.UNEST_IGNORE: ("66.7 %", "6.00")}          # 7 / 10.5; 6.6 / 10; 7.6 / 12; 5.8 / 9; 4 / 6 (Gewicht gesamt je Regel)
    for rule, (value, weight) in expected.items():
        at.sidebar.selectbox(key="unest_rule").set_value(rule).run(timeout=TIMEOUT)
        _ok(at, rule)
        assert at.metric[0].value == value and at.metric[2].label == f"Offenes Gewicht (SP, gesamt {weight})" and any(f"Regel: {rule}" in w.value for w in at.warning)


def test_the_summary_is_always_one_level_below_the_root():
    import json
    at = _open(plan_csv(make_mini()))
    assert not [s for s in at.sidebar.selectbox if s.key == "level"]                           # keine Auswahl der Stufe
    assert any("direkt unter dem Plan" in m.value for m in at.markdown)
    bars = lambda: json.loads(at.get("plotly_chart")[0].proto.spec)["data"][0]["y"]          # noqa: E731
    assert bars() == ["B1", "E1: Epic A", "E2: Epic B"]                                        # im ganzen Plan die obersten Tickets
    at.sidebar.selectbox(key="root").set_value("E1").run(timeout=TIMEOUT)
    _ok(at)
    assert any("direkt unter der Wurzel" in m.value for m in at.markdown) and bars() == ["S1", "S2"]          # die Kinder von E1; T1 und T2 zählen zu S2
    assert at.metric[0].value == "80.0 %"
    at.sidebar.selectbox(key="root").set_value("S2").run(timeout=TIMEOUT)
    assert bars() == ["T1", "T2"]


def test_the_subproject_selection_rescopes_the_numbers():
    at = _open(plan_csv(make_mini()))
    at.sidebar.selectbox(key="root").set_value("E2").run(timeout=TIMEOUT)
    _ok(at)
    assert at.metric[0].value == "40.0 %" and any("E2" in i.value and "2 zählende" in i.value for i in at.info)       # S3 (2, offen) und S4 (Median 2, Review): 1.6 / 4
    at.sidebar.selectbox(key="root").set_value("S2").run(timeout=TIMEOUT)
    _ok(at)
    assert at.metric[0].value == "50.0 %"                                                        # S2 zählt durch seine Sub-Tasks T1 (Done) und T2 (To Do), beide ungeschätzt und gleich schwer
    at.sidebar.selectbox(key="root").set_value("").run(timeout=TIMEOUT)
    assert at.metric[0].value == "66.7 %"


def test_changed_status_weights_change_the_numbers():
    at = _open(plan_csv(make_mini()))
    at.session_state["overrides"] = (("In Review", 0.5), ("To Do", 0.4))
    at.run(timeout=TIMEOUT)
    _ok(at)
    assert at.metric[0].value == pct_by_hand((3 + 2 * 0.4 + 2.5 * 0.5 + 1 + 1 + 0.4) / 10.5)
    reset = [b for b in at.button if b.label.startswith("↩️")]
    assert reset
    reset[0].click().run(timeout=TIMEOUT)
    _ok(at)
    assert at.metric[0].value == "66.7 %" and not at.session_state["overrides"]


def pct_by_hand(x):
    return f"{100 * x:.1f} %"


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
    assert any("Story-Points-Spalte" in w.value for w in at.warning) and at.metric[0].value == "33.3 %"          # (1 + 0 + 0) / 3
    assert at.metric[2].label.startswith("Offenes Gewicht (SP,")


def test_all_tickets_rejected_shows_a_dash_and_no_error():
    at = _open("Vorgangsschlüssel;Vorgangsstatus;Hierarchie\nA-1;Rejected;Story\nA-2;Won't do;Story\n".encode())
    _ok(at)
    assert at.metric[0].value == "–" and any("zurückgewiesene Tickets" in c.value for c in at.caption)


@pytest.mark.parametrize("seed", [0, 3, 7])
def test_random_projects_render_below_every_root(seed):
    import jira_core as A
    project = random_project(seed, n_epics=6)
    at = _open(plan_csv(project))
    _ok(at, seed)
    for root, _ in A.root_choices(project):
        at.sidebar.selectbox(key="root").set_value(root).run(timeout=TIMEOUT)
        _ok(at, seed, root)


def test_the_options_box_describes_the_variants_and_shows_the_effect_on_the_data():
    at = _open(plan_csv(make_mini()))
    _ok(at)
    labels = [e.label for e in at.expander]
    assert labels.index("🧮 Tickets ohne Story Points: Berechnungsmöglichkeiten") == labels.index("📖 Welche Status zählen wie viel? Standard nach Namen") + 1       # direkt nach den Regeln der Status
    assert not at.tabs or "🧮" not in " ".join(t.label for t in at.tabs)
    text = " ".join(m.value for m in at.markdown)
    assert "Teil 1: Woher kommt das Gewicht" in text and "Teil 2: Sub-Tasks ohne Story Points" in text and "Wirkung der wählbaren Regeln" in text
    table = next(t.value for t in at.dataframe if "Regel" in t.value.columns)
    assert list(table["Regel"]) == list(C.UNEST_RULES) and list(table["Gewicht gesamt"]) == [10.5, 10.5, 10.5, 10.0, 12.0, 12.0, 9.0, 6.0]


def test_the_options_box_is_there_before_a_file_is_loaded_without_the_table():
    at = _open()
    box = next(e for e in at.expander if "Berechnungsmöglichkeiten" in e.label)
    assert "Teil 1: Woher kommt das Gewicht" in " ".join(m.value for m in box.markdown) and not at.dataframe


def test_up_buttons_stand_above_the_selection_in_the_sidebar():
    at = _open(plan_csv(make_mini()))
    at.sidebar.selectbox(key="root").set_value("S2").run(timeout=TIMEOUT)
    assert [b.key for b in at.sidebar.button] == ["nav_top", "nav_up"] and not [b for b in at.main.button if str(b.key).startswith("nav_")]
    elements = [e.key for e in at.sidebar if getattr(e, "key", None) in ("nav_up", "nav_top", "root", "unest_rule")]
    assert elements[:3] == ["nav_top", "nav_up", "root"] and elements[-2:] == ["root", "unest_rule"]


def test_navigation_up_and_down_changes_the_root():
    at = _open(plan_csv(make_mini()))
    assert not [b for b in at.sidebar.button if b.key == "nav_up"]                                   # im ganzen Plan gibt es nichts darüber
    at.sidebar.selectbox(key="root").set_value("S2").run(timeout=TIMEOUT)                   # runter: S2 mit seinen Sub-Tasks
    _ok(at)
    up = at.sidebar.button(key="nav_up")
    assert up.label == "⬆ Eine Stufe hoch: E1: Epic A" and at.sidebar.button(key="nav_top").label == "⏫ Ganzer Plan"
    up.click().run(timeout=TIMEOUT)                                                         # hoch: E1
    _ok(at)
    assert at.sidebar.selectbox(key="root").value == "E1" and at.metric[0].value == "80.0 %"        # S1 (3, Done) und T1 (1, Done), T2 (1, offen) im Teilbaum von E1
    at.sidebar.button(key="nav_up").click().run(timeout=TIMEOUT)                                    # hoch: ganzer Plan
    _ok(at)
    assert at.sidebar.selectbox(key="root").value == "" and at.metric[0].value == "66.7 %" and not [b for b in at.sidebar.button if b.key == "nav_up"]


def test_the_top_button_jumps_to_the_whole_plan_from_a_deep_root():
    at = _open(plan_csv(make_mini()))
    at.sidebar.selectbox(key="root").set_value("S2").run(timeout=TIMEOUT)
    assert at.sidebar.button(key="nav_top").label == "⏫ Ganzer Plan"
    at.sidebar.button(key="nav_top").click().run(timeout=TIMEOUT)
    _ok(at)
    assert at.sidebar.selectbox(key="root").value == ""


def test_both_charts_report_clicks_as_a_selection():
    import ast
    tree = ast.parse(open(APP_PATH, encoding="utf-8").read())
    charts = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "plotly_chart"]
    clickable = [n for n in charts if {k.arg for k in n.keywords} >= {"on_select", "selection_mode"}]
    assert len(charts) == 4 and len(clickable) == 2                                      # Kachelansicht und Graph; die Balken (je Ticket und je Sprint) nicht
    assert not any(isinstance(n, ast.Name) and n.id == "child_pick" for n in ast.walk(tree)) and "Darunter öffnen" not in open(APP_PATH, encoding="utf-8").read()


def test_the_sub_task_rule_is_selectable_and_changes_the_numbers():
    at = _open(plan_csv(make_mini()))
    pick = at.sidebar.selectbox(key="sub_rule")
    assert pick.value == C.SUB_RULE and pick.options == list(C.SUB_RULES)
    expected = {C.SUB_RULE: ("66.7 %", "10.50"), C.SUB_SHARE: ("63.0 %", "13.50"), C.SUB_SELF: ("45.7 %", "14.00")}          # 7 / 10.5; 8.5 / 13.5; 6.4 / 14
    for rule, (value, weight) in expected.items():
        at.sidebar.selectbox(key="sub_rule").set_value(rule).run(timeout=TIMEOUT)
        _ok(at, rule)
        assert at.metric[0].value == value and at.metric[2].label == f"Offenes Gewicht (SP, gesamt {weight})"
    table = next(t.value for t in at.dataframe if "Zählende Tickets" in t.value.columns)
    assert list(table["Regel"]) == list(C.SUB_RULES)


def test_story_points_in_quarters_are_shown_with_two_decimals():
    at = _open("Vorgangsschlüssel;Vorgangsstatus;Hierarchie;Übergeordnetes Element;Story Points\nE-1;In Arbeit;Epic;;\nS-1;To Do;Story;E-1;0,25\nS-2;To Do;Story;E-1;0,5\n".encode("utf-8"))
    _ok(at)
    assert at.metric[2].label == "Offenes Gewicht (SP, gesamt 0.75)" and at.metric[2].value == "0.75"


def test_the_explanation_says_that_only_leaves_count_and_names_the_exceptions():
    at = _open(plan_csv(make_mini()))
    box = next(e for e in at.expander if e.label == "📐 So wird gerechnet")
    text = " ".join(m.value for m in box.markdown)
    for part in ("Nur die **Blätter**", "Zwischentickets", "gehen nicht ein", "ein Epic auf „Done“ mit offenen Kindern bringt also nichts", "Zurückgewiesen.", "nimmt alle Blätter darunter mit",
                 "Sub-Tasks einer Story", "Alle Kinder zurückgewiesen."):
        assert part in text, part


def test_the_assumptions_box_is_in_the_app_with_the_limits():
    import jira_constants as consts
    at = _open(plan_csv(make_mini()))
    box = next(e for e in at.expander if e.label == "⚠️ Annahmen, Grenzen und bekannte Probleme")
    text = " ".join(m.value for m in box.markdown)
    assert "Nur ein Stichtag" in text and "Obergrenzen" in text and f"{consts.MAX_UPLOAD_MB} MB" in text and f"{consts.MAX_IMPORT_ISSUES} Tickets" in text and f"{consts.GRAPH_MAX_NODES} Knoten" in text


JIRA_PROGRESS_CSV = (
    "Hierarchie;Titel;Story Points;Übergeordnetes Element;Vorgangsschlüssel;Vorgangsstatus;Fortschritt (%);Fortschritt abgeschlossen (SP);Verbleibender Fortschritt (SP)\n"
    "Epic;Eins;;;E-1;In Arbeit;40;4;6\n"
    "Story;A;4;E-1;S-1;Done;;;\n"
    "Story;B;6;E-1;S-2;To Do;;;\n").encode("utf-8")


def test_the_sprint_section_shows_a_bar_chart_and_a_table_when_tickets_have_sprints():
    at = _open(plan_csv(make_mini()))
    _ok(at)
    assert any("Fortschritt je Sprint" in m.value for m in at.markdown)
    table = next(t.value for t in at.dataframe if "Mitgenommene Tickets" in t.value.columns)
    assert table["Sprint"].tolist() == ["Sprint 1", "Sprint 2", "(ohne Sprint)", "Summe"] and table["Tickets"].tolist() == [1, 4, 1, 6]
    sub = _open(plan_csv(make_mini()))
    sub.sidebar.selectbox(key="root").set_value("S2").run(timeout=TIMEOUT)
    _ok(sub)
    table = next(t.value for t in sub.dataframe if "Mitgenommene Tickets" in t.value.columns)
    assert table["Sprint"].tolist() == ["Sprint 2", "Summe"] and table["Tickets"].tolist() == [2, 2]            # nur T1 und T2 unter S2: beide erben von S2, das als Wurzel keine Eltern mehr hat, aber selbst Sprints trägt


def test_without_any_sprint_the_section_is_left_out():
    data = "Vorgangsschlüssel;Vorgangsstatus;Story Points\nA-1;Done;3\nA-2;To Do;2\n".encode("utf-8")
    at = _open(data)
    _ok(at)
    assert not any("Fortschritt je Sprint" in m.value for m in at.markdown)


def test_unknown_status_names_are_reported_under_the_numbers_and_known_ones_are_not():
    data = "Vorgangsschlüssel;Vorgangsstatus;Story Points\nA-1;Freigegeben;3\nA-2;Done;2\nA-3;In Arbeit;5\n".encode("utf-8")
    at = _open(data)
    _ok(at)
    notes = [w.value for w in at.warning if "keine Regel kennt" in w.value]
    assert len(notes) == 1 and "„Freigegeben“ (1)" in notes[0] and "30.0 % des Gewichts" in notes[0]
    clean = _open(plan_csv(make_mini()))
    _ok(clean)
    assert not [w for w in clean.warning if "keine Regel kennt" in w.value]


def test_unusable_story_points_do_not_break_the_page_and_are_reported():
    data = "Vorgangsschlüssel;Vorgangsstatus;Story Points\nA-1;Done;nan\nA-2;To Do;inf\nA-3;Done;-4\nA-4;Done;2\n".encode("utf-8")
    at = _open(data)
    _ok(at)
    assert at.metric[0].value == "75.0 %" and any("nicht endlich oder negativ): 3" in w.value for w in at.warning)          # die drei unlesbaren Tickets wiegen wie der Median (2): 6 von 8 Story Points sind Done


def test_changed_status_weights_do_not_move_into_the_next_file_after_deleting_the_data():
    at = _open(plan_csv(make_mini()))
    _ok(at)
    at.session_state["overrides"] = (("Done", 0.5),)
    at.run(timeout=TIMEOUT)
    assert at.metric[0].value != "66.7 %"
    at.button(key="clear_loaded").click().run(timeout=TIMEOUT)
    assert not at.session_state["overrides"] if "overrides" in at.session_state else True
    at.file_uploader(key=f"upload_{at.session_state['upload_version']}").set_value(("zwei.csv", plan_csv(make_mini()), "text/csv")).run(timeout=TIMEOUT)
    _ok(at)
    assert at.metric[0].value == "66.7 %"


def test_titles_with_dollar_signs_and_asterisks_are_escaped_in_the_markdown_texts():
    data = "Hierarchie;Titel;Story Points;Übergeordnetes Element;Vorgangsschlüssel;Vorgangsstatus\nEpic;Kosten $5 bis $10 *neu*;;;E-1;In Arbeit\nStory;A;3;E-1;S-1;Done\n".encode("utf-8")
    at = _open(data)
    at.sidebar.selectbox(key="root").set_value("E-1").run(timeout=TIMEOUT)
    _ok(at)
    texts = " ".join(i.value for i in at.info)
    assert r"Kosten \$5 bis \$10 \*neu\*" in texts and "Kosten $5" not in texts


def test_jiras_own_progress_columns_are_ignored_and_no_comparison_is_shown():
    at = _open(JIRA_PROGRESS_CSV)
    _ok(at)
    assert not any("Gegenprobe" in m.value for m in at.markdown if m.value.lstrip().startswith("#"))
    assert not any("Jira:" in str(t.value.columns.tolist()) for t in at.dataframe)
    found = next(t.value for t in at.dataframe if "Gefunden in" in t.value.columns)
    assert not any("Jira" in str(name) for name in found["Feld"].tolist())            # der Erkennungsbericht kennt die Spalten nicht
    assert at.metric[0].value == "40.0 %"                                              # Story A (4, Done) von 10 Story Points: allein Status und Story Points zählen
