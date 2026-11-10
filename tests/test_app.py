"""End-to-end über Streamlits AppTest: ohne Datei, mit Datei, jede Auswahl jeder Option, Teilprojekt, Zeitraum, Fehlerfälle und geänderte Gewichte."""

import os

import pytest
from streamlit.testing.v1 import AppTest

import jira_constants as C
import jira_evaluation as ev
from conftest import make_mini, plan_csv, random_project
from jira_core import Issue

APP_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")
TIMEOUT = int(os.environ.get("APPTEST_TIMEOUT", "300"))      # unter Last (parallele Läufe) reichen 180 s nicht immer; Umgebungsvariable zum Anpassen


def _open(data=None, name="plan.csv"):
    """App, auf Wunsch mit hochgeladener Datei."""
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
    assert [m.label for m in at.metric] == ["Fortschritt (nach Status gewichtet)", "Nur Done, nach Gewicht", "Offenes Gewicht (SP, gesamt 14.00)"]
    assert [m.value for m in at.metric] == ["45.7 %", "28.6 %", "7.60"]            # 6.4 / 14; 4 / 14; 14 · (1 − 6.4/14)
    assert [w.value for w in at.warning if "Bitte vor dem Hochladen" not in w.value] == [ev.unestimated_note(1, 5)[1]] and any("9 Tickets" in e.label for e in at.expander)       # nur die Meldung zum ungeschätzten Ticket (1 von 5 = 20 %); die Zahl der Tickets steht im Erkennungsbericht


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
    assert labels == ["Teilprojekt (Wurzel)", "Tickets ohne Story Points"]
    assert not at.sidebar.toggle and not at.sidebar.radio and not at.sidebar.slider
    assert not at.radio or [r.label for r in at.radio] == ["Kennzahl je Zelle"]


def test_the_rule_for_unestimated_tickets_is_visible_and_changes_the_numbers():
    at = _open(plan_csv(make_mini()))
    assert at.sidebar.selectbox(key="unest_rule").value == C.UNEST_MEDIAN and at.sidebar.selectbox(key="unest_rule").options == list(C.UNEST_RULES)
    expected = {C.UNEST_MEDIAN: ("45.7 %", "14.00"), C.UNEST_PLAN: ("45.7 %", "14.00"), C.UNEST_TYPE: ("45.7 %", "14.00"), C.UNEST_SIBLINGS: ("43.1 %", "13.00"), C.UNEST_TEAM: ("44.4 %", "13.50"),
                C.UNEST_CHAIN: ("43.1 %", "13.00"), C.UNEST_ONE: ("40.0 %", "12.00"), C.UNEST_IGNORE: ("36.4 %", "11.00")}          # 6.4 / 14; 5.6 / 13; 6 / 13.5; 4.8 / 12; 4 / 11 (Gewicht gesamt je Regel)
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
    assert any("direkt unter der Wurzel" in m.value for m in at.markdown) and bars() == ["S1", "S2"]          # die Kinder von E1
    assert at.metric[0].value == "37.5 %"                                                        # S1 (3, Done) und S2 (5, In Progress)


def test_the_subproject_selection_rescopes_the_numbers():
    at = _open(plan_csv(make_mini()))
    at.sidebar.selectbox(key="root").set_value("E2").run(timeout=TIMEOUT)
    _ok(at)
    assert at.metric[0].value == "40.0 %" and any("E2" in i.value and "2 zählende" in i.value for i in at.info)       # S3 (2, offen) und S4 (Median 2, Review): 1.6 / 4
    at.sidebar.selectbox(key="root").set_value("E1").run(timeout=TIMEOUT)
    _ok(at)
    assert at.metric[0].value == "37.5 %"                                                        # S1 (3, Done) und S2 (5, In Progress; seine Sub-Tasks bleiben außen vor)
    at.sidebar.selectbox(key="root").set_value("").run(timeout=TIMEOUT)
    assert at.metric[0].value == "45.7 %"


