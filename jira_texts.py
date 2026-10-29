"""Die langen Erklärtexte der App (Markdown), getrennt vom Aufbau der Seite in `app.py`. Reine Zeichenketten und eine Funktion (`status_rules_markdown`), die Zahlen aus den Konstanten einsetzt."""

import jira_constants as C
import jira_core as A

UPLOAD_NOTICE = f"""
**Bitte vor dem Hochladen lesen.** Die Datei geht zur Berechnung an den Server, auf dem diese App läuft (bei einer Veröffentlichung z. B. Streamlit Community Cloud, USA), und liegt dort nur für Ihre
Sitzung im Arbeitsspeicher. Das Werkzeug speichert sie nicht, legt sie nicht zwischen und gibt sie nicht weiter; den Server betreibt aber, wer die App bereitstellt. Laden Sie keine vertraulichen Daten
ohne Freigabe hoch. Höchstens {C.MAX_UPLOAD_MB} MB und {C.MAX_IMPORT_ISSUES} Tickets je Datei. Gebraucht werden nur diese Spalten: Vorgangsschlüssel, Vorgangsstatus, Hierarchie, Übergeordnetes Element
und Story Points (optional Titel, Sprint und Team). Alle anderen Spalten, besonders Personen, Beschreibungen und Kommentare, gehören vor dem Hochladen gelöscht; das Werkzeug liest sie nicht, sie erreichen
den Server aber mit der Datei. Für sensible Projekte das Werkzeug lokal ausführen: Es ist Open Source (MIT-Lizenz), Code und Anleitung stehen im [Repository]({C.REPO_URL}).
"""


EXPORT_GUIDE = """
**1. Story Points als Schätzung des Plans einstellen.** Das Werkzeug gewichtet mit Story Points. Die Einheit gilt je Plan: neben dem Namen des Plans in der Seitenleiste **•••** (More actions) →
**Plan settings** → Seite **Estimation and scheduling** → **Story Points**. Falls nötig, das Feld, mit dem die Tickets geschätzt werden, dem Plan hinzufügen. Laut Atlassian gilt dabei: Story Points sind nur wählbar,
wenn alle Teams im Plan Scrum-Teams sind (bei einem Kanban-Team fehlt die Option; das Team auf dem Reiter Teams auf Scrum umstellen), Story Points und Zeitschätzungen (Tage, Stunden) sind nicht austauschbar, und
beim Wechsel der Einheit gehen nicht gespeicherte Schätzungen verloren. Steht der Plan auf Tagen, heißt die Spalte im Export „Schätzung (T)“: Die liest dieses Werkzeug nicht. Die Tickets selbst müssen
Story Points tragen; Tickets ohne Story Points behandelt die Auswahl „Tickets ohne Story Points“ in der Seitenleiste.

**2. Festlegen, was der Export enthält.** Der Export enthält nur, was in der **Timeline-Ansicht** des Plans sichtbar ist. Deshalb zuerst die Filter so setzen, dass genau der Teil des Plans erscheint, der
ausgewertet werden soll (die Hierarchie darüber, z. B. Initiativen, gehört dazu, wenn sie als Wurzel wählbar sein soll), und über **Add fields** die Spalten einblenden: mindestens Vorgangsschlüssel und
Status, außerdem **Story Points** (Gewicht), Hierarchie und Übergeordnetes Element (Aufbau des Baums) und, wenn gewünscht, Titel, Sprint und Team. Welche Spalten der Export genau liefert, listet Atlassian nicht auf; die genannten sind die, die dieses Werkzeug aus echten Exporten kennt.

**3. Exportieren.** In der Timeline-Ansicht: **Share** → **Export** → **Export data (.csv)** → **Export**. Gebraucht werden die Rolle Plans administrator oder Plan user und Jira Cloud Premium oder Enterprise.
Die erzeugte CSV-Datei hier hochladen; vorher Spalten wie Beschreibung und Kommentare, falls vorhanden, löschen.

**4. Prüfen.** Nach dem Laden zeigt „Was wurde erkannt?“, bei wie vielen Tickets Story Points stehen. Fehlt die Spalte, steht oben eine Warnung, und alle Tickets wiegen gleich viel.

*Die Menünamen folgen der Dokumentation von Atlassian ([Export](https://support.atlassian.com/jira-software-cloud/docs/export-advanced-roadmaps-plan-data-as-csv/),
[Schätzeinheit](https://support.atlassian.com/jira-software-cloud/docs/change-estimation-units-in-your-plan/), [Spalten](https://support.atlassian.com/jira-software-cloud/docs/add-edit-and-remove-columns-in-advanced-roadmaps/)) in der englischen Oberfläche.
Die deutsche Oberfläche und neuere Versionen können anders heißen; an einer eigenen Jira-Instanz geprüft ist das nicht.*
"""


