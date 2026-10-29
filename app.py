"""Jira-Fortschritt kompakt: Export aus Jira Plans einlesen und den nach Status und Story Points gewichteten Fortschritt zeigen.

Lauffähig mit: streamlit run app.py

Aufbau: Die Seite entsteht in `main()` aus einzelnen `render_*`-Schritten in der Reihenfolge, in der sie erscheinen. Die Erklärtexte stehen in `jira_texts.py`.
"""

import contextlib
from functools import partial

import numpy as np
import streamlit as st

import jira_constants as C
import jira_core as A
import jira_plan as J
import jira_tables as T
import jira_texts as texts
from jira_charts import MAX_BARS, build_progress_bars, build_tiles, build_tree_graph, selected_key
from jira_evaluation import (
    Settings,
    analyse,
    check_consistency,
    de,
    delta_points,
    md_escape,
    or_dash,
    pct,
    sprint_stats,
    status_list,
    unestimated_note,
    unrecognized_note,
    unrecognized_statuses,
)
from jira_privacy import scrub_streamlit_logs

st.set_page_config(page_title="Jira-Fortschritt", layout="wide")
scrub_streamlit_logs()      # keine Ausnahmemeldungen (können Ticketdaten enthalten) im Protokoll der App


def _read(data: bytes):
    """Datei einlesen. Bewusst ohne Cache: hochgeladene Daten bleiben nicht im Serverspeicher liegen (tests/test_privacy.py prüft das)."""
    return J.read_plan(data)


@contextlib.contextmanager
def guard(what):
    """Fängt unerwartete Fehler und zeigt nur den Typ: Die Meldung könnte Teile der hochgeladenen Daten enthalten. st.stop() ist keine Exception und läuft durch."""
    try:
        yield
    except Exception as exc:  # noqa: BLE001 - bewusst breit
        st.error(f"Unerwarteter Fehler bei „{what}“ ({type(exc).__name__}). Details zeigt das Werkzeug nicht, weil sie Teile Ihrer Daten enthalten könnten. Bitte Datei und Auswahl prüfen.")
        st.stop()


# --- Rückrufe (Knöpfe, Tabellen, Klicks in Diagramme) --------------------------------------------------------------------------------------------

def _on_weight_edit(version, shown, base):
    """Tabelle der Status-Gewichte wurde bearbeitet: Abweichungen vom Namen merken (auch für Status, die gerade nicht zu sehen sind)."""
    edited = st.session_state[f"weights_{version}"].get("edited_rows", {})
    st.session_state["overrides"] = A.edited_overrides(st.session_state.get("overrides", ()), base, shown, edited)
    st.session_state["weights_version"] = version + 1


def _clear_loaded():
    """Löscht die geladenen Daten der Sitzung und stellt das Upload-Feld zurück."""
    st.session_state.pop("loaded", None)
    st.session_state.pop("overrides", None)          # geänderte Gewichte gehören zu den gelöschten Daten und dürfen nicht in die nächste Datei wandern
    st.session_state["weights_version"] = st.session_state.get("weights_version", 0) + 1
    st.session_state["upload_version"] = st.session_state.get("upload_version", 0) + 1


def _go_to(key):
    """Wurzel der Auswertung wechseln (Klick in ein Diagramm, Knöpfe „hoch“): nur auf ein Ticket mit Kindern, das als Wurzel taugt, oder auf das ganze Projekt; ein Blatt bewirkt nichts."""
    target = A.root_for_click(st.session_state["loaded"][1], key)
    if target is not None:
        st.session_state["root"] = target


def _drill(chart_key):
    """Auswahl in einem Diagramm (Klick): den angeklickten Knoten bzw. die angeklickte Kachel als Wurzel öffnen, wenn sie Kinder hat."""
    try:
        points = st.session_state[chart_key]["selection"]["points"]
    except (KeyError, TypeError):
        return
    key = selected_key(points)
    if key:
        _go_to(key)


