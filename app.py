"""Jira-Fortschritt kompakt: Export aus Jira Plans einlesen und den nach Status und Story Points gewichteten Fortschritt zeigen.

Lauffähig mit: streamlit run app.py
"""

import contextlib
from functools import partial

import streamlit as st

import jira_constants as C
import jira_core as A
import jira_plan as J
import jira_tables as T
from jira_charts import build_progress_bars, build_tiles, build_tree_graph, selected_key
from jira_evaluation import Settings, analyse, check_consistency, de, pct, status_list, unestimated_note
from jira_privacy import scrub_streamlit_logs

st.set_page_config(page_title="Jira-Fortschritt", layout="wide")
scrub_streamlit_logs()      # keine Ausnahmemeldungen (können Ticketdaten enthalten) im Protokoll der App

UPLOAD_NOTICE = f"""
**Bitte vor dem Hochladen lesen.** Die Datei geht zur Berechnung an den Server, auf dem diese App läuft (bei einer Veröffentlichung z. B. Streamlit Community Cloud, USA), und liegt dort nur für Ihre
Sitzung im Arbeitsspeicher. Das Werkzeug speichert sie nicht, legt sie nicht zwischen und gibt sie nicht weiter; den Server betreibt aber, wer die App bereitstellt. Laden Sie keine vertraulichen Daten
ohne Freigabe hoch. Höchstens {C.MAX_UPLOAD_MB} MB und {C.MAX_IMPORT_ISSUES} Tickets je Datei. Gebraucht werden nur diese Spalten: Vorgangsschlüssel, Vorgangsstatus, Hierarchie, Übergeordnetes Element
und Story Points (optional Titel, Sprint, Releases, Team, Bereich, Zugewiesene Person, Priorität, Stichwörter, Komponenten). Alle anderen Spalten, besonders Beschreibungen und Kommentare, gehören vor dem
Hochladen gelöscht. Beim Laden lassen sich die Namen der Bearbeiter ersetzen. Für sensible Projekte das Werkzeug lokal ausführen: Es ist Open Source (MIT-Lizenz), Code und Anleitung stehen im [Repository]({C.REPO_URL}).
"""


EXPORT_GUIDE = """
**1. Story Points als Schätzung des Plans einstellen.** Das Werkzeug gewichtet mit Story Points. Die Einheit gilt je Plan: neben dem Namen des Plans in der Seitenleiste **•••** (More actions) →
**Plan settings** → Seite **Estimation and scheduling** → **Story Points**. Falls nötig, das Feld, mit dem die Tickets geschätzt werden, dem Plan hinzufügen. Laut Atlassian gilt dabei: Story Points sind nur wählbar,
wenn alle Teams im Plan Scrum-Teams sind (bei einem Kanban-Team fehlt die Option; das Team auf dem Reiter Teams auf Scrum umstellen), Story Points und Zeitschätzungen (Tage, Stunden) sind nicht austauschbar, und
beim Wechsel der Einheit gehen nicht gespeicherte Schätzungen verloren. Steht der Plan auf Tagen, heißt die Spalte im Export „Schätzung (T)“: Die liest dieses Werkzeug nicht. Die Tickets selbst müssen
Story Points tragen; Tickets ohne Story Points behandelt die Auswahl „Tickets ohne Story Points“ in der Seitenleiste.

**2. Festlegen, was der Export enthält.** Der Export enthält nur, was in der **Timeline-Ansicht** des Plans sichtbar ist. Deshalb zuerst die Filter so setzen, dass genau der Teil des Plans erscheint, der
ausgewertet werden soll (die Hierarchie darüber, z. B. Initiativen, gehört dazu, wenn sie als Wurzel wählbar sein soll), und über **Add fields** die Spalten einblenden: mindestens Vorgangsschlüssel und
Status, außerdem **Story Points** (Gewicht), Hierarchie und Übergeordnetes Element (Aufbau des Baums) und, wenn gewünscht, Titel, Sprint, Releases, Team, Bereich, Zugewiesene Person, Priorität, Stichwörter und
Komponenten. Welche Spalten der Export genau liefert, listet Atlassian nicht auf; die genannten sind die, die dieses Werkzeug aus echten Exporten kennt.

**3. Exportieren.** In der Timeline-Ansicht: **Share** → **Export** → **Export data (.csv)** → **Export**. Gebraucht werden die Rolle Plans administrator oder Plan user und Jira Cloud Premium oder Enterprise.
Die erzeugte CSV-Datei hier hochladen; vorher Spalten wie Beschreibung und Kommentare, falls vorhanden, löschen.

**4. Prüfen.** Nach dem Laden zeigt „Was wurde erkannt?“, bei wie vielen Tickets Story Points stehen. Fehlt die Spalte, steht oben eine Warnung, und alle Tickets wiegen gleich viel.

*Die Menünamen folgen der Dokumentation von Atlassian ([Export](https://support.atlassian.com/jira-software-cloud/docs/export-advanced-roadmaps-plan-data-as-csv/),
[Schätzeinheit](https://support.atlassian.com/jira-software-cloud/docs/change-estimation-units-in-your-plan/), [Spalten](https://support.atlassian.com/jira-software-cloud/docs/add-edit-and-remove-columns-in-advanced-roadmaps/)) in der englischen Oberfläche.
Die deutsche Oberfläche und neuere Versionen können anders heißen; an einer eigenen Jira-Instanz geprüft ist das nicht.*
"""


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