DATA_SOURCE_MARKDOWN = """
**Plan-Export.** Wie man ihn erzeugt, steht oben unter „So kommt die Datei zustande“. Erkannt werden deutsche und englische Spaltenköpfe: *Vorgangsschlüssel*, *Vorgangsstatus*, *Titel*, *Hierarchie* (als Ticket-Typ; Epic,
Initiative und Thema fassen Tickets zusammen), *Übergeordnetes Element* (als Schlüssel, mit dem Schlüssel am Anfang oder als eindeutiger Titel), *Story Points*, *Sprint* und *Team*. Pflicht sind nur Schlüssel und Status; was fehlt, wird oben gemeldet. Spalten mit *(hochrechnen)* sind Summen über die Kinder und werden
übergangen, ebenso die Schätzung in Tagen und alle weiteren Spalten, darunter Personen, Releases, Bereiche, Prioritäten, Stichwörter und Komponenten: Sie werden nicht einmal eingelesen. Der Export enthält weder eine Statuskategorie noch ein Lösungsdatum: Was erledigt ist, folgt allein dem Statusnamen.

**Datenschutz.** Die Datei geht zur Berechnung an den Server der App und wird nur für die Sitzung im Arbeitsspeicher gehalten, nie gespeichert und nie zwischengespeichert; die Plattform kann sie bis zum
Ende der Sitzung noch im Speicher halten. Nach dem Einlesen bleiben nur die berechnungsrelevanten Felder (Namen von Personen werden gar nicht erst gelesen), und „Daten jetzt löschen“ verwirft die geladenen Tickets. Fehlermeldungen nennen nur den Fehlertyp, und die Ausnahmemeldungen stehen nicht im Protokoll der App (sie könnten Daten enthalten). Es gibt bewusst keine
Anbindung an die Jira-Schnittstelle: Zugangsdaten sollen nie durch dieses Werkzeug laufen. Höchstens 50 MB und 20000 Tickets je Datei. Läuft die App auf dem eigenen Rechner oder im eigenen Netz, verlässt
die Datei es nicht.
"""

HOW_IT_WORKS_BEFORE_FORMULA = """
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

HOW_IT_WORKS_AFTER_FORMULA = """
**Teilprojekt.** Die Wurzel macht ein Ticket mit allem darunter zu einem eigenständigen Datensatz: Auch der Median für ungeschätzte Tickets (falls gewählt), die Status der Gewichtstabelle, die Sprints und die
Hierarchiestufen beziehen sich nur auf diesen Teilbaum.

**Annahmen, Grenzen und bekannte Probleme** stehen im nächsten Ausklapper.
"""


def status_rules_markdown() -> str:
    """Welcher Statusname zählt standardmäßig wie viel? Erst die Regeln in der Reihenfolge, in der sie geprüft werden (der erste Treffer gilt), dann die Auflistung mit Beispielnamen.
    Die Prozentwerte stammen aus `C.STATUS_CLASS_CREDIT`, die Beispiele aus `A.STATUS_EXAMPLES`."""
    pct_of = {name: f"{round(100 * credit)} %" for name, credit in C.STATUS_CLASS_CREDIT.items()}
    examples = {name: ", ".join(names) for name, names in A.STATUS_EXAMPLES.items()}
    return f"""
**Regeln.** Verglichen wird der Name des Status ohne Groß- und Kleinschreibung, Akzente, Umlaut-Punkte und Satzzeichen. Die Regeln werden in dieser Reihenfolge geprüft, der erste Treffer gilt
(„Test Review“ zählt also als Test, nicht als Review):

1. **Zurückgewiesen → zählt nicht.** Der Name enthält Rejected, Declined, Zurückgewiesen, Abgelehnt, Won't do, Will not do, Wontfix, Cancel…, Abgebrochen, Verworfen, Storniert, Abandon…, Duplicate, Duplikat,
   Obsolete, Invalid, Ungültig, Nicht umgesetzt oder Won't implement. Das Ticket und alles unter ihm fällt aus Gewicht und Anzahl.