def _reset_weights():
    st.session_state["overrides"] = ()
    st.session_state["weights_version"] = st.session_state.get("weights_version", 0) + 1


def show_table(rows, key, formats=None, file_name="tabelle"):
    """Zeigt Zeilen (Wörterbücher) als Tabelle und bietet sie als CSV und zum Einfügen in Jira oder Confluence an. `formats`: Spalte -> Streamlit-Zahlenformat."""
    if not rows:
        st.info("Keine Daten für diese Tabelle.")
        return
    percent = [name for name, fmt in (formats or {}).items() if fmt == "percent" and name in rows[0]]
    # Das Streamlit-Format „percent“ folgt der Sprache des Browsers (Komma); für einen einheitlichen Dezimalpunkt zeigt die Tabelle Prozentwerte als Zahl mit „%“ im Format
    shown = [{**r, **{name: None if r[name] is None else 100 * r[name] for name in percent}} for r in rows]
    config = {name: st.column_config.NumberColumn(format="%.1f %%" if fmt == "percent" else fmt) for name, fmt in (formats or {}).items() if name in rows[0]}
    if "Wirkung" in rows[0]:
        config["Wirkung"] = st.column_config.TextColumn(width="large")
    st.dataframe(shown, hide_index=True, width="stretch", column_config=config, key=f"df_{key}")
    st.download_button("⬇️ Als CSV", T.rows_to_csv(rows), file_name=f"{file_name}.csv", mime="text/csv", key=f"csv_{key}")
    with st.expander("📋 In Jira oder Confluence einfügen"):
        wiki_tab, html_tab = st.tabs(["Wiki-Markup", "Tabelle zum Kopieren"])
        with wiki_tab:
            st.caption("Für Textfelder in Jira (Beschreibung, Kommentar im klassischen Editor) und für Confluence über „Einfügen → Markup“ (Wiki-Markup). Das Kopiersymbol oben rechts im Feld kopiert alles.")
            st.code(T.rows_to_wiki(rows, formats), language=None)
        with html_tab:
            st.caption("Die Tabelle unten markieren, kopieren und in Confluence oder ein Jira-Textfeld einfügen: Sie wird als Tabelle mit Kopfzeile übernommen.")
            st.html(T.rows_to_html(rows, formats))


def _below(root) -> str:
    """„dem Plan“ oder „der Wurzel“ für Überschriften „… direkt unter …“."""
    return "dem Plan" if root == C.ROOT_ALL else "der Wurzel"


# --- Kopf und Datei -----------------------------------------------------------------------------------------------------------------------------

def render_intro(loaded):
    """Titel, Hinweise und Anleitungen. Rückgabe: der Ausklapper der Berechnungsmöglichkeiten (die Wirkung auf die Daten kommt nach der Auswertung hinein)."""
    st.title("📊 Jira-Fortschritt")
    st.caption("Wie weit ist ein Teilbaum eines Plans? Gewichtet mit den Story Points der Tickets und ihrem Status: fertig 100 %, Test 90 %, Merged oder Review 80 %, alles andere 0 %; "
               "zurückgewiesene Tickets zählen nicht.")
    st.caption(f"🔓 Open Source (MIT-Lizenz): Code und Anleitung im [Repository]({C.REPO_URL}). Mit eigenen, vertraulichen Daten besser lokal ausführen: Dann verlassen sie Ihren Rechner nicht.")
    st.warning(texts.UPLOAD_NOTICE)
    with st.expander("📤 So kommt die Datei zustande: Export aus Jira Plans, mit Story Points", expanded=loaded is None):
        st.markdown(texts.EXPORT_GUIDE)
    with st.expander("📖 Welche Status zählen wie viel? Standard nach Namen"):
        st.markdown(texts.status_rules_markdown())
    options_box = st.expander("🧮 Tickets ohne Story Points: Berechnungsmöglichkeiten")
    with options_box:
        st.markdown(texts.UNEST_OPTIONS_MARKDOWN)
    return options_box


