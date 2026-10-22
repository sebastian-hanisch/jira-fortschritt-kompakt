# Jira-Fortschritt kompakt

Schlanke Fassung von `jira-fortschritt-intern` für den täglichen Gebrauch: Sie liest **nur den CSV-Export aus Jira Plans**, rechnet den Fortschritt eines Plans oder
Teilbaums nach **Status und Schätzung** gewichtet und zeigt ihn als Kennzahlen, Balken, Hierarchiegraph und Tabellen, die sich direkt in Jira oder Confluence einfügen lassen.
Es gibt keine Beispieldaten, keinen Upload-Dienst und keine Rechenoptionen: Die Annahmen stehen fest und sind unten beschrieben.

## Starten

```bash
pip install -r requirements.txt
streamlit run app.py
```

Alles läuft lokal; die Datei verlässt den Rechner nicht. Tests: `pip install -r requirements-dev.txt`, dann `python -m pytest tests`.

## Eingabe

CSV-Export aus Jira Plans (Plan öffnen → Export → CSV, deutsche oder englische Oberfläche, Semikolon oder Komma). Die Spalten werden an ihren Köpfen erkannt:

| Feld | Spalte (deutsch) |
|---|---|
| Schlüssel (Pflicht) | Vorgangsschlüssel |
| Status (Pflicht) | Vorgangsstatus |
| Typ / Hierarchie | Hierarchie |
| Eltern | Übergeordnetes Element (als Schlüssel, Schlüssel mit Titel oder eindeutiger Titel) |
| Schätzung | Schätzung (T), die Einheit ist dann Tage; stehen daneben Story Points, gelten nur sie |
| weitere | Titel, Sprint, Releases, Team, Bereich, Zugewiesene Person, Priorität, Stichwörter, Komponenten |

Spalten mit „(hochrechnen)“ sind Summen über die Kinder und werden übergangen, ebenso alle anderen Spalten. Der Export enthält weder Statusverlauf noch Lösungsdatum:
Es gibt deshalb keinen Verlauf über die Zeit und keine Prognose. Was nicht gelesen werden konnte, meldet die App oben, bevor sie eine Zahl zeigt.

## Was zählt

* **Zählende Tickets:** Story, Task und Bug. Epics, Initiativen, Themen und Sub-Tasks fassen zusammen und zählen nicht selbst.
* **Gewicht:** die Schätzung des Tickets; fehlt sie, der Median der geschätzten Tickets (im gewählten Teilbaum und Zeitraum).
* **Gutschrift nach Statusname** (deutsch und englisch): fertig (Done, Closed, Fertig, Released, Ready4Prod …) 100 %, Test (In Test, QA, Abnahme, Ready4Test …) 90 %,
  Merged sowie Review und Überprüfung 80 %, alles andere 0 %. Verneinungen („Not done“, „Untested“) zählen 0 %.
* **Zurückgewiesen** (Rejected, Zurückgewiesen, Won't do, Abgelehnt, Cancelled, Duplicate …): das Ticket und alles darunter zählen nicht, weder im Gewicht noch in der Anzahl.
* **Fortschritt** einer Gruppe: Summe aus Gewicht mal Gutschrift, geteilt durch die Summe der Gewichte.

Die Gewichte der Status stehen in einer Tabelle (Ausklapper „Gewichte der Status“) und lassen sich dort ändern, wenn ein Status anders heißt, als sein Name vermuten lässt.
Sonst gibt es nichts einzustellen.

## Auswahl (Seitenleiste)

* **Teilprojekt (Wurzel):** macht ein Ticket mit allem darunter zu einem eigenständigen Datensatz; auch Median, Status, Sprints und Hierarchiestufen beziehen sich dann nur auf diesen Teilbaum.
* **Zeitraum von Sprint … bis Sprint …**, optional mit den Tickets ohne Sprint (es zählt der letzte Sprint eines Tickets).
* **Zusammenfassen nach:** Epic, Hierarchiestufe, Sprint, Release, Komponente, Label, Bearbeiter, Team, Bereich, Priorität, Ticket-Typ oder Status.

## Ausgabe

Kennzahlen (nach Status gewichtet, nur Done nach Gewicht, nur Done nach Ticketzahl, offenes Gewicht), Fortschrittsbalken, Hierarchiegraph und vier Tabellen: **Status-Matrix je Parent**
(Summe der Schätzungen je Status mit dem Gewicht im Kopf, Epic-Schätzung gegen Total, Rejected getrennt, Completed ab 90 % und gewichteter Fortschritt), Je Gruppe, Status × Gruppe und
Datenqualität. Jede Tabelle gibt es als CSV für Excel (Semikolon, Dezimalkomma) und als Wiki-Markup bzw. HTML-Tabelle zum Einfügen in Jira und Confluence.

## Bewusst nicht enthalten

Gegenüber `jira-fortschritt-intern`: Beispieldaten, JSON- und Standard-CSV-Export, Wahl des Gewichtsschemas, der Zählebene und der Gewichtung, Sub-Task-Mischung, Kreuztabelle,
Treemap, Verlauf (Burn-up), Sensitivitätsprüfung, JQL-Hilfe, Zusammenfassung zum Kopieren, Datenschutzoptionen (die App läuft lokal).

## Aufbau

| Datei | Inhalt |
|---|---|
| `app.py` | Oberfläche (Streamlit) |
| `jira_plan.py` | Einlesen des Plan-Exports |
| `jira_core.py` | Statusklassen, Hierarchie, Gewichte, Gruppen, Hierarchiegraph |
| `jira_evaluation.py` | `analyse`: Kennzahlen aus Auswahl und Gewichten, interne Konsistenzprüfung |
| `jira_tables.py` | Tabellen und Ausgabe als CSV, Wiki-Markup, HTML |
| `jira_charts.py` | Plotly-Diagramme |
| `tests/` | Tests an einer von Hand gerechneten Mini-Instanz, Zufallsprojekte für Summen und Grenzen, App-Tests mit AppTest |
