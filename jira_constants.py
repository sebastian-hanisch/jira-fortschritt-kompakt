"""Konstanten: Obergrenzen, Gutschriften je Statusklasse, Ebenen und Farben."""

MAX_IMPORT_ISSUES = 5000      # harte Obergrenze für eine Datei: alle Schritte sind O(n), das Diagramm-Budget ist darauf ausgelegt
REPO_URL = "https://github.com/sebastian-hanisch/jira-fortschritt-kompakt"      # Open Source (MIT-Lizenz): Code und Anleitung zum lokalen Betrieb
MAX_UPLOAD_MB = 50            # Größe einer hochgeladenen Datei; gehört in .streamlit/config.toml als server.maxUploadSize (tests/test_privacy.py prüft die Übereinstimmung)
UNIT = "SP"                 # Einheit der Gewichte: Story Points

# Gutschrift je Klasse, in die der Name eines Status fällt (jira_core.status_class); alles andere zählt 0, zurückgewiesene Tickets zählen gar nicht
STATUS_CLASS_CREDIT = {"done": 1.0, "merged": 0.8, "review": 0.8, "test": 0.9}
# Gewicht eines Tickets ohne Story Points; die Buchstaben entsprechen den Varianten im Ausklapper „Berechnungsmöglichkeiten“ (G, der Mittelwert, ist nicht eingebaut)
UNEST_MEDIAN = "A. Median der Stufe im Teilbaum"
UNEST_PLAN = "B. Median der Stufe im ganzen Plan"
UNEST_TYPE = "C. Median je Ticket-Typ"
UNEST_SIBLINGS = "D. Median der Geschwister"
UNEST_TEAM = "E. Median je Team"
UNEST_CHAIN = "F. Rückfallkette (Geschwister, Typ, Stufe, ganzer Plan)"
UNEST_ONE = "H. als 1 Story Point"
UNEST_IGNORE = "I. nicht zählen"
UNEST_RULES = (UNEST_MEDIAN, UNEST_PLAN, UNEST_TYPE, UNEST_SIBLINGS, UNEST_TEAM, UNEST_CHAIN, UNEST_ONE, UNEST_IGNORE)
DEFAULT_UNEST = UNEST_MEDIAN
# Sub-Tasks einer Story (die Buchstaben entsprechen Teil 2 im Ausklapper „Berechnungsmöglichkeiten“)
SUB_RULE = "a. Sub-Tasks zählen wie ungeschätzte Tickets"
SUB_SHARE = "b. Story Points der Story auf ihre Sub-Tasks verteilen"
SUB_SELF = "c. Story zählt selbst, Sub-Tasks bleiben außen vor"
SUB_RULES = (SUB_RULE, SUB_SHARE, SUB_SELF)
DEFAULT_SUB = SUB_RULE
COMPLETED_MIN_CREDIT = 0.9      # „Completed“ der Status-Matrix: alle Status ab diesem Gewicht

ROOT_ALL = ""              # Wurzel der Auswertung: leer = ganzes Projekt
GRAPH_MAX_NODES = 250      # Hierarchiegraph: mehr Knoten lassen sich nicht lesen; die tiefste Ebene wird dann zusammengefasst
GRAPH_LABEL_MAX = 60       # bis zu dieser Knotenzahl trägt jeder Knoten seinen Schlüssel, darüber nur die Knoten mit Kindern

COLOR_DONE = "#2F6B65"
COLOR_PARTIAL = "#7FB5AE"
COLOR_OPEN = "rgba(150,150,150,0.45)"
COLOR_SCALE = [[0.0, "#c9534b"], [0.5, "#f2d57e"], [1.0, "#2F6B65"]]   # Fortschritt 0 % bis 100 %