def test_changed_status_weights_change_the_numbers():
    at = _open(plan_csv(make_mini()))
    at.session_state["overrides"] = (("In Review", 0.5), ("To Do", 0.4))
    at.run(timeout=TIMEOUT)
    _ok(at)
    assert at.metric[0].value == pct_by_hand((3 + 2 * 0.4 + 3 * 0.5 + 1) / 14)
    reset = [b for b in at.button if b.label.startswith("↩️")]
    assert reset
    reset[0].click().run(timeout=TIMEOUT)
    _ok(at)
    assert at.metric[0].value == "45.7 %" and not at.session_state["overrides"]


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
    assert "Woher kommt das Gewicht eines Tickets ohne Story Points?" in text and "Sub-Tasks ohne Story Points" not in text and "Wirkung der wählbaren Regeln" not in text          # die Tabelle entsteht erst auf Klick
    assert at.button(key="make_effects") and not [t for t in at.dataframe if "Regel" in t.value.columns]
    at.button(key="make_effects").click().run(timeout=TIMEOUT)
    _ok(at)
    assert "Wirkung der wählbaren Regeln" in " ".join(m.value for m in at.markdown) and at.button(key="hide_effects")
    table = next(t.value for t in at.dataframe if "Regel" in t.value.columns)
    assert list(table["Regel"]) == list(C.UNEST_RULES) and list(table["Gewicht gesamt"]) == [14.0, 14.0, 14.0, 13.0, 13.5, 13.0, 12.0, 11.0]


def test_the_options_box_is_there_before_a_file_is_loaded_without_the_table():
    at = _open()
    box = next(e for e in at.expander if "Berechnungsmöglichkeiten" in e.label)
    assert "Woher kommt das Gewicht eines Tickets ohne Story Points?" in " ".join(m.value for m in box.markdown) and not at.dataframe


def make_deep() -> tuple[Issue, ...]:
    """Drei Ebenen: Initiative I1, darunter Epic E1 mit den Stories S1 (3, Done) und S2 (5, To Do)."""
    return (
        Issue(key="I1", summary="Initiative X", type="Initiative", status="In Progress"),
        Issue(key="E1", summary="Epic A", type="Epic", status="In Progress", parent="I1"),
        Issue(key="S1", type="Story", status="Done", points=3.0, parent="E1"),
        Issue(key="S2", type="Story", status="To Do", points=5.0, parent="E1"),
    )


def test_up_buttons_stand_above_the_selection_in_the_sidebar():
    at = _open(plan_csv(make_deep()))
    at.sidebar.selectbox(key="root").set_value("E1").run(timeout=TIMEOUT)
    assert [b.key for b in at.sidebar.button] == ["nav_top", "nav_up"] and not [b for b in at.main.button if str(b.key).startswith("nav_")]
    elements = [e.key for e in at.sidebar if getattr(e, "key", None) in ("nav_up", "nav_top", "root", "unest_rule")]
    assert elements[:3] == ["nav_top", "nav_up", "root"] and elements[-2:] == ["root", "unest_rule"]


def test_navigation_up_and_down_changes_the_root():
    at = _open(plan_csv(make_deep()))
    assert not [b for b in at.sidebar.button if b.key == "nav_up"]                                   # im ganzen Plan gibt es nichts darüber
    at.sidebar.selectbox(key="root").set_value("E1").run(timeout=TIMEOUT)                   # runter: E1 unter der Initiative
    _ok(at)
    up = at.sidebar.button(key="nav_up")
    assert up.label == "⬆ Eine Stufe hoch: I1: Initiative X" and at.sidebar.button(key="nav_top").label == "⏫ Ganzer Plan" and at.metric[0].value == "37.5 %"          # S1 (3, Done) und S2 (5, To Do)
    up.click().run(timeout=TIMEOUT)                                                         # hoch: I1
    _ok(at)
    assert at.sidebar.selectbox(key="root").value == "I1" and at.metric[0].value == "37.5 %"
    at.sidebar.button(key="nav_up").click().run(timeout=TIMEOUT)                                    # hoch: ganzer Plan
    _ok(at)
    assert at.sidebar.selectbox(key="root").value == "" and at.metric[0].value == "37.5 %" and not [b for b in at.sidebar.button if b.key == "nav_up"]


def test_the_top_button_jumps_to_the_whole_plan_from_a_deep_root():
    at = _open(plan_csv(make_deep()))
    at.sidebar.selectbox(key="root").set_value("E1").run(timeout=TIMEOUT)
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