2. **Verneinung → 0 %.** Not done, Nicht fertig, Unfertig, Nicht erledigt, Unresolved, Unreleased, Not closed, Nicht abgeschlossen, Incomplete, Unvollständig, Unfinished, Not merged, Untested, Ungetestet,
   Unreviewed, Ungeprüft, Nicht überprüft, Not reviewed, Not tested, Not resolved, Not finished, Unmerged, Nicht geschlossen, Unabgeschlossen u. ä.
3. **Fertig → {pct_of['done']}.** Der Name enthält Done, Closed, Resolved, Fertig, Erledigt, Abgeschlossen, Geschlossen, Released, Deployed, Delivered, Ausgeliefert, Complete, Finished, Production, Produktion oder
   Produktiv, endet auf „Prod“ (Ready4Prod) oder enthält das Wort „Live“.
4. **Merged → {pct_of['merged']}.** Merged, Gemerged, Zusammengeführt.
5. **Test → {pct_of['test']}.** Der Name enthält Test (In Test, Testing, Ready4Test), Abnahme, Acceptance, Verif… oder Validat…, oder ist das Wort QA oder UAT.
6. **Review → {pct_of['review']}.** Review, Überprüf…, Geprüft, Prüfung, Prüfen, Begutachtung.
7. **Alles andere → 0 %** (In Arbeit, In Progress, On Hold, Backlog, To Do, Specification …).

**Auflistung** (Beispielnamen, nicht vollständig):

| Gewicht | Beispiele |
|---|---|
| {pct_of['done']} | {examples['done']} |
| {pct_of['test']} | {examples['test']} |
| {pct_of['merged']} | {examples['merged']} |
| {pct_of['review']} | {examples['review']} |
| 0 % | {examples['other']} |
| zählt nicht | {examples['rejected']} |

Jedes Gewicht lässt sich nach dem Laden in der Tabelle „Gewichte der Status“ ändern, falls ein Status anders heißt, als sein Name vermuten lässt. Die Namen, die in euren Daten vorkommen, stehen dort mit ihrem
Standardgewicht.
"""


UNEST_OPTIONS_MARKDOWN = """
Ein Ticket ohne Story Points braucht ein Gewicht, sonst fehlt es im Fortschritt. Dafür gibt es mehrere Möglichkeiten. Zwei Fragen sind getrennt zu entscheiden (beide haben ein Auswahlmenü in der Seitenleiste): **aus welcher Vergleichsgruppe** der Ersatzwert kommt
(Teil 1) und **wie mit Sub-Tasks** umzugehen ist, deren Story Points fehlen (Teil 2). Was „Stand“ als *wählbar* ausweist, steht in der Seitenleiste unter „Tickets ohne Story Points“ bzw. „Sub-Tasks einer Story“ zur Wahl (mit dem Buchstaben der Variante); alles andere ist ein **Vorschlag** und noch nicht
eingebaut. Vor- und Nachteile sind Überlegungen zur Methode, keine Messungen an euren Daten.

### Teil 1: Woher kommt das Gewicht eines Tickets ohne Story Points?

