# Jira-Fortschritt kompakt

Schlanke Fassung eines ausführlicheren Auswertungswerkzeugs für den täglichen Gebrauch: Sie liest **nur den CSV-Export aus Jira Plans**, rechnet den Fortschritt eines Plans oder
Teilbaums nach **Status und Story Points** gewichtet und zeigt ihn als Kennzahlen, Balken, Hierarchiegraph und Tabellen, die sich direkt in Jira oder Confluence einfügen lassen.
Es gibt keine Beispieldaten und nur wenige Rechenoptionen: Die Annahmen stehen fest und sind unten beschrieben.

## Starten

```bash
pip install -r requirements.txt
streamlit run app.py
```

Tests: `pip install -r requirements-dev.txt`, dann `python -m pytest tests`.

## Eingabe

CSV-Export aus Jira Plans (deutsche oder englische Oberfläche, Semikolon oder Komma); wie man ihn erzeugt, steht im nächsten Abschnitt. Die Spalten werden an ihren Köpfen erkannt:

| Feld | Spalte (deutsch) |
|---|---|
| Schlüssel (Pflicht) | Vorgangsschlüssel |
| Status (Pflicht) | Vorgangsstatus |
| Typ / Hierarchie | Hierarchie |
| Eltern | Übergeordnetes Element (als Schlüssel, Schlüssel mit Titel oder eindeutiger Titel) |
| Gewicht | Story Points (die Schätzung in Tagen, „Schätzung (T)“, wird nicht gelesen) |
| weitere | Titel, Sprint, Releases, Team, Bereich, Zugewiesene Person, Priorität, Stichwörter, Komponenten |

Spalten mit „(hochrechnen)“ sind Summen über die Kinder und werden übergangen, ebenso alle anderen Spalten. Der Export enthält weder Statusverlauf noch Lösungsdatum:
Es gibt deshalb keinen Verlauf über die Zeit und keine Prognose. Was nicht gelesen werden konnte, meldet die App oben, bevor sie eine Zahl zeigt.

## Daten aus Jira Plans exportieren

Die App zeigt diese Anleitung auch vor dem Hochladen. Menünamen nach der Dokumentation von Atlassian (englische Oberfläche); die deutsche Oberfläche und neuere Versionen können anders heißen, an einer eigenen
Instanz geprüft ist das nicht.

1. **Story Points als Schätzung des Plans einstellen.** Neben dem Namen des Plans **•••** (More actions) → **Plan settings** → **Estimation and scheduling** → **Story Points**; falls nötig, das Schätzfeld dem Plan
   hinzufügen. Laut Atlassian sind Story Points nur wählbar, wenn alle Teams im Plan Scrum-Teams sind (bei einem Kanban-Team fehlt die Option), Story Points und Zeitschätzungen (Tage, Stunden) sind nicht
   austauschbar, und beim Wechsel gehen nicht gespeicherte Schätzungen verloren. Steht der Plan auf Tagen, heißt die Spalte „Schätzung (T)“, und die liest dieses Werkzeug nicht. Die Tickets selbst müssen Story Points tragen.
2. **Festlegen, was der Export enthält.** Der Export enthält nur, was in der **Timeline-Ansicht** sichtbar ist: Filter auf den auszuwertenden Teil des Plans setzen (inklusive der Ebenen darüber, wenn sie als Wurzel
   wählbar sein sollen) und über **Add fields** mindestens Vorgangsschlüssel, Status, **Story Points**, Hierarchie und Übergeordnetes Element einblenden, optional Titel, Sprint, Releases, Team, Bereich,
   Zugewiesene Person, Priorität, Stichwörter und Komponenten.
3. **Exportieren:** in der Timeline-Ansicht **Share** → **Export** → **Export data (.csv)** → **Export**. Gebraucht werden die Rolle Plans administrator oder Plan user und Jira Cloud Premium oder Enterprise.
4. **Prüfen:** Unter „Was wurde erkannt?“ zeigt die App, bei wie vielen Tickets Story Points stehen; fehlt die Spalte, warnt sie.