def _on_weight_edit(version, shown, base):
    """Tabelle der Status-Gewichte wurde bearbeitet: Abweichungen vom Namen merken (auch für Status, die gerade nicht zu sehen sind)."""
    edited = st.session_state[f"weights_{version}"].get("edited_rows", {})
    st.session_state["overrides"] = A.edited_overrides(st.session_state.get("overrides", ()), base, shown, edited)
    st.session_state["weights_version"] = version + 1


def _clear_loaded():
    """Löscht die geladenen Daten der Sitzung und stellt das Upload-Feld zurück."""
    st.session_state.pop("loaded", None)
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


st.session_state.setdefault("upload_version", 0)
st.title("📊 Jira-Fortschritt")
st.caption("Wie weit ist ein Teilbaum eines Plans? Gewichtet mit den Story Points der Tickets und ihrem Status: fertig 100 %, Test 90 %, Merged oder Review 80 %, alles andere 0 %; "
           "zurückgewiesene Tickets zählen nicht.")
st.caption(f"🔓 Open Source (MIT-Lizenz): Code und Anleitung im [Repository]({C.REPO_URL}). Mit eigenen, vertraulichen Daten besser lokal ausführen: Dann verlassen sie Ihren Rechner nicht.")

st.warning(UPLOAD_NOTICE)
loaded = st.session_state.get("loaded")
with st.expander("📤 So kommt die Datei zustande: Export aus Jira Plans, mit Story Points", expanded=loaded is None):
    st.markdown(EXPORT_GUIDE)
with st.expander("📖 Welche Status zählen wie viel? Standard nach Namen"):
    st.markdown(T.status_rules_markdown())
options_box = st.expander("🧮 Tickets ohne Story Points: Berechnungsmöglichkeiten")          # die Wirkung auf die Daten kommt nach der Auswertung dazu
with options_box:
    st.markdown(T.UNEST_OPTIONS_MARKDOWN)
pseudo = st.checkbox(
    "Namen der Bearbeiter durch Nummern ersetzen", value=True, key="pseudo", disabled=loaded is not None,
    help="Gilt beim Laden und ersetzt die Namen in den Daten der Sitzung. Diese Fassung zeigt Bearbeiter nirgends an; die Option begrenzt, was im Arbeitsspeicher bleibt. Die Datei hat den Server beim Hochladen schon erreicht.")
if loaded is None:
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
    if pseudo:
        issues_all = J.pseudonymize_assignees(issues_all)
    st.session_state["loaded"] = (upload.name, issues_all, report)
    st.session_state["upload_version"] += 1       # neues Upload-Feld: die Datei steht danach nicht mehr im Formular
    st.rerun()
file_name, issues_all, report = loaded
if not issues_all:
    st.warning("Die Datei enthält keine Tickets.")
    st.button("🗑️ Daten jetzt löschen", on_click=_clear_loaded, key="clear_loaded")
    st.stop()
