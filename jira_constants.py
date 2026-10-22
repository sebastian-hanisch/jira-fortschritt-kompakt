"""Konstanten: Obergrenzen, Gutschriften je Statusklasse, Ebenen und Farben."""

MAX_IMPORT_ISSUES = 5000      # harte Obergrenze für eine Datei: alle Schritte sind O(n), das Diagramm-Budget ist darauf ausgelegt
REPO_URL = "https://github.com/sebastian-hanisch/jira-fortschritt-kompakt"      # Open Source (MIT-Lizenz): Code und Anleitung zum lokalen Betrieb
MAX_UPLOAD_MB = 50            # Größe einer hochgeladenen Datei; gehört in .streamlit/config.toml als server.maxUploadSize (tests/test_privacy.py prüft die Übereinstimmung)
UNIT = "SP"                 # Einheit der Gewichte: Story Points

# Gutschrift je Klasse, in die der Name eines Status fällt (jira_core.status_class); alles andere zählt 0, zurückgewiesene Tickets zählen gar nicht
STATUS_CLASS_CREDIT = {"done": 1.0, "merged": 0.8, "review": 0.8, "test": 0.9}
UNEST_MEDIAN, UNEST_ONE, UNEST_IGNORE = "Median der geschätzten Tickets", "als 1 Story Point", "nicht zählen"      # Gewicht eines Tickets ohne Story Points
UNEST_RULES = (UNEST_MEDIAN, UNEST_ONE, UNEST_IGNORE)
DEFAULT_UNEST = UNEST_MEDIAN
COMPLETED_MIN_CREDIT = 0.9      # „Completed“ der Status-Matrix: alle Status ab diesem Gewicht

DIM_ALL, DIM_EPIC, DIM_LEVEL, DIM_SPRINT, DIM_RELEASE, DIM_COMPONENT, DIM_LABEL, DIM_ASSIGNEE, DIM_TEAM, DIM_AREA, DIM_PRIORITY, DIM_TYPE, DIM_STATUS = (
    "Gesamtes Projekt", "Epic", "Hierarchiestufe", "Sprint", "Release (Fix Version)", "Komponente", "Label", "Bearbeiter", "Team", "Bereich", "Priorität", "Ticket-Typ", "Status")
DIMENSIONS = (DIM_ALL, DIM_EPIC, DIM_LEVEL, DIM_SPRINT, DIM_RELEASE, DIM_COMPONENT, DIM_LABEL, DIM_ASSIGNEE, DIM_TEAM, DIM_AREA, DIM_PRIORITY, DIM_TYPE, DIM_STATUS)
DEFAULT_DIM = DIM_EPIC

ROOT_ALL = ""              # Wurzel der Auswertung: leer = ganzes Projekt
MAX_LEVELS = 8             # höchste wählbare Hierarchiestufe
GRAPH_MAX_NODES = 250      # Hierarchiegraph: mehr Knoten lassen sich nicht lesen; die tiefste Ebene wird dann zusammengefasst
GRAPH_LABEL_MAX = 60       # bis zu dieser Knotenzahl trägt jeder Knoten seinen Schlüssel, darüber nur die Knoten mit Kindern

COLOR_DONE = "#2F6B65"
COLOR_PARTIAL = "#7FB5AE"
COLOR_OPEN = "rgba(150,150,150,0.45)"
COLOR_SCALE = [[0.0, "#c9534b"], [0.5, "#f2d57e"], [1.0, "#2F6B65"]]   # Fortschritt 0 % bis 100 %