def load_file():
    """Upload-Feld, Einlesen und Ablegen in der Sitzung. Endet immer mit `st.stop()` (keine Datei, Fehler) oder `st.rerun()` (Datei geladen)."""
    upload = st.file_uploader("Export aus Jira Plans (CSV)", type=["csv"], key=f"upload_{st.session_state['upload_version']}",
                              help="In Jira Plans: Plan öffnen → Export → CSV. Die Spalten werden an ihren Köpfen erkannt (deutsch oder englisch).")
    if upload is None:
        st.info("Bitte den CSV-Export aus Jira Plans wählen. Gebraucht werden mindestens „Vorgangsschlüssel“ und „Vorgangsstatus“; für die Gewichte „Story Points“, "
                "für die Hierarchie „Hierarchie“ und „Übergeordnetes Element“.")
        st.stop()
    try:
        issues_all, report = _read(upload.getvalue())
    except J.PlanImportError as exc:
        st.error(str(exc))
        st.stop()
    except Exception as exc:  # noqa: BLE001 - bewusst breit: nur der Typ, nie die Meldung
        st.error(f"Die Datei konnte nicht gelesen werden ({type(exc).__name__}). Bitte Format und Spalten prüfen: Erwartet wird der CSV-Export aus Jira Plans.")
        st.stop()
    st.session_state["loaded"] = (upload.name, issues_all, report)
    st.session_state["upload_version"] += 1       # neues Upload-Feld: die Datei steht danach nicht mehr im Formular
    st.rerun()


def render_loaded(file_name, issues_all, report):
    """Meldungen zur geladenen Datei und der Erkennungsbericht; ohne Tickets endet der Lauf hier."""
    if not issues_all:
        st.warning("Die Datei enthält keine Tickets.")
        st.button("🗑️ Daten jetzt löschen", on_click=_clear_loaded, key="clear_loaded")
        st.stop()
    st.success(f"Geladen: {md_escape(file_name)} mit {len(issues_all)} Tickets. Die Datei selbst behält das Werkzeug nicht; im Arbeitsspeicher dieser Sitzung bleiben nur die für die Berechnung nötigen Felder. "
               "Die Plattform kann die hochgeladene Datei bis zum Ende der Sitzung noch im Speicher halten.")
    st.button("🗑️ Daten jetzt löschen", on_click=_clear_loaded, key="clear_loaded", help="Verwirft die geladenen Tickets dieser Sitzung und stellt das Upload-Feld zurück.")
    for note in report.notes:
        st.warning(note)
    with st.expander(f"🔎 Was wurde erkannt? ({len(issues_all)} Tickets)"):
        st.caption("Welche Spalte wofür gelesen wurde und bei wie vielen Tickets ein Wert steht. Spalten mit „(hochrechnen)“ sind Summen über die Kinder und werden nicht gelesen, ebenso alle weiteren Spalten des Exports.")
        st.dataframe(report.columns, hide_index=True, width="stretch")


# --- Auswahl (Seitenleiste) ---------------------------------------------------------------------------------------------------------------------

def root_labeller(issues_all, ctx):
    """Funktion Schlüssel -> Beschriftung der Wurzel-Auswahl (eingerückt nach Tiefe im Baum). `ctx`: Zwischenergebnisse zu `issues_all` (siehe `A.cached`)."""
    root_depth = dict(A.root_choices(issues_all, ctx))
    by_key = {t.key: t for t in issues_all}

    def root_label(key):
        if key == C.ROOT_ALL:
            return "(ganzer Plan)"
        title = by_key[key].summary
        return "↳ " * root_depth[key] + key + (f": {title}" if title else "")
    return root_label


