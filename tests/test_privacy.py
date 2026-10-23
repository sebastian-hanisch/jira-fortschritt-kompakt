"""Datenschutz: kein Zwischenspeichern hochgeladener Daten, Wächter bei unerwarteten Fehlern, Filter für das Protokoll, Hinweise vor dem Hochladen, Obergrenzen in der Serverkonfiguration."""

import ast
import io
import logging
import tomllib
from pathlib import Path

import jira_constants as C
import jira_evaluation as ev
import jira_plan as J
import jira_privacy as P
from conftest import make_mini, plan_csv
from test_app import APP_PATH, TIMEOUT, _ok, _open

ROOT = Path(APP_PATH).parent


# ---------------------------------------------------------------- Protokoll-Filter

def _logger_with_filter():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    handler.addFilter(P.ScrubExceptionDetails())
    logger = logging.getLogger("test_privacy_scrub")
    logger.handlers = [handler]
    logger.propagate = False
    return logger, stream


def test_filter_replaces_the_exception_message_but_keeps_type_and_call_stations():
    logger, stream = _logger_with_filter()
    secret = "GEHEIM-12345 Kundenname"      # steht nur als Wert da, nicht in der Quelltextzeile, die der Traceback zeigt
    try:
        raise ValueError(secret)
    except ValueError:
        logger.error("Uncaught app execution", exc_info=True)
    text = stream.getvalue()
    assert "GEHEIM-12345" not in text and "Kundenname" not in text
    assert "Uncaught app execution" in text and "ValueError" in text and P.SUPPRESSED in text and "test_filter_replaces_the_exception_message" in text


def test_filter_leaves_entries_without_an_exception_alone():
    logger, stream = _logger_with_filter()
    logger.warning("alles in Ordnung %s", "ok")
    assert stream.getvalue() == "WARNING alles in Ordnung ok\n"


def test_scrub_streamlit_logs_installs_the_filter_once_on_every_streamlit_handler():
    import streamlit.logger as sl
    sl.get_logger("streamlit.runtime.scriptrunner.exec_code")            # legt den Logger mit eigenem Handler an
    first = P.scrub_streamlit_logs()
    second = P.scrub_streamlit_logs()
    assert first == second and first >= 1
    for logger in P._streamlit_loggers():
        for handler in logger.handlers:
            assert sum(isinstance(f, P.ScrubExceptionDetails) for f in handler.filters) == 1


def test_the_app_installs_the_log_filter_before_the_upload_field():
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    calls = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "scrub_streamlit_logs"]
    uploads = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "file_uploader"]
    assert calls and uploads and min(calls) < min(uploads)


# ---------------------------------------------------------------- Wächter

def test_unexpected_error_in_the_evaluation_shows_only_the_type(monkeypatch):
    def boom(*args, **kwargs):
        raise ValueError("GEHEIM-12345 Kundenname")
    monkeypatch.setattr(ev, "analyse", boom)
    at = _open(plan_csv(make_mini()))
    assert not at.exception
    assert any("Unerwarteter Fehler bei „Auswertung“ (ValueError)" in e.value for e in at.error)
    texts = " ".join([e.value for e in at.error] + [str(m.value) for m in at.markdown] + [c.value for c in at.caption])
    assert "GEHEIM" not in texts and not at.metric