def test_a_manual_percent_replaces_the_status_and_is_announced():
    data = ("Vorgangsschlüssel;Vorgangsstatus;Hierarchie;Übergeordnetes Element;Story Points;Prozent erledigt (manuell)\nE-1;In Arbeit;Epic;;;\nS-1;To Do;Story;E-1;4;50\nS-2;Done;Story;E-1;6;\n").encode("utf-8")
    at = _open(data)
    _ok(at)
    assert at.metric[0].value == "80.0 %" and at.metric[1].value == "60.0 %"                    # (4 · 0.5 + 6) / 10; nur Done: S-2 (6 von 10)
    assert any("Bei einem zählenden Ticket gilt „Prozent erledigt (manuell)“" in c.value for c in at.caption)
    assert not any("Bei" in c.value and "Prozent erledigt (manuell)" in c.value for c in _open(plan_csv(make_mini())).caption)


def test_a_done_ticket_with_a_rejecting_resolution_does_not_count_and_is_named():
    data = ("Vorgangsschlüssel;Vorgangsstatus;Lösung;Hierarchie;Übergeordnetes Element;Story Points\nE-1;In Arbeit;;Epic;;\nS-1;Done;Fertig;Story;E-1;4\nS-2;Done;Abgelehnt;Story;E-1;6\nS-3;To Do;;Story;E-1;4\n").encode("utf-8")
    at = _open(data)
    _ok(at)
    assert at.metric[0].value == "50.0 %" and at.metric[2].label == "Offenes Gewicht (SP, gesamt 8.00)"                    # S-2 (6) fällt heraus: 4 von 8
    assert any("1 zurückgewiesene Tickets" in c.value and "Lösung: Abgelehnt" in c.value for c in at.caption)


def test_story_points_in_quarters_are_shown_with_two_decimals():
    at = _open("Vorgangsschlüssel;Vorgangsstatus;Hierarchie;Übergeordnetes Element;Story Points\nE-1;In Arbeit;Epic;;\nS-1;To Do;Story;E-1;0,25\nS-2;To Do;Story;E-1;0,5\n".encode("utf-8"))
    _ok(at)
    assert at.metric[2].label == "Offenes Gewicht (SP, gesamt 0.75)" and at.metric[2].value == "0.75"


def test_the_explanation_says_that_only_leaves_count_and_names_the_exceptions():
    at = _open(plan_csv(make_mini()))
    box = next(e for e in at.expander if e.label == "📐 So wird gerechnet")
    text = " ".join(m.value for m in box.markdown)
    for part in ("Die **Blätter** des Ticket-Baums", "Zwischentickets", "gehen nicht ein", "ein Epic auf „Done“ mit offenen Kindern bringt also nichts", "Zurückgewiesen.", "nimmt alle Blätter darunter mit",
                 "Sub-Tasks einer Story", "Alle Kinder zurückgewiesen."):
        assert part in text, part


def test_the_assumptions_box_is_in_the_app_with_the_limits():
    import jira_constants as consts
    at = _open(plan_csv(make_mini()))
    box = next(e for e in at.expander if e.label == "⚠️ Annahmen, Grenzen und bekannte Probleme")
    text = " ".join(m.value for m in box.markdown)
    assert "Nur ein Stichtag" in text and "Obergrenzen" in text and f"{consts.MAX_UPLOAD_MB} MB" in text and f"{consts.MAX_IMPORT_ISSUES} Tickets" in text and f"{consts.TREE_LEVEL_LIMITS[0]} Einträgen" in text and f"{consts.TREE_LEVEL_LIMITS[1]} in der zweiten" in text


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
    assert table["Sprint"].tolist() == ["Sprint 1", "Sprint 2", "(ohne Sprint)", "Summe"] and table["Tickets"].tolist() == [1, 3, 1, 5]
    sub = _open(plan_csv(make_mini()))
    sub.sidebar.selectbox(key="root").set_value("E1").run(timeout=TIMEOUT)
    _ok(sub)
    table = next(t.value for t in sub.dataframe if "Mitgenommene Tickets" in t.value.columns)
    assert table["Sprint"].tolist() == ["Sprint 1", "Sprint 2", "Summe"] and table["Tickets"].tolist() == [1, 1, 2]            # S1 und S2; S2 stand in zwei Sprints und zählt im letzten


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
    assert at.metric[0].value != "45.7 %"
    at.button(key="clear_loaded").click().run(timeout=TIMEOUT)
    assert not at.session_state["overrides"] if "overrides" in at.session_state else True
    at.file_uploader(key=f"upload_{at.session_state['upload_version']}").set_value(("zwei.csv", plan_csv(make_mini()), "text/csv")).run(timeout=TIMEOUT)
    _ok(at)
    assert at.metric[0].value == "45.7 %"


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