def render_sidebar(issues_all, root_label, ctx):
    """Teilprojekt, Regel für Tickets ohne Story Points und Regel für Sub-Tasks. Rückgabe: Wurzel, die Tickets des Teilprojekts und die beiden Regeln."""
    root_depth = dict(A.root_choices(issues_all, ctx))
    root_options = (C.ROOT_ALL, *root_depth)
    if st.session_state.get("root", C.ROOT_ALL) not in root_options:        # die Datei hat gewechselt: die alte Wurzel gibt es nicht mehr
        st.session_state["root"] = C.ROOT_ALL
    current_root = st.session_state.get("root", C.ROOT_ALL)
    with st.sidebar:
        st.header("Teilprojekt")
        if current_root != C.ROOT_ALL:
            up_key = A.parent_root(issues_all, current_root, ctx)
            if up_key != C.ROOT_ALL:
                st.button("⏫ Ganzer Plan", on_click=_go_to, args=(C.ROOT_ALL,), key="nav_top", width="stretch")
            st.button("⬆ Eine Stufe hoch: " + md_escape(root_label(up_key).lstrip("↳ ")), on_click=_go_to, args=(up_key,), key="nav_up", width="stretch",
                      help="Wechselt zum übergeordneten Ticket, das als Wurzel taugt, sonst zum ganzen Plan.")
        root = st.selectbox(
            "Teilprojekt (Wurzel)", root_options, key="root", format_func=root_label, disabled=not root_depth,
            help="Macht dieses Ticket zur Wurzel: Alles Weitere (Status, Ebenen, Kennzahlen, Diagramme, Tabellen) gilt wie für einen eigenständigen Datensatz aus diesem Ticket und allem darunter.")
        issues = A.scope_issues(issues_all, root)
        st.header("Berechnung und Darstellung")
        unest_rule = st.selectbox(
            "Tickets ohne Story Points", C.UNEST_RULES, key="unest_rule",
            help="Was ein Ticket ohne Story Points wiegt: ein Median geschätzter Tickets (Stufe, Typ, Geschwister, Team oder eine Kette davon), 1 Story Point oder nichts (das Ticket zählt dann nicht im Fortschritt, auch wenn es noch offen ist). Die Buchstaben gehören zu den Varianten im Ausklapper „Berechnungsmöglichkeiten“ oben, dort stehen Vor- und Nachteile.")
        sub_rule = st.selectbox(
            "Sub-Tasks einer Story", C.SUB_RULES, key="sub_rule",
            help="Zählende Tickets sind die Blätter des Baums, bei einer Story also ihre Sub-Tasks. a: Sub-Tasks ohne Story Points bekommen das Gewicht nach der Regel oben, die Story Points der Story fallen weg. "
                 "b: Hat keine Sub-Task eigene Story Points, teilen sie sich die Story Points der Story gleichmäßig. c: Die Story zählt selbst mit ihren Story Points und ihrem Status, die Sub-Tasks bleiben außen vor. "
                 "Vor- und Nachteile stehen im Ausklapper „Berechnungsmöglichkeiten“ oben.")
    return root, issues, unest_rule, sub_rule


# --- Auswertung ---------------------------------------------------------------------------------------------------------------------------------

def render_status_weights(issues):
    """Tabelle der Status-Gewichte (aus dem Namen abgeleitet, änderbar). Rückgabe: die geänderten Gewichte der Status, die in diesen Tickets vorkommen."""
    statuses = status_list(issues)
    base = tuple(A.status_credits(statuses).items())
    overrides = tuple((s, c) for s, c in st.session_state.get("overrides", ()) if s in statuses)
    shown = tuple(A.status_credits(statuses, overrides).items())
    version = st.session_state.get("weights_version", 0)
    with st.expander(f"⚖️ Gewichte der Status ({len(statuses)}) – aus dem Namen abgeleitet, änderbar"):
        st.caption("Anteil der Arbeit, der bei diesem Status als getan gilt: Namen, die nach fertig klingen (Done, Closed, Fertig, Ready4Prod …), zählen 100 %, nach Test 90 %, nach Merged oder Review 80 %, "
                   "alles andere 0 %. Die Regeln und Beispielnamen stehen oben unter „Welche Status zählen wie viel?“. Heißt ein Status anders, hier ändern. Zurückgewiesene Status (Rejected, Zurückgewiesen, Won't do …) zählen nicht mit, egal was hier steht.")
        rejected_names = [s for s in statuses if A.is_rejected_status(s)]
        if rejected_names:
            st.caption(f"Zurückgewiesen: {', '.join(rejected_names)}.")
        if overrides:
            st.button("↩️ Gewichte nach Namen wiederherstellen", on_click=_reset_weights, key="reset_weights")
        st.data_editor([{"Status": s, "Gewicht (%)": round(100 * c, 1)} for s, c in shown], disabled=["Status"], hide_index=True, key=f"weights_{version}",
                       on_change=_on_weight_edit, args=(version, shown, base), column_config={"Gewicht (%)": st.column_config.NumberColumn(min_value=0, max_value=100, step=5, format="%.0f")})
    return overrides