def test_unexpected_error_while_parsing_shows_only_the_type(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("GEHEIM-98765")
    monkeypatch.setattr(J, "read_plan", boom)
    at = _open(plan_csv(make_mini()))
    assert not at.exception and any("RuntimeError" in e.value and "GEHEIM" not in e.value for e in at.error) and not at.metric


# ---------------------------------------------------------------- nichts wird zwischengespeichert, keine Netzwerk- oder Zugangsdaten-Wege

def test_no_caching_no_network_and_no_credential_field_in_the_code():
    for name in ("app.py", "jira_plan.py", "jira_core.py", "jira_evaluation.py", "jira_tables.py", "jira_charts.py", "jira_privacy.py"):
        source = (ROOT / name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert not attrs & {"cache_data", "cache_resource"}, name
        imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        assert not imported & {"requests", "urllib", "http", "httpx", "socket", "aiohttp", "smtplib"}, name
        assert "password" not in source.lower() and "api_token" not in source.lower(), name


# ---------------------------------------------------------------- Hinweise und Konfiguration

def test_notice_before_the_upload_names_the_limits_the_server_and_local_hosting():
    at = _open()
    notice = next(w.value for w in at.warning if "Bitte vor dem Hochladen lesen" in w.value)
    assert f"{C.MAX_UPLOAD_MB} MB" in notice and f"{C.MAX_IMPORT_ISSUES} Tickets" in notice and "Server" in notice and "keine vertraulichen daten" in " ".join(notice.split()).lower()
    assert "Open Source (MIT-Lizenz)" in notice and C.REPO_URL in notice and "lokal ausführen" in notice and "Beschreibungen und Kommentare" in notice


def test_caption_points_to_the_repository_and_local_hosting_and_does_not_claim_local_operation():
    at = _open()
    caption = next(c.value for c in at.caption if "Open Source" in c.value)
    assert "MIT-Lizenz" in caption and C.REPO_URL in caption and "lokal ausführen" in caption
    assert not any("läuft lokal" in c.value for c in at.caption) and not any("verlässt diesen Rechner nicht" in c.value for c in at.caption)


def test_privacy_explanation_is_in_the_data_expander():
    at = _open(plan_csv(make_mini()))
    _ok(at)
    explanation = next(m.value for e in at.expander if "Datenquelle und Datenschutz" in e.label for m in e.markdown)
    for part in ("**Plan-Export.**", "Vorgangsschlüssel", "Story Points", "(hochrechnen)", "**Datenschutz.**", "nie gespeichert und nie zwischengespeichert", "nur der Fehlertyp",
                 "nicht im Protokoll der App", "Zugangsdaten", "50 MB und 5000 Tickets", "eigenen Rechner oder im eigenen Netz"):
        assert part in explanation or part.replace("nur der", "nur den") in explanation, part


def test_server_config_limits_the_upload_size_and_disables_usage_statistics():
    config = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert config["server"]["maxUploadSize"] == C.MAX_UPLOAD_MB == 50
    assert config["browser"]["gatherUsageStats"] is False
    assert TIMEOUT > 0


# ---------------------------------------------------------------- Upload-Lebenslauf, Titel, Bearbeiter

TITLES = ("Vorgangsschlüssel;Vorgangsstatus;Hierarchie;Titel;Übergeordnetes Element;Story Points;Zugewiesene Person\n"
          "E-1;In Arbeit;Epic;Kundenprojekt Alpha;;;\nE-2;To Do;Story;Geheimer Kundenname;E-1;;Erika Mustermann\nE-3;Done;Story;Noch ein Titel;E-1;3;Max Beispiel\n").encode("utf-8")


def test_upload_lifecycle_loads_once_resets_the_uploader_and_can_be_deleted():
    at = _open(plan_csv(make_mini()), name="projekt.csv")
    _ok(at)
    assert any("Geladen: projekt.csv mit 9 Tickets" in s.value for s in at.success)
    assert not at.get("file_uploader") and at.button(key="clear_loaded")           # nach dem Laden gibt es kein Upload-Feld mit der Datei mehr
    assert at.checkbox(key="pseudo").disabled and at.checkbox(key="drop_titles").disabled and at.metric[0].value == "66.7 %"
    at.button(key="clear_loaded").click().run(timeout=TIMEOUT)
    _ok(at)
    assert at.get("file_uploader") and not at.metric and any("Bitte den CSV-Export" in i.value for i in at.info)
    assert not at.checkbox(key="pseudo").disabled and "loaded" not in at.session_state


def test_titles_are_dropped_by_default_but_epic_titles_stay():
    at = _open(TITLES)
    _ok(at)
    assert at.checkbox(key="drop_titles").value is True and at.checkbox(key="pseudo").value is True
    tables = " ".join(t.value.to_string() for t in at.dataframe)
    page = " ".join(str(m.value) for m in at.markdown) + " ".join(c.value for c in at.caption) + tables
    assert "Geheimer Kundenname" not in page and "Noch ein Titel" not in page and "Kundenprojekt Alpha" in tables


def test_titles_and_names_can_be_kept_when_switched_off_before_loading():
    at = _open()
    at.checkbox(key="drop_titles").set_value(False)
    at.checkbox(key="pseudo").set_value(False)
    at.file_uploader(key="upload_0").set_value(("plan.csv", TITLES, "text/csv")).run(timeout=TIMEOUT)
    _ok(at)
    loaded = at.session_state["loaded"][1]
    assert [t.summary for t in loaded] == ["Kundenprojekt Alpha", "Geheimer Kundenname", "Noch ein Titel"] and [t.assignee for t in loaded] == ["", "Erika Mustermann", "Max Beispiel"]


def test_assignee_names_are_replaced_by_numbers_by_default():
    at = _open(TITLES)
    _ok(at)
    loaded = at.session_state["loaded"][1]
    assert [t.assignee for t in loaded] == ["", "Person 1", "Person 2"] and [t.summary for t in loaded] == ["Kundenprojekt Alpha", "", ""]          # Epic-Titel bleiben, Ticket-Titel sind verworfen


# ---------------------------------------------------------------- Anleitung zum Export

def test_export_guide_is_shown_before_the_upload_and_names_the_steps():
    at = _open()
    guide = next(e for e in at.expander if "Export aus Jira Plans" in e.label)
    assert guide.proto.expanded                                                  # ohne Datei steht die Anleitung offen
    text = " ".join(m.value for m in guide.markdown)
    for part in ("Plan settings", "Estimation and scheduling", "Story Points", "Scrum-Teams", "Timeline-Ansicht", "Add fields", "Export data (.csv)", "Schätzung (T)",
                 "Plans administrator", "Premium", "geprüft ist das nicht",
                 "support.atlassian.com/jira-software-cloud/docs/export-advanced-roadmaps-plan-data-as-csv"):
        assert part in text, part


def test_export_guide_is_collapsed_once_a_file_is_loaded():
    at = _open(plan_csv(make_mini()))
    guide = next(e for e in at.expander if "Export aus Jira Plans" in e.label)
    assert not guide.proto.expanded


def test_status_rules_are_shown_before_the_upload():
    at = _open()
    box = next(e for e in at.expander if "Welche Status zählen wie viel" in e.label)
    text = " ".join(m.value for m in box.markdown)
    assert "Regeln" in text and "Auflistung" in text and "Ready4Prod" in text and "zählt nicht" in text