st.success(f"Geladen: {file_name} mit {len(issues_all)} Tickets. Die Datei selbst behält das Werkzeug nicht; im Arbeitsspeicher dieser Sitzung bleiben nur die für die Berechnung nötigen Felder. "
           "Die Plattform kann die hochgeladene Datei bis zum Ende der Sitzung noch im Speicher halten.")
st.button("🗑️ Daten jetzt löschen", on_click=_clear_loaded, key="clear_loaded", help="Verwirft die geladenen Tickets dieser Sitzung und stellt das Upload-Feld zurück.")
for note in report.notes:
    st.warning(note)
with st.expander(f"🔎 Was wurde erkannt? ({len(issues_all)} Tickets)"):
    st.caption("Welche Spalte wofür gelesen wurde und bei wie vielen Tickets ein Wert steht. Spalten mit „(hochrechnen)“ sind Summen über die Kinder und werden nicht gelesen, ebenso alle weiteren Spalten des Exports.")
    st.dataframe(report.columns, hide_index=True, width="stretch")

# --- Auswahl (Seitenleiste) ----------------------------------------------------------------------------------------------------------------

root_depth = dict(A.root_choices(issues_all))
by_key = {t.key: t for t in issues_all}
root_options = (C.ROOT_ALL, *root_depth)
if st.session_state.get("root", C.ROOT_ALL) not in root_options:        # die Datei hat gewechselt: die alte Wurzel gibt es nicht mehr
    st.session_state["root"] = C.ROOT_ALL


def root_label(key):
    if key == C.ROOT_ALL:
        return "(ganzer Plan)"
    title = by_key[key].summary
    return "↳ " * root_depth[key] + key + (f": {title}" if title else "")