def render_headline(a, issues, issues_all, root, root_label, unest_rule):
    """Überschrift „Ergebnis“, Hinweise und die vier Kennzahlen."""
    st.markdown("## 🎯 Ergebnis")
    st.caption("Runter: ein Klick auf eine Kachel oder einen Knoten mit Kindern, oder die Auswahl „Teilprojekt“ in der Seitenleiste. Hoch: die Knöpfe oben in der Seitenleiste.")
    for problem in check_consistency(a):
        st.error(f"Interne Prüfung verletzt: {problem}")
    if root != C.ROOT_ALL:
        st.info(f"Die Auswertung ist auf **{md_escape(root_label(root).lstrip('↳ '))}** und alles darunter beschränkt: {len(issues)} von {len(issues_all)} Tickets, davon {a.n_atoms} zählende.")
    if a.n_excluded:
        bad = sorted({issues[i].status for i in a.rejected_atoms if A.is_rejected_status(issues[i].status)})
        st.caption(f"{a.n_excluded} zurückgewiesene Tickets" + (f" ({', '.join(md_escape(s) for s in bad)})" if bad else " (unter einem zurückgewiesenen Ticket)") + " zählen nicht: weder im Gewicht noch in der Anzahl.")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Fortschritt (nach Status gewichtet)", or_dash(a.progress, pct))
    # Delta immer als „mein Wert minus Referenz“ (Referenz: der gewichtete Fortschritt); die Farbe bleibt neutral, weil kleiner nicht schlechter heißt.
    m2.metric("Nur Done, nach Gewicht", or_dash(a.progress_done, pct), delta=delta_points(a.progress_done, a.progress), delta_color="off")
    m3.metric("Nur Done, nach Ticketzahl", or_dash(a.progress_count, pct), delta=delta_points(a.progress_count, a.progress), delta_color="off")
    m4.metric(f"Offenes Gewicht ({C.UNIT}, gesamt {de(a.weight, 2)})", de(0.0 if np.isnan(a.progress) else a.weight * (1 - a.progress), 2))
    kind, text = unestimated_note(a.n_unestimated, a.n_atoms, unest_rule)
    getattr(st, kind)(text)
    unknown = unrecognized_note(unrecognized_statuses(issues, a), a.weight)
    if unknown:
        st.warning(unknown)


