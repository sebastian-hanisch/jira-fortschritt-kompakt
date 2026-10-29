# Jira-Fortschritt kompakt

Schlanke Fassung eines ausführlicheren Auswertungswerkzeugs für den täglichen Gebrauch: Sie liest **nur den CSV-Export aus Jira Plans**, rechnet den Fortschritt eines Plans oder
Teilbaums nach **Status und Story Points** gewichtet und zeigt ihn als Kennzahlen, Balken, Kachelansicht, Teilprojektbaum und die Status-Matrix, die sich direkt in Jira oder Confluence einfügen lässt.
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
| Gewicht | Story Points (die Schätzung in Tagen, „Schätzung (T)“, wird nicht gelesen; unlesbare, unendliche und negative Werte gelten als nicht geschätzt) |
| weitere | Titel, Sprint, Team (alle anderen Spalten, auch Personen, werden nicht gelesen) |
| Gegenprobe | Fortschritt (%), Fortschritt abgeschlossen (SP), Verbleibender Fortschritt (SP): Jiras eigene Werte, nur zum Vergleich |

Spalten mit „(hochrechnen)“ sind Summen über die Kinder und werden übergangen, ebenso alle anderen Spalten. Der Export enthält weder Statusverlauf noch Lösungsdatum:
Es gibt deshalb keinen Verlauf über die Zeit und keine Prognose. Was nicht gelesen werden konnte, meldet die App oben, bevor sie eine Zahl zeigt.

## Daten aus Jira Plans exportieren

Die App zeigt diese Anleitung auch vor dem Hochladen. Menünamen nach der Dokumentation von Atlassian (englische Oberfläche); die deutsche Oberfläche und neuere Versionen können anders heißen, an einer eigenen
Instanz geprüft ist das nicht.

1. **Story Points als Schätzung des Plans einstellen.** Neben dem Namen des Plans **•••** (More actions) → **Plan settings** → **Estimation and scheduling** → **Story Points**; falls nötig, das Schätzfeld dem Plan
   hinzufügen. Laut Atlassian sind Story Points nur wählbar, wenn alle Teams im Plan Scrum-Teams sind (bei einem Kanban-Team fehlt die Option), Story Points und Zeitschätzungen (Tage, Stunden) sind nicht
   austauschbar, und beim Wechsel gehen nicht gespeicherte Schätzungen verloren. Steht der Plan auf Tagen, heißt die Spalte „Schätzung (T)“, und die liest dieses Werkzeug nicht. Die Tickets selbst müssen Story Points tragen.
2. **Festlegen, was der Export enthält.** Der Export enthält nur, was in der **Timeline-Ansicht** sichtbar ist: Filter auf den auszuwertenden Teil des Plans setzen (inklusive der Ebenen darüber, wenn sie als Wurzel
   wählbar sein sollen) und über **Add fields** mindestens Vorgangsschlüssel, Status, **Story Points**, Hierarchie und Übergeordnetes Element einblenden, optional Titel, Sprint und Team.
3. **Exportieren:** in der Timeline-Ansicht **Share** → **Export** → **Export data (.csv)** → **Export**. Gebraucht werden die Rolle Plans administrator oder Plan user und Jira Cloud Premium oder Enterprise.
4. **Prüfen:** Unter „Was wurde erkannt?“ zeigt die App, bei wie vielen Tickets Story Points stehen; fehlt die Spalte, warnt sie.