Quellen: [Export](https://support.atlassian.com/jira-software-cloud/docs/export-advanced-roadmaps-plan-data-as-csv/), [Schätzeinheit](https://support.atlassian.com/jira-software-cloud/docs/change-estimation-units-in-your-plan/),
[Spalten](https://support.atlassian.com/jira-software-cloud/docs/add-edit-and-remove-columns-in-advanced-roadmaps/).

## Was zählt

* **Zählende Tickets:** die Blätter des Ticket-Baums, also Tickets ohne Kinder (Stories, Tasks und Bugs ohne Sub-Tasks und die Sub-Tasks selbst). Epics, Initiativen und Themen zählen nie selbst; eine Story mit Sub-Tasks
  zählt durch ihre Sub-Tasks, ihre eigenen Story Points und ihr eigener Status zählen dann nicht.
* **Gewicht:** die Story Points des Tickets; fehlen sie, entscheidet die Auswahl „Tickets ohne Story Points“: Median der Tickets mit Story Points auf gleicher Stufe des Baums (Voreinstellung; gibt es auf der Stufe keines, gilt 1; im gewählten Teilbaum), 1 Story Point oder nicht zählen.
* **Gutschrift nach Statusname** (deutsch und englisch): fertig (Done, Closed, Fertig, Released, Ready4Prod …) 100 %, Test (In Test, QA, Abnahme, Ready4Test …) 90 %,
  Merged sowie Review und Überprüfung 80 %, alles andere 0 %. Verneinungen („Not done“, „Untested“) zählen 0 %.
* **Zurückgewiesen** (Rejected, Zurückgewiesen, Won't do, Abgelehnt, Cancelled, Duplicate …): das Ticket und alles darunter zählen nicht, weder im Gewicht noch in der Anzahl.
* **Fortschritt** einer Gruppe: Summe aus Gewicht mal Gutschrift, geteilt durch die Summe der Gewichte.

Die Regeln stehen auch in der App (Ausklapper „Welche Status zählen wie viel?“). Reihenfolge der Prüfung, der erste Treffer gilt: zurückgewiesen (zählt nicht), Verneinung (0 %), fertig (100 %), Merged (80 %),
Test (90 %), Review (80 %), alles andere 0 %; die Namen der Klassen stehen in der App. Die Gewichte der Status stehen in einer Tabelle (Ausklapper „Gewichte der Status“) und lassen sich dort ändern, wenn ein Status anders heißt, als sein Name vermuten lässt.
Sonst gibt es nichts einzustellen.

## Auswahl (Seitenleiste)

* **Teilprojekt (Wurzel):** macht ein Ticket mit allem darunter zu einem eigenständigen Datensatz; auch Median, Status und Hierarchiestufen beziehen sich dann nur auf diesen Teilbaum.
* **Tickets ohne Story Points:** Median der geschätzten Tickets auf gleicher Stufe, als 1 Story Point oder nicht zählen. Die Meldung unter den Kennzahlen nennt, wie viele Tickets betroffen sind.
* **Zusammenfassen nach:** Epic, Hierarchiestufe, Sprint, Release, Komponente, Label, Bearbeiter, Team, Bereich, Priorität, Ticket-Typ oder Status.

## Ausgabe

Kennzahlen (nach Status gewichtet, nur Done nach Gewicht, nur Done nach Ticketzahl, offenes Gewicht), Fortschrittsbalken, Hierarchiegraph und vier Tabellen: **Status-Matrix je Parent**
(Summe der Story Points je Status mit dem Gewicht im Kopf, Epic-level Story Points gegen Total, Rejected getrennt, Completed ab 90 % und gewichteter Fortschritt), Je Gruppe, Status × Gruppe und
Datenqualität. Jede Tabelle gibt es als CSV für Excel (Semikolon, Dezimalkomma) und als Wiki-Markup bzw. HTML-Tabelle zum Einfügen in Jira und Confluence.

## Datenschutz

* **Hochgeladene Dateien liegen für die Sitzung im Arbeitsspeicher des Servers, auf dem die App läuft** (bei einer Veröffentlichung z. B. Streamlit Community Cloud, USA). Das Werkzeug speichert und cached sie nicht
  (kein `st.cache_data`, kein Schreiben auf die Platte), gibt sie nicht weiter und hat keine Anbindung an die Jira-Schnittstelle und kein Eingabefeld für Zugangsdaten. Die Plattform kann die Datei bis zum
  Sitzungsende im Speicher halten; den Server betreibt, wer die App bereitstellt.
* Nach dem Einlesen bleiben nur die berechnungsrelevanten Felder. Beim Laden lassen sich die Namen der Bearbeiter durch Nummern ersetzen und die Titel der Tickets (außer Epics) verwerfen (beides ist voreingestellt); „Daten jetzt löschen“
  verwirft die geladenen Tickets der Sitzung und stellt das Upload-Feld zurück. Das betrifft nur Anzeige und Tabellen: Die Datei hat den Server beim Hochladen schon erreicht.
* Fehlermeldungen nennen nur den Fehlertyp, und ein Filter ersetzt die Meldung unbehandelter Ausnahmen im Protokoll durch den Typ (sie könnte Ticketdaten enthalten). Das ist nur gegen die eigene Testsuite
  geprüft, nicht gegen die Server einer Plattform.
* Obergrenzen: 50 MB (`server.maxUploadSize`) und 5000 Tickets je Datei. Vor dem Hochladen weist die App darauf hin, nur die gebrauchten Spalten zu exportieren.
* **Keine vertraulichen Daten ohne Freigabe auf einem fremden Server auswerten. Für sensible Projekte lokal ausführen:** Dann bleibt die Datei auf dem eigenen Rechner (oder im eigenen Netz, wenn die App dort
  betrieben wird), es gibt weder einen Upload an einen fremden Server noch ein Protokoll bei einem Anbieter.

```bash
streamlit run app.py --server.address localhost
```

Mit `--server.address localhost` hört die App nur auf dem eigenen Rechner (`http://localhost:8501`); ohne diese Angabe ist sie standardmäßig auch im lokalen Netz erreichbar.

## Bewusst nicht enthalten

Gegenüber der ausführlicheren Fassung fehlen: Beispieldaten, JSON- und Standard-CSV-Export, Wahl des Gewichtsschemas, der Zählebene und der Gewichtungsart (Story Points oder Ticketanzahl), Zeitraum (Sprint von … bis …), Sub-Task-Mischung, Kreuztabelle,
Treemap, Verlauf (Burn-up), Sensitivitätsprüfung, JQL-Hilfe, Zusammenfassung zum Kopieren.

## Aufbau

| Datei | Inhalt |
|---|---|
| `app.py` | Oberfläche (Streamlit) |
| `jira_plan.py` | Einlesen des Plan-Exports, Titel verwerfen, Bearbeiter ersetzen |
| `jira_core.py` | Statusklassen, Hierarchie, Gewichte, Gruppen, Hierarchiegraph |
| `jira_evaluation.py` | `analyse`: Kennzahlen aus Auswahl und Gewichten, interne Konsistenzprüfung |
| `jira_tables.py` | Tabellen und Ausgabe als CSV, Wiki-Markup, HTML |
| `jira_charts.py` | Plotly-Diagramme |
| `jira_privacy.py` | Filter, der Ausnahmemeldungen aus dem Protokoll nimmt |
| `tests/` | Tests an einer von Hand gerechneten Mini-Instanz, Zufallsprojekte für Summen und Grenzen, App-Tests mit AppTest |

## Lizenz

Open Source unter der [MIT-Lizenz](LICENSE).