def render_charts(a, root):
    """Balken je Ticket unter der Wurzel, Kachelansicht und Teilprojektbaum (die beiden letzten mit Klick-Navigation)."""
    unit = C.UNIT
    st.markdown("### Fortschritt je Ticket direkt unter " + _below(root))
    st.plotly_chart(build_progress_bars(a.stats, unit), width="stretch", key="chart_bars")
    st.caption(f"Balkenlänge = Gewicht der Gruppe. Dunkel: erledigt; hell: durch den Status angerechnet (z. B. 80 % für ein Ticket in Review); grau: offen. Rechts: Fortschritt und Gewicht in {unit}."
               + (f" Gezeigt werden die {MAX_BARS} gewichtsstärksten von {len(a.stats.labels)} Gruppen; die Tabelle unten enthält alle." if len(a.stats.labels) > MAX_BARS else ""))

    st.markdown("### 🗺️ Kachelansicht")
    if a.tree.weight[0] > 0:
        tiles_key = f"chart_tiles_{root}"
        st.plotly_chart(build_tiles(a.tree, unit), width="stretch", key=tiles_key, on_select=partial(_drill, tiles_key), selection_mode="points")
        st.caption("Fläche = Gewicht, Farbe = Fortschritt, große Kacheln = Kinder von " + ("Wurzel" if root != C.ROOT_ALL else "Projekt") + ", die kleinen darin = deren Kinder. **Ein Klick auf eine Kachel mit Kindern öffnet sie als Teilprojekt** "
                   "(eine Stufe tiefer, Kacheln ohne Kinder reagieren nicht); mit den Knöpfen in der Seitenleiste geht es wieder hoch. Kacheln ohne Gewicht (zurückgewiesen, ohne Story Points bei „nicht zählen“) fehlen.")
    else:
        st.info("Kein Ticket hat Gewicht; die Kachelansicht bleibt leer. Die Auswahl „Tickets ohne Story Points“ ändern.")

    st.markdown("### 🌳 Teilprojektbaum")
    g = a.tree
    graph_key = f"chart_graph_{root}"
    st.plotly_chart(build_tree_graph(g, unit), width="stretch", key=graph_key, on_select=partial(_drill, graph_key), selection_mode="points")
    st.caption(f"Von links nach rechts: {'das gewählte Teilprojekt' if root != C.ROOT_ALL else 'Plan'} → Ebenen darunter → Tickets. Größe = Gewicht aller zählenden Tickets darunter, Farbe = Fortschritt, "
               "Quadrat = fasst Tickets zusammen, Kreis = Ticket ohne Kinder, grau = nichts messbar. Alle Angaben stehen im Hover. **Ein Klick auf einen Knoten mit Kindern öffnet ihn als Teilprojekt** (ein Blatt reagiert nicht)."
               + (f" Der Teilprojektbaum hätte {g.n_total} Knoten; gezeichnet werden die obersten Ebenen bis Ebene {g.shown_depth} (höchstens {C.GRAPH_MAX_NODES} Knoten). Ein Teilprojekt als Wurzel zeigt mehr Tiefe." if g.hidden.any() else ""))


def render_matrix(issues, a, root):
    """Status-Matrix je Ticket unter der Wurzel mit CSV- und Wiki-Ausgabe."""
    st.markdown("## 📋 Status-Matrix je Ticket unter " + _below(root))
    st.caption(
        "Eine Zeile je Ticket direkt unter der Wurzel (im ganzen Plan die obersten), mit allem darunter: die Summe der Story Points der zählenden Tickets je Status, die Status nach Gewicht geordnet und mit ihrem "
        "Gewicht im Kopf. Zurückgewiesene Tickets stehen in einer eigenen Spalte und fehlen im Total ohne Rejected. „Completed“ ist der Anteil der Status ab 90 % Gewicht am Total ohne Rejected; der Fortschritt ist nach "
        "Status und Story Points gewichtet. Die Tabelle folgt dem Teilprojekt und den Status-Gewichten; als CSV für Excel (Semikolon, Dezimalkomma) und als Tabelle für Jira oder Confluence zu übernehmen.")
    matrix_rows, matrix_status, completed_col = T.status_matrix(issues, a)
    matrix_formats = {name: "%.2f" for name in (*matrix_status, T.REJECTED_COL, T.TOTAL_NET_COL)}
    matrix_formats.update({completed_col: "percent", T.PROGRESS_COL: "percent"})
    show_table(matrix_rows, "parent", matrix_formats, "status-matrix-je-parent")