def _html_tables(at):
    return [e for e in at.get("html")]


def test_the_copyable_html_table_is_only_made_on_click_and_can_be_hidden_again():
    at = _open(plan_csv(make_mini()))
    _ok(at)
    assert not _html_tables(at) and at.button(key="make_parent")                          # ohne Klick wird keine Tabelle erzeugt und mitgeschickt
    at.button(key="make_parent").click().run(timeout=TIMEOUT)
    _ok(at)
    assert len(_html_tables(at)) == 1 and at.session_state["html_parent"] and at.button(key="hide_parent")
    at.sidebar.selectbox(key="unest_rule").set_value(C.UNEST_ONE).run(timeout=TIMEOUT)      # die erzeugte Tabelle bleibt bei weiteren Änderungen stehen
    assert len(_html_tables(at)) == 1
    at.button(key="hide_parent").click().run(timeout=TIMEOUT)
    assert not _html_tables(at) and at.button(key="make_parent")
    at.button(key="make_parent").click().run(timeout=TIMEOUT)
    at.button(key="clear_loaded").click().run(timeout=TIMEOUT)
    assert "html_parent" not in at.session_state                                            # mit den Daten verschwinden auch die erzeugten Tabellen


def test_the_headline_numbers_explain_themselves_in_a_tooltip():
    at = _open(plan_csv(make_mini()))
    _ok(at)
    helps = [m.help for m in at.metric]
    assert all(helps)
    assert "Gutschrift" in helps[0] and "fertig 100 %" in helps[0] and "Test 90 %" in helps[0] and "Merged oder Review 80 %" in helps[0]
    assert "ohne Teilgutschriften" in helps[1] and "Prozentpunkte" in helps[1]
    assert "1 minus Fortschritt" in helps[2] and "Story Points" in helps[2]


def test_the_effect_of_the_rules_is_only_calculated_on_click_and_can_be_hidden_again():
    at = _open(plan_csv(make_mini()))
    _ok(at)
    assert not [t for t in at.dataframe if "Regel" in t.value.columns]                     # ohne Klick keine Berechnung der elf Varianten
    at.button(key="make_effects").click().run(timeout=TIMEOUT)
    _ok(at)
    assert [t for t in at.dataframe if "Regel" in t.value.columns] and at.session_state["effects_shown"]
    at.sidebar.selectbox(key="unest_rule").set_value(C.UNEST_ONE).run(timeout=TIMEOUT)      # die Tabelle bleibt bei weiteren Änderungen und folgt den Einstellungen
    table = next(t.value for t in at.dataframe if "Zählende Tickets" not in t.value.columns and "Regel" in t.value.columns)
    assert list(table["Regel"]) == list(C.UNEST_RULES)
    at.button(key="hide_effects").click().run(timeout=TIMEOUT)
    assert not [t for t in at.dataframe if "Regel" in t.value.columns] and at.button(key="make_effects")
    at.button(key="make_effects").click().run(timeout=TIMEOUT)
    at.button(key="clear_loaded").click().run(timeout=TIMEOUT)
    assert "effects_shown" not in at.session_state                                         # mit den Daten verschwindet auch der Merker


def test_the_csv_download_is_made_on_click_and_does_not_rerun_the_app():
    import ast
    tree = ast.parse(open(APP_PATH, encoding="utf-8").read())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "download_button"]
    assert len(calls) == 1
    call = calls[0]
    assert isinstance(call.args[1], ast.Lambda)                                              # die Daten sind eine Funktion, die erst beim Klick läuft
    assert {k.arg: getattr(k.value, "value", None) for k in call.keywords}["on_click"] == "ignore"