| Variante | Vergleichsgruppe | Vorteile | Nachteile | Stand |
|---|---|---|---|---|
| **A. Median der Stufe im Teilbaum** | geschätzte Blätter derselben Tiefe im gewählten Teilbaum (Tiefe ab der Wurzel) | Das Teilprojekt ist ein eigenständiger Datensatz; einfach zu erklären; Stories und Sub-Tasks werden nicht gemischt | Gewichte und Fortschritt ändern sich mit dem gewählten Teilbaum; „Stufe“ ist die Tiefe, nicht der Typ (ein Bug ohne Epic liegt auf einer anderen Stufe als Stories unter Epics); bei wenigen geschätzten Tickets wackelt der Median | wählbar, Voreinstellung |
| **B. Median der Stufe im ganzen Plan** | geschätzte Blätter derselben Tiefe im ganzen Plan | Dasselbe Ticket wiegt in jeder Ansicht gleich; ein Teilprojekt ist ein Ausschnitt der Gesamtansicht; größere Datenbasis | Das Teilprojekt ist nicht mehr eigenständig, Tickets außerhalb bestimmen die Gewichte; mischt Teams mit unterschiedlicher Story-Point-Skala | wählbar |
| **C. Median je Ticket-Typ** | geschätzte Blätter desselben Typs (Story, Task, Bug, Sub-Task) im gewählten Teilbaum | Vergleicht Gleiches (Bugs sind oft kleiner als Stories), unabhängig von der Tiefe | Seltene Typen haben kaum geschätzte Tickets; Typnamen und Konventionen unterscheiden sich je Jira-Instanz | wählbar |
| **D. Median der Geschwister** | geschätzte Tickets mit demselben übergeordneten Ticket | Lokal: passt zur Größe des Epics bzw. der Story und zur Skala des Teams | Oft gibt es zu wenige oder keine geschätzten Geschwister (Sub-Tasks einer Story); Gewichte schwanken von Epic zu Epic | wählbar |
| **E. Median je Team** | geschätzte Blätter desselben Teams (Spalte Team; ohne Team bilden die Tickets ohne Team eine Gruppe) im gewählten Teilbaum | Story Points gelten nur innerhalb eines Teams: Das ist die vergleichbarste Gruppe | Das Team-Feld ist oft leer; dünne Datenbasis je Team | wählbar |
| **F. Rückfallkette** | Geschwister → gleicher Typ → gleiche Stufe (je im Teilbaum) → alle geschätzten Tickets des ganzen Plans → 1 | Nutzt die genaueste vorhandene Basis und fällt nur auf 1 zurück, wenn nirgends etwas geschätzt ist | Das Gewicht eines Tickets hängt davon ab, was in seiner Nähe geschätzt ist; schwerer zu erklären und nachzurechnen | wählbar |
| **G. Mittelwert statt Median** | wie A oder B | Nutzt alle Werte | Ausreißer (ein Ticket mit 21 Story Points) verschieben ihn stark; der Median ist robuster | Vorschlag, nicht empfohlen |
| **H. Als 1 Story Point** | keine | Einfach, transparent, unabhängig von den Daten | Verzerrt, wenn typische Tickets größer sind: ungeschätzte Tickets wirken zu leicht, der Fortschritt fällt zu hoch aus, wenn sie offen sind | wählbar |
| **I. Nicht zählen** | keine | Keine erfundenen Gewichte | Offene, ungeschätzte Tickets verschwinden aus dem Fortschritt, die Zahl wird zu optimistisch; bei vielen ungeschätzten Tickets kaum aussagekräftig | wählbar |

### Teil 2: Sub-Tasks ohne Story Points

Seit nur Blätter zählen, zählt eine Story mit Sub-Tasks durch ihre Sub-Tasks. Haben diese keine Story Points, gilt für sie die Regel aus Teil 1; die Story Points der Story selbst fallen weg.

| Variante | Vorteile | Nachteile | Stand |
|---|---|---|---|
| **a. Sub-Tasks wie ungeschätzte Tickets** | Einheitliche Regel für alle Blätter | Die Story Points der Story fallen weg; die Summe der Sub-Tasks weicht von der Story ab; eine Story mit vielen Sub-Tasks wiegt mehr als eine mit wenigen | wählbar, Voreinstellung |
| **b. Story Points der Story gleichmäßig auf die Sub-Tasks verteilen** (nur wenn keine Sub-Task eigene Story Points hat) | Das Gewicht der Story bleibt erhalten, „Epic vs. Total“ in der Status-Matrix stimmt, keine erfundenen Zahlen | Annahme gleich großer Sub-Tasks; setzt eine geschätzte Story voraus; Mischformen (einige Sub-Tasks geschätzt, andere nicht) brauchen eine Zusatzregel | wählbar |
| **c. Story zählt selbst, Sub-Tasks bleiben außen vor** (frühere Fassung) | Die Story Points der Planung bleiben das Gewicht | Der Fortschritt der Sub-Tasks bleibt unsichtbar, bis der Status der Story wechselt | wählbar |

### Einschätzung

Das ist eine Einschätzung, keine Messung. Kommt es auf **vergleichbare Zahlen zwischen Teilprojekten** an (z. B. ein Bericht je Epic), sprechen B oder F dafür, die Vergleichsgruppe nicht vom gewählten Teilbaum abhängen zu lassen. Soll ein **Teilprojekt für sich stehen**, ist A richtig.
Für **Sub-Tasks ohne Story Points** ist b am nächsten an der Planung. Wie stark die Wahl die Zahl verschiebt, zeigt die Tabelle am Ende für alle wählbaren Regeln an den geladenen Daten (sobald eine Datei geladen ist); für den Vorschlag G gibt es keine Zahlen.
"""


ASSUMPTIONS_MARKDOWN = """
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
"""