def render_sprints(issues, a):
    """Fortschritt je Sprint (Balken und Tabelle); nur wenn mindestens ein Ticket einen Sprint hat."""
    if not T.has_sprints(issues):
        return
    st.markdown("## 🏃 Fortschritt je Sprint")
    st.caption(
        "Jedes zählende Ticket steht in seinem **letzten** Sprint (Jira führt übernommene Tickets mit allen ihren Sprints, der letzte ist der aktuelle); ein Ticket ohne Sprint, etwa eine Sub-Task, übernimmt den Sprint des nächsten "
        "übergeordneten Tickets, das einen hat. „Mitgenommen“ sind Tickets, die schon in einem früheren Sprint standen; sie zählen nur im letzten. Der Export enthält keinen Statusverlauf: Die Zahlen zeigen den Stand heute je Sprint, "
        "nicht, was am Ende des Sprints erreicht war. Gewicht, Gutschrift und Teilprojekt wie in der Auswertung oben.")
    st.plotly_chart(build_progress_bars(sprint_stats(issues, a), C.UNIT), width="stretch", key="chart_sprints")
    formats = {T.SPRINT_WEIGHT_COL: "%.2f", T.PROGRESS_COL: "percent", T.SPRINT_DONE_COL: "percent", T.CARRIED_WEIGHT_COL: "%.2f"}
    show_table(T.sprint_rows(issues, a), "sprints", formats, "fortschritt-je-sprint")


def render_rule_effects(issues, a):
    """Wirkung der wählbaren Regeln auf die geladenen Daten (im Ausklapper „Berechnungsmöglichkeiten“)."""
    st.markdown("#### Wirkung der wählbaren Regeln auf die geladenen Daten")
    st.caption("Alles andere wie in der aktuellen Auswertung (Teilprojekt, Status-Gewichte); die Auswahl in der Seitenleiste ändert nur, welche Zeile in „Ergebnis“ gilt.")
    show_table(T.unestimated_rule_comparison(issues, a), "rules", {"Fortschritt": "percent", "Gewicht gesamt": "%.2f"}, "wirkung-der-regeln")
    st.markdown("#### Wirkung der Sub-Task-Regeln auf die geladenen Daten")
    show_table(T.subtask_rule_comparison(issues, a), "subrules", {"Fortschritt": "percent", "Gewicht gesamt": "%.2f"}, "wirkung-der-sub-task-regeln")


def render_explanations():
    st.expander("🔧 Datenquelle und Datenschutz").markdown(texts.DATA_SOURCE_MARKDOWN)
    with st.expander("📐 So wird gerechnet"):
        st.markdown(texts.HOW_IT_WORKS_BEFORE_FORMULA)
        st.markdown("$$P(G) = \\frac{\\sum_{i \\in G} w_i\\, c_i}{\\sum_{i \\in G} w_i}$$")
        st.markdown(texts.HOW_IT_WORKS_AFTER_FORMULA)
    st.expander("⚠️ Annahmen, Grenzen und bekannte Probleme").markdown(texts.ASSUMPTIONS_MARKDOWN)


def main():
    st.session_state.setdefault("upload_version", 0)
    loaded = st.session_state.get("loaded")
    options_box = render_intro(loaded)
    if loaded is None:
        load_file()
        return
    file_name, issues_all, report = loaded
    render_loaded(file_name, issues_all, report)
    all_ctx: dict = {}            # Zwischenergebnisse zum ganzen Plan (Baumreihenfolge), nur für diesen Durchlauf
    root_label = root_labeller(issues_all, all_ctx)
    root, issues, unest_rule, sub_rule = render_sidebar(issues_all, root_label, all_ctx)
    with guard("Auswertung"):
        overrides = render_status_weights(issues)
        a = analyse(issues, Settings(root=root, unest_rule=unest_rule, sub_rule=sub_rule, overrides=overrides), issues_all)
        render_headline(a, issues, issues_all, root, root_label, unest_rule)
        render_charts(a, root)
        render_matrix(issues, a, root)
        render_sprints(issues, a)
    with options_box, guard("Berechnungsmöglichkeiten"):
        render_rule_effects(issues, a)
    render_explanations()


main()