current_root = st.session_state.get("root", C.ROOT_ALL)
with st.sidebar:
    st.header("Teilprojekt")
    if current_root != C.ROOT_ALL:
        up_key = A.parent_root(issues_all, current_root)
        if up_key != C.ROOT_ALL:
            st.button("⏫ Ganzer Plan", on_click=_go_to, args=(C.ROOT_ALL,), key="nav_top", width="stretch")
        st.button("⬆ Eine Stufe hoch: " + root_label(up_key).lstrip("↳ "), on_click=_go_to, args=(up_key,), key="nav_up", width="stretch",
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

with guard("Auswertung"):
    # --- Status-Gewichte -----------------------------------------------------------------------------------------------------------------------

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

    # --- Ergebnis ------------------------------------------------------------------------------------------------------------------------------

    unit = C.UNIT
    settings = Settings(root=root, unest_rule=unest_rule, sub_rule=sub_rule, overrides=overrides)
    a = analyse(issues, settings, issues_all)

    st.markdown("## 🎯 Ergebnis")
    st.caption("Runter: ein Klick auf eine Kachel oder einen Knoten mit Kindern, oder die Auswahl „Teilprojekt“ in der Seitenleiste. Hoch: die Knöpfe oben in der Seitenleiste.")
    for problem in check_consistency(a):
        st.error(f"Interne Prüfung verletzt: {problem}")
    if root != C.ROOT_ALL:
        st.info(f"Die Auswertung ist auf **{root_label(root).lstrip('↳ ')}** und alles darunter beschränkt: {len(issues)} von {len(issues_all)} Tickets, davon {a.n_atoms} zählende.")
    if a.n_excluded:
        bad = sorted({issues[i].status for i in a.rejected_atoms if A.is_rejected_status(issues[i].status)})
        st.caption(f"{a.n_excluded} zurückgewiesene Tickets" + (f" ({', '.join(bad)})" if bad else " (unter einem zurückgewiesenen Ticket)") + " zählen nicht: weder im Gewicht noch in der Anzahl.")


    def na(x, fmt):
        """NaN (kein Gewicht) als Strich zeigen."""
        return "–" if x != x else fmt(x)


    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Fortschritt (nach Status gewichtet)", na(a.progress, pct))
    # Delta immer als „mein Wert minus Referenz“ (Referenz: der gewichtete Fortschritt); die Farbe bleibt neutral, weil kleiner nicht schlechter heißt.
    m2.metric("Nur Done, nach Gewicht", na(a.progress_done, pct),
              delta=None if a.progress != a.progress or a.progress_done != a.progress_done else f"{de(100 * (a.progress_done - a.progress), sign=True)} Punkte", delta_color="off")
    m3.metric("Nur Done, nach Ticketzahl", na(a.progress_count, pct),
              delta=None if a.progress != a.progress or a.progress_count != a.progress_count else f"{de(100 * (a.progress_count - a.progress), sign=True)} Punkte", delta_color="off")
    m4.metric(f"Offenes Gewicht ({unit}, gesamt {de(a.weight, 2)})", de(a.weight * (1 - a.progress) if a.progress == a.progress else 0.0, 2))
    kind, text = unestimated_note(a.n_unestimated, a.n_atoms, unest_rule)
    getattr(st, kind)(text)

    st.markdown("### Fortschritt je Ticket direkt unter " + ("dem Plan" if root == C.ROOT_ALL else "der Wurzel"))
    st.plotly_chart(build_progress_bars(a.stats, unit), width="stretch", key="chart_bars")
    st.caption(f"Balkenlänge = Gewicht der Gruppe. Dunkel: erledigt; hell: durch den Status angerechnet (z. B. 80 % für ein Ticket in Review); grau: offen. Rechts: Fortschritt und Gewicht in {unit}."
               + (f" Gezeigt werden die 30 gewichtsstärksten von {len(a.stats.labels)} Gruppen; die Tabelle unten enthält alle." if len(a.stats.labels) > 30 else ""))

    st.markdown("### 🗺️ Kachelansicht")
    if a.tree.weight[0] > 0:
        tiles_key = f"chart_tiles_{root}"
        st.plotly_chart(build_tiles(a.tree, unit), width="stretch", key=tiles_key, on_select=partial(_drill, tiles_key), selection_mode="points")
        st.caption("Fläche = Gewicht, Farbe = Fortschritt, große Kacheln = Kinder von " + ("Wurzel" if root != C.ROOT_ALL else "Projekt") + ", die kleinen darin = deren Kinder. **Ein Klick auf eine Kachel mit Kindern öffnet sie als Teilprojekt** "
                   "(eine Stufe tiefer, Kacheln ohne Kinder reagieren nicht); mit den Knöpfen in der Seitenleiste geht es wieder hoch. Kacheln ohne Gewicht (zurückgewiesen, ohne Story Points bei „nicht zählen“) fehlen.")
    else:
        st.info("Kein Ticket hat Gewicht; die Kachelansicht bleibt leer. Die Auswahl „Tickets ohne Story Points“ ändern.")

    st.markdown("### 🌳 Hierarchiegraph")
    g = a.tree
    graph_key = f"chart_graph_{root}"
    st.plotly_chart(build_tree_graph(g, unit), width="stretch", key=graph_key, on_select=partial(_drill, graph_key), selection_mode="points")
    st.caption(f"Von links nach rechts: {'das gewählte Teilprojekt' if root != C.ROOT_ALL else 'Plan'} → Ebenen darunter → Tickets. Größe = Gewicht aller zählenden Tickets darunter, Farbe = Fortschritt, "
               "Quadrat = fasst Tickets zusammen, Kreis = Ticket ohne Kinder, grau = nichts messbar. Alle Angaben stehen im Hover. **Ein Klick auf einen Knoten mit Kindern öffnet ihn als Teilprojekt** (ein Blatt reagiert nicht)."
               + (f" Der Graph hätte {g.n_total} Knoten; gezeichnet werden die obersten Ebenen bis Ebene {g.shown_depth} (höchstens {C.GRAPH_MAX_NODES} Knoten). Ein Teilprojekt als Wurzel zeigt mehr Tiefe." if g.hidden.any() else ""))

    # --- Tabellen ------------------------------------------------------------------------------------------------------------------------------

    st.markdown("## 📋 Status-Matrix je Ticket unter " + ("dem Plan" if root == C.ROOT_ALL else "der Wurzel"))
    st.caption(
        "Eine Zeile je Ticket direkt unter der Wurzel (im ganzen Plan die obersten), mit allem darunter: die Summe der Story Points der zählenden Tickets je Status, die Status nach Gewicht geordnet und mit ihrem "
        "Gewicht im Kopf. Zurückgewiesene Tickets stehen in einer eigenen Spalte und fehlen im Total ohne Rejected. „Completed“ ist der Anteil der Status ab 90 % Gewicht am Total ohne Rejected; der Fortschritt ist nach "
        "Status und Story Points gewichtet. Die Tabelle folgt dem Teilprojekt und den Status-Gewichten; als CSV für Excel (Semikolon, Dezimalpunkt) und als Tabelle für Jira oder Confluence zu übernehmen.")


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


    matrix_rows, matrix_status, completed_col = T.status_matrix(issues, a)
    matrix_formats = {name: "%.2f" for name in (*matrix_status, T.REJECTED_COL, T.TOTAL_NET_COL)}
    matrix_formats.update({completed_col: "percent", T.PROGRESS_COL: "percent"})
    show_table(matrix_rows, "parent", matrix_formats, "status-matrix-je-parent")

with options_box, guard("Berechnungsmöglichkeiten"):
    st.markdown("#### Wirkung der wählbaren Regeln auf die geladenen Daten")
    st.caption("Alles andere wie in der aktuellen Auswertung (Teilprojekt, Status-Gewichte); die Auswahl in der Seitenleiste ändert nur, welche Zeile in „Ergebnis“ gilt.")
    show_table(T.unestimated_rule_comparison(issues, a), "rules", {"Fortschritt": "percent", "Gewicht gesamt": "%.2f"}, "wirkung-der-regeln")
    st.markdown("#### Wirkung der Sub-Task-Regeln auf die geladenen Daten")
    show_table(T.subtask_rule_comparison(issues, a), "subrules", {"Fortschritt": "percent", "Gewicht gesamt": "%.2f"}, "wirkung-der-sub-task-regeln")

# --- Erklärung -----------------------------------------------------------------------------------------------------------------------------

with st.expander("🔧 Datenquelle und Datenschutz"):
    st.markdown(
        """
**Plan-Export.** Wie man ihn erzeugt, steht oben unter „So kommt die Datei zustande“. Erkannt werden deutsche und englische Spaltenköpfe: *Vorgangsschlüssel*, *Vorgangsstatus*, *Titel*, *Hierarchie* (als Ticket-Typ; Epic,
Initiative und Thema fassen Tickets zusammen), *Übergeordnetes Element* (als Schlüssel, mit dem Schlüssel am Anfang oder als eindeutiger Titel), *Story Points*, *Sprint*, *Releases*, *Team*, *Bereich*,
*Zugewiesene Person*, *Priorität*, *Stichwörter* und *Komponenten*. Pflicht sind nur Schlüssel und Status; was fehlt, wird oben gemeldet. Spalten mit *(hochrechnen)* sind Summen über die Kinder und werden
übergangen, ebenso die Schätzung in Tagen und alle weiteren Spalten. Der Export enthält weder eine Statuskategorie noch ein Lösungsdatum: Was erledigt ist, folgt allein dem Statusnamen.

**Datenschutz.** Die Datei geht zur Berechnung an den Server der App und wird nur für die Sitzung im Arbeitsspeicher gehalten, nie gespeichert und nie zwischengespeichert; die Plattform kann sie bis zum
Ende der Sitzung noch im Speicher halten. Nach dem Einlesen bleiben nur die berechnungsrelevanten Felder; die Namen der Bearbeiter lassen sich beim Laden durch Nummern ersetzen, und „Daten jetzt löschen“ verwirft die geladenen Tickets. Fehlermeldungen nennen nur den Fehlertyp, und die Ausnahmemeldungen stehen nicht im Protokoll der App (sie könnten Daten enthalten). Es gibt bewusst keine
Anbindung an die Jira-Schnittstelle: Zugangsdaten sollen nie durch dieses Werkzeug laufen. Höchstens 50 MB und 5000 Tickets je Datei. Läuft die App auf dem eigenen Rechner oder im eigenen Netz, verlässt
die Datei es nicht.
"""
    )

with st.expander("📐 So wird gerechnet"):
    st.markdown(
        """
**Was in den Fortschritt eingeht.** Nur die **Blätter** des Ticket-Baums, also Tickets ohne Kinder: Story Points (Gewicht) und Status kommen allein von ihnen. Alles darüber wird nur aufsummiert: Der Fortschritt eines
Tickets, eines Epics oder der Wurzel ist die Summe aus Story Points mal Status-Gewicht aller Blätter darunter, geteilt durch die Summe ihrer Story Points. Story Points und Status der **Zwischentickets** (Epics, Initiativen,
Themen, Stories mit Sub-Tasks) gehen nicht ein; ein Epic auf „Done“ mit offenen Kindern bringt also nichts. Auch die Mediane für Tickets ohne Story Points nehmen nur geschätzte Blätter.

Wo ein Zwischenticket doch eine Rolle spielt:

- **Zurückgewiesen.** Ein Ticket mit Status wie Rejected, Zurückgewiesen, Won't do, Abgelehnt, Cancelled oder Duplicate und alles unter ihm fällt ganz heraus, aus Gewicht und Anzahl. Ist ein Zwischenticket
  zurückgewiesen, zählt sein Status also doch: Er nimmt alle Blätter darunter mit.
- **Sub-Tasks einer Story** (Auswahl in der Seitenleiste). Bei **b** teilt eine geschätzte Story ihre Story Points gleichmäßig auf ihre Sub-Tasks auf, wenn keine Sub-Task eigene Story Points hat; dann fließen die Story Points
  der Story indirekt ein. Bei **c** zählt die Story selbst mit ihren Story Points und ihrem Status, und ihre Sub-Tasks bleiben außen vor.
- **Alle Kinder zurückgewiesen.** Eine Story, deren Sub-Tasks alle zurückgewiesen sind, ist selbst ein Blatt und zählt mit ihren eigenen Story Points und ihrem Status.

**Gewicht** eines Tickets sind seine Story Points. Fehlen sie, entscheidet die Auswahl „Tickets ohne Story Points“: ein Median geschätzter Tickets (A bis F: je Stufe im Teilbaum oder im ganzen Plan, je Ticket-Typ, je Geschwistergruppe, je Team oder eine Rückfallkette; gibt es in der Gruppe kein geschätztes Ticket, gilt 1), 1 Story Point (H) oder nicht zählen, Gewicht 0 (I). Stufe heißt Tiefe im Ticket-Baum ab der Wurzel. Die Varianten mit Vor- und Nachteilen stehen im Ausklapper „Berechnungsmöglichkeiten“, ebenso die drei Möglichkeiten für Sub-Tasks (Auswahl „Sub-Tasks einer Story“).

**Gutschrift** eines Tickets ist der Anteil, den sein Status als getan zählt, nach dem Namen: fertig (Done, Closed, Resolved, Fertig, Erledigt, Released, Deployed, Live, …Prod) 100 %, Test (In Test,
Testing, QA, UAT, Abnahme, Verification) 90 %, Merged sowie Review und Überprüfung 80 %, alles andere 0 %. Verneinungen („Not done“, „Untested“) zählen 0 %. Das ist eine Lesart des Namens, keine Messung;
Status, die anders heißen, lassen sich oben in der Tabelle der Gewichte ändern.

**Fortschritt** einer Gruppe $G$ ist die Summe aus Gewicht mal Gutschrift, geteilt durch die Summe der Gewichte:
"""
    )
    st.markdown("$$P(G) = \\frac{\\sum_{i \\in G} w_i\\, c_i}{\\sum_{i \\in G} w_i}$$")
    st.markdown(
        """
Ein Ticket mit mehreren Werten (Stichwörter, Komponenten, Releases) teilt sich gleichmäßig auf seine Gruppen auf, damit die Summe über alle Gruppen die Gesamtsumme bleibt.

**Teilprojekt.** Die Wurzel macht ein Ticket mit allem darunter zu einem eigenständigen Datensatz: Auch der Median für ungeschätzte Tickets (falls gewählt), die Status der Gewichtstabelle, die Sprints und die
Hierarchiestufen beziehen sich nur auf diesen Teilbaum.

**Annahmen, Grenzen und bekannte Probleme** stehen im nächsten Ausklapper.
"""
    )

with st.expander("⚠️ Annahmen, Grenzen und bekannte Probleme"):
    st.markdown(T.ASSUMPTIONS_MARKDOWN)