Quellen: [Export](https://support.atlassian.com/jira-software-cloud/docs/export-advanced-roadmaps-plan-data-as-csv/), [Schätzeinheit](https://support.atlassian.com/jira-software-cloud/docs/change-estimation-units-in-your-plan/),
[Spalten](https://support.atlassian.com/jira-software-cloud/docs/add-edit-and-remove-columns-in-advanced-roadmaps/).

## Was zählt

* **Zählende Tickets:** nur die Blätter des Ticket-Baums, also Tickets ohne Kinder (Stories, Tasks und Bugs ohne Sub-Tasks und die Sub-Tasks selbst). Story Points und Status kommen allein von ihnen, alles darüber wird nur
  aufsummiert: Story Points und Status der Zwischentickets (Epics, Initiativen, Themen, Stories mit Sub-Tasks) gehen nicht ein. Ausnahmen: Ein zurückgewiesenes Zwischenticket nimmt alle Blätter darunter mit; im Menü „Sub-Tasks
  einer Story“ verteilt b die Story Points der Story auf ihre Sub-Tasks und lässt c die Story selbst zählen; eine Story, deren Sub-Tasks alle zurückgewiesen sind, ist selbst ein Blatt.
* **Gewicht:** die Story Points des Tickets; fehlen sie, entscheidet die Auswahl „Tickets ohne Story Points“: ein Median geschätzter Tickets, 1 Story Point oder nicht zählen (die Varianten stehen unten).
* **Gutschrift nach Statusname** (deutsch und englisch): fertig (Done, Closed, Fertig, Released, Ready4Prod …) 100 %, Test (In Test, QA, Abnahme, Ready4Test …) 90 %,
  Merged sowie Review und Überprüfung 80 %, alles andere 0 %. Verneinungen („Not done“, „Untested“) zählen 0 %.
* **Zurückgewiesen** (Rejected, Zurückgewiesen, Won't do, Abgelehnt, Cancelled, Duplicate …): das Ticket und alles darunter zählen nicht, weder im Gewicht noch in der Anzahl.
* **Fortschritt** einer Gruppe: Summe aus Gewicht mal Gutschrift, geteilt durch die Summe der Gewichte.

Die Regeln stehen auch in der App (Ausklapper „Welche Status zählen wie viel?“). Reihenfolge der Prüfung, der erste Treffer gilt: zurückgewiesen (zählt nicht), Verneinung (0 %), fertig (100 %), Merged (80 %),
Test (90 %), Review (80 %), alles andere 0 %; die Namen der Klassen stehen in der App. Die Gewichte der Status stehen in einer Tabelle (Ausklapper „Gewichte der Status“) und lassen sich dort ändern, wenn ein Status anders heißt, als sein Name vermuten lässt.
Sonst gibt es nichts einzustellen.

## Auswahl (Seitenleiste)

* **Teilprojekt (Wurzel):** macht ein Ticket mit allem darunter zu einem eigenständigen Datensatz; auch Median, Status und Hierarchiestufen beziehen sich dann nur auf diesen Teilbaum.
* **Tickets ohne Story Points:** acht Varianten (A Median der Stufe im Teilbaum, Voreinstellung; B Median der Stufe im ganzen Plan; C je Ticket-Typ; D der Geschwister; E je Team; F Rückfallkette; H als 1 Story Point; I nicht zählen). Die Meldung unter den Kennzahlen nennt, wie viele Tickets betroffen sind.
* **Sub-Tasks einer Story:** a Sub-Tasks zählen wie ungeschätzte Tickets (Voreinstellung); b die Story Points der Story verteilen sich gleichmäßig auf ihre Sub-Tasks, wenn keine eigene Story Points hat; c die Story zählt selbst, die Sub-Tasks bleiben außen vor.
* **Zusammenfassung:** Die Balken fassen immer die Tickets direkt unter der Wurzel zusammen (im ganzen Plan die obersten), jedes Ticket mit allem darunter; ein Klick auf eine Kachel oder einen Knoten mit Kindern macht es zur neuen Wurzel.

## Hoch und runter im Baum

**Runter:** Ein Klick auf eine Kachel oder einen Knoten des Teilprojektbaums, der Kinder hat, öffnet ihn als Teilprojekt; die Zahlen, die Kachelansicht, der Teilprojektbaum und die Tabellen folgen der neuen Wurzel. Ein Klick auf
ein Blatt (ein Ticket ohne Kinder) bewirkt nichts. **Hoch:** Die Knöpfe über der Auswahl in der Seitenleiste gehen eine Stufe hoch („Eine Stufe hoch“) oder zurück zum ganzen Plan („Ganzer Plan“). Alternativ
wechselt die Auswahl „Teilprojekt“ die Wurzel. Der Klick kommt in Streamlit als Auswahl eines Diagrammpunkts an (`on_select`); den Weg von der Auswahl bis zur neuen Wurzel prüfen die Tests und ein Mausklick im Browser
(Chromium-basiert, erfundener Plan mit 37 Tickets, Kachelansicht und Teilprojektbaum). Wenn der Klick bei euch nichts bewirkt,
bitte melden.

## Ausgabe

Kennzahlen (nach Status gewichtet, nur Done nach Gewicht, nur Done nach Ticketzahl, offenes Gewicht), Fortschrittsbalken je Ticket direkt unter der Wurzel, Kachelansicht, Teilprojektbaum und eine Tabelle: die
**Status-Matrix** mit einer Zeile je Ticket direkt unter der Wurzel (die Summe der Story Points je Status mit dem Gewicht im Kopf, Rejected getrennt, Completed ab 90 % und gewichteter Fortschritt). Haben Tickets einen Sprint, kommt der **Fortschritt je Sprint** dazu (Balken und Tabelle: Tickets, Gewicht, Fortschritt, „nur Done“, mitgenommene Tickets); jedes zählende Ticket steht in seinem letzten Sprint, eine Sub-Task ohne Sprint erbt den ihrer Story. Enthält der Export Jiras eigene Fortschrittsspalten, kommt die **Gegenprobe** dazu: je Ticket Jiras Wert neben „Nur Done, nach Gewicht“ und der Abstand in Prozentpunkten, dazu die Prüfung, ob Jiras drei Spalten untereinander zusammenpassen (Fortschritt (%) gegen abgeschlossen ÷ (abgeschlossen + verbleibend)). Status, deren Name keine Regel kennt, meldet die App unter den Kennzahlen.

## Datenschutz

* **Hochgeladene Dateien liegen für die Sitzung im Arbeitsspeicher des Servers, auf dem die App läuft** (bei einer Veröffentlichung z. B. Streamlit Community Cloud, USA). Das Werkzeug speichert und cached sie nicht
  (kein `st.cache_data`, kein Schreiben auf die Platte), gibt sie nicht weiter und hat keine Anbindung an die Jira-Schnittstelle und kein Eingabefeld für Zugangsdaten. Die Plattform kann die Datei bis zum
  Sitzungsende im Speicher halten; den Server betreibt, wer die App bereitstellt.
* Nach dem Einlesen bleiben nur die berechnungsrelevanten Felder. Namen von Personen werden gar nicht erst gelesen; die Titel der Tickets bleiben erhalten; „Daten jetzt löschen“
  verwirft die geladenen Tickets der Sitzung und stellt das Upload-Feld zurück. Das betrifft nur die Daten der Sitzung: Die Datei hat den Server beim Hochladen schon erreicht.
* Fehlermeldungen nennen nur den Fehlertyp, und ein Filter ersetzt die Meldung unbehandelter Ausnahmen im Protokoll durch den Typ (sie könnte Ticketdaten enthalten). Das ist nur gegen die eigene Testsuite
  geprüft, nicht gegen die Server einer Plattform.
* Obergrenzen: 50 MB (`server.maxUploadSize`) und 20000 Tickets je Datei. Vor dem Hochladen weist die App darauf hin, nur die gebrauchten Spalten zu exportieren.
* **Keine vertraulichen Daten ohne Freigabe auf einem fremden Server auswerten. Für sensible Projekte lokal ausführen:** Dann bleibt die Datei auf dem eigenen Rechner (oder im eigenen Netz, wenn die App dort
  betrieben wird), es gibt weder einen Upload an einen fremden Server noch ein Protokoll bei einem Anbieter.

```bash
streamlit run app.py --server.address localhost
```

Mit `--server.address localhost` hört die App nur auf dem eigenen Rechner (`http://localhost:8501`); ohne diese Angabe ist sie standardmäßig auch im lokalen Netz erreichbar.

## Berechnungsmöglichkeiten für Tickets ohne Story Points

Der Ausklapper „Tickets ohne Story Points: Berechnungsmöglichkeiten“ in der App (nach „Welche Status zählen wie viel?“) stellt die Varianten mit Vor- und Nachteilen gegenüber (Median der Stufe im Teilbaum oder im ganzen Plan, je Ticket-Typ, je Geschwistergruppe, je Team,
Rückfallkette, Mittelwert, 1 Story Point, nicht zählen; dazu drei Möglichkeiten für Sub-Tasks ohne Story Points) und zeigt, wie sich der Fortschritt unter den drei wählbaren Regeln an den geladenen Daten verschiebt.
Eingebaut sind die Varianten A bis F, H und I (Auswahl „Tickets ohne Story Points“); G (Mittelwert) ist nur ein Vorschlag. Die drei Möglichkeiten für Sub-Tasks (a bis c) stehen in der Auswahl „Sub-Tasks einer Story“ zur Wahl.

## Annahmen, Grenzen und bekannte Probleme

### Annahmen

- **Die Gutschrift nach Statusname stimmt.** Fertig 100 %, Test 90 %, Merged oder Review 80 %, alles andere 0 %: Das ist eine Lesart des Namens und eine Verabredung, keine Messung. Angefangene Arbeit („In Arbeit“) zählt 0 %, der Fortschritt springt also erst mit dem Statuswechsel; für laufende Arbeit ist die Zahl eher vorsichtig.
- **Story Points sind vergleichbar und additiv.** Ein Ticket mit 4 Story Points zählt doppelt so viel wie eines mit 2, über alle Teams und Epics hinweg. Story Points sind aber teamintern kalibriert; ein Gesamtwert über mehrere Teams mischt Maßstäbe.
- **Die Blätter bilden die Arbeit vollständig ab.** Was nicht als Blatt im Export steht (nicht angelegte oder aus dem Plan herausgefilterte Tickets), fehlt im Fortschritt. Die Story Points der Zwischentickets gelten als nicht maßgeblich, auch wenn ein Epic oder eine Story eine eigene Schätzung hat, die von der Summe der Blätter abweicht; die Tabelle prüft das nicht.
- **Ersatzwerte für Tickets ohne Story Points sind Annahmen.** Jede Variante (A bis F, H, I) nimmt etwas anderes an; die Tabelle im Ausklapper „Berechnungsmöglichkeiten“ zeigt, wie weit die Zahl an den geladenen Daten schwankt.
- **Der Export ist der Plan.** Was die Filter und Spalten der Timeline-Ansicht nicht enthalten, kennt das Werkzeug nicht. Eltern außerhalb der Datei werden verworfen (die App meldet es), das Ticket steht dann als eigene Wurzel da.

### Grenzen

- **Nur ein Stichtag.** Der Plan-Export enthält weder Statusverlauf noch Lösungsdatum: kein Verlauf, kein Tempo, keine Prognose, kein Vergleich mit einem früheren Stand.
- **Hierarchiestufe heißt Tiefe im Baum, nicht Typ.** Ein Bug ohne Epic liegt auf Stufe 1, Stories unter einem Epic auf Stufe 2; „Median der Stufe“ vergleicht deshalb unter Umständen Ungleiches, und ein Ticket ohne Eltern bekommt nie den Median der Stories unter Epics.
- **Ein Teilprojekt ist ein eigener Datensatz.** Die Mediane (außer bei B und F), die Stufen und die Auswahl der Status beziehen sich nur auf den Teilbaum; dasselbe Epic kann im Teilprojekt eine andere Zahl haben als in der Gesamtansicht, wenn Tickets ohne Story Points darunter liegen.
- **Zurückgewiesen wird am Statusnamen erkannt.** Heißt ein Status anders („Entfällt“, „Nicht weiterverfolgt“), bleibt das Ticket im Gewicht und zählt 0 %. Die Tabelle der Status-Gewichte zeigt jeden Status der Daten; ein Status ohne erkannte Bedeutung (weder fertig, Test, Merged oder Review noch ein bekannter Name für „noch nicht fertig“ wie Backlog, To Do, In Arbeit oder On Hold) zählt 0 %; die App weist unter den Kennzahlen darauf hin.
- **Obergrenzen.** Höchstens 30 Balken (die gewichtsstärksten), im Teilprojektbaum höchstens 250 Knoten (die tiefste Ebene wird zusammengefasst), höchstens 20000 Tickets und 50 MB je Datei.
- **Sprint heißt der letzte Sprint.** Ein Ticket, das in mehreren Sprints stand, zählt in der Auswertung je Sprint nur im letzten (als „mitgenommen“ ausgewiesen); die Zeit davor ist im Export nicht als Verlauf abgebildet. Die Zahlen je Sprint zeigen den Stand heute, nicht den am Sprintende, und ein Ticket ohne Sprint übernimmt den Sprint seines nächsten übergeordneten Tickets mit Sprint.
- **Gerundete Anzeige.** Prozent mit einer, Gewichte mit zwei Nachkommastellen; gerechnet wird ungerundet.

### Bekannte Probleme und Unsicherheiten

- **Die Spaltennamen des Exports sind erschlossen.** Erkannt werden die Namen aus früheren Exporten (Vorgangsschlüssel, Vorgangsstatus, Hierarchie, Übergeordnetes Element, Story Points …); der Export einer anderen Jira-Version oder -Sprache kann abweichen. Fehlende Spalten meldet die App.
- **Sub-Tasks ohne Story Points** bekommen in der Voreinstellung (a) Ersatzwerte, während die Story Points der Story wegfallen; die Summe der Sub-Tasks weicht dann von der Story ab. Die Varianten b und c ändern das, haben aber eigene Nachteile (siehe „Berechnungsmöglichkeiten“).
- **Zählung nach Blättern.** Eine Story mit vielen Sub-Tasks wiegt mehr als eine mit wenigen, wenn die Sub-Tasks einzeln gezählt werden.
- **Klick in die Diagramme.** Der Wechsel der Wurzel per Mausklick ist in Kachelansicht und Teilprojektbaum an einem erfundenen Plan mit 37 Tickets in einem Chromium-basierten Browser geprüft (Streamlit 1.64, Plotly 7.1); andere Browser und Streamlit-Versionen nicht. Die Auswahl „Teilprojekt“ und die Hoch-Knöpfe funktionieren unabhängig davon.
- **Gegenprobe zu Jira.** Jiras eigene Spalten „Fortschritt (%)“, „Fortschritt abgeschlossen (SP)“ und „Verbleibender Fortschritt (SP)“ werden nur neben „Nur Done, nach Gewicht“ gezeigt und gehen in keine Rechnung ein. Wie Jira sie berechnet, steht nicht im Export; die Gegenprobe ist an keinem echten Export mit Inhalten geprüft.
- **Zahlenformat der Story Points.** Ein Komma gilt als Dezimaltrenner: „1,000“ liest das Werkzeug als 1, nicht als tausend. Werte, die keine Zahl sind, nicht endlich (nan, inf) oder negativ sind, zählen als nicht geschätzt, und die App meldet ihre Zahl.
- **Nur an erfundenen Beispielen geprüft.** Die Rechenregeln sind in Tests von Hand nachgerechnet, an einem echten Export der eigenen Jira-Instanz aber nicht.
- **Datenschutz.** Die Datei geht an den Server der App; die App speichert sie nicht, die Plattform kann sie aber bis zum Sitzungsende im Speicher halten (siehe „Datenquelle und Datenschutz“).

## Bewusst nicht enthalten

Gegenüber der ausführlicheren Fassung fehlen: weitere Zusammenfassungen (nach Epic, Release, Komponente, Label, Bearbeiter, Team, Bereich, Priorität, Typ oder Status; die Spalten dazu werden nicht gelesen) und die Tabellen Je Gruppe, Status × Gruppe und Datenqualität, Beispieldaten, JSON- und Standard-CSV-Export, Wahl des Gewichtsschemas und der Gewichtungsart (Story Points oder Ticketanzahl), Zeitraum (Sprint von … bis …), die Mischung des Story-Fortschritts aus den Sub-Tasks, Kreuztabelle,
Treemap, Verlauf (Burn-up), Sensitivitätsprüfung, JQL-Hilfe, Zusammenfassung zum Kopieren.

## Aufbau

| Datei | Inhalt |
|---|---|
| `app.py` | Oberfläche (Streamlit): `main()` setzt die Seite aus `render_*`-Schritten zusammen |
| `jira_texts.py` | Die langen Erklärtexte der App |
| `jira_plan.py` | Einlesen des Plan-Exports |
| `jira_core.py` | Statusklassen, Hierarchie, Gewichte, Gruppen, Teilprojektbaum |
| `jira_evaluation.py` | `analyse`: Kennzahlen aus Auswahl und Gewichten, interne Konsistenzprüfung |
| `jira_tables.py` | Tabellen (Status-Matrix, Gegenprobe zu Jira, Wirkung der Regeln) und Ausgabe als CSV, Wiki-Markup, HTML |
| `jira_charts.py` | Plotly-Diagramme |
| `jira_privacy.py` | Filter, der Ausnahmemeldungen aus dem Protokoll nimmt |
| `tests/` | Tests an einer von Hand gerechneten Mini-Instanz, Zufallsprojekte für Summen und Grenzen, App-Tests mit AppTest; `test_gaps.py` prüft Randfälle und Stellen, die andere Tests nicht festhielten |
| `ruff.toml` | Lint-Regeln (`ruff check .`, läuft auch in der CI) |

## Lizenz

Open Source unter der [MIT-Lizenz](LICENSE).
