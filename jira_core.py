"""Kern (nur numpy/Standardbibliothek): gewichteter Fortschritt aus Status, Story Points und Aggregationsebenen.

Modell: Ein *Atom* ist ein Blatt des Ticket-Baums, also ein Ticket ohne Kinder (Story, Task, Bug oder Sub-Task; Epics, Initiativen und Themen zählen nie selbst, und eine Story mit
Sub-Tasks zählt durch ihre Sub-Tasks). Es hat ein Gewicht w (die Story Points; fehlen sie, nach der gewählten Regel: ein Median geschätzter Atome, 1 oder nicht gezählt) und eine Gutschrift c in [0, 1] (Anteil der Arbeit, der laut Statusname als getan gilt). Der Fortschritt einer Gruppe G ist
P(G) = sum_G w*c / sum_G w. Zurückgewiesene Tickets (und alles unter ihnen) sind keine Atome."""

import re
import unicodedata
from dataclasses import dataclass, replace
from statistics import median

import numpy as np

import jira_constants as C

STRUCTURAL_TYPES = ("epic", "initiative", "initiativen", "thema", "theme")      # Ebenen über der Story: fassen Tickets zusammen, zählen selbst nie


@dataclass(frozen=True)
class Issue:
    """Ein Ticket in der Form, die der Kern braucht. `points` (Story Points) ist None, wenn das Ticket nicht geschätzt ist."""

    key: str
    summary: str = ""
    type: str = "Story"
    is_subtask: bool = False
    status: str = "To Do"
    points: float | None = None
    parent: str = ""                 # Schlüssel des übergeordneten Tickets, leer ohne Eltern
    sprints: tuple[str, ...] = ()    # in Jira-Reihenfolge; der letzte ist der aktuelle
    components: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()
    assignee: str = ""
    versions: tuple[str, ...] = ()
    team: str = ""
    area: str = ""                   # Bereich
    priority: str = ""

    @property
    def is_epic(self) -> bool:
        """Epic oder eine höhere Ebene (Initiative, Thema): Behälter für Tickets, kein Atom."""
        return self.type.strip().lower() in STRUCTURAL_TYPES


# ---------------------------------------------------------------- Status und Gutschriften

def name_key(name: str) -> str:
    """Statusname für den Vergleich: klein geschrieben, ohne Akzente und Umlaut-Punkte, nur Buchstaben und Ziffern („Won't do“ → „wontdo“, „Zurückgewiesen“ → „zuruckgewiesen“)."""
    plain = unicodedata.normalize("NFKD", (name or "").lower())
    return "".join(ch for ch in plain if ch.isalnum() and not unicodedata.combining(ch))


# Zurückgewiesen und Verwandte: das Ticket wird nicht umgesetzt und fällt aus der Fortschrittsrechnung ganz heraus (Gewicht und Anzahl)
_REJECTED_KEYS = (
    "rejected", "declined", "zuruckgewiesen", "zueruckgewiesen", "zurueckgewiesen", "abgelehnt", "wontdo", "willnotdo", "wontfix", "wontimplement", "nichtumgesetzt",
    "cancel", "abgebrochen", "verworfen", "storniert", "abandon", "duplicate", "duplikat", "obsolete", "obsolet", "invalid", "ungultig")
# Verneinungen vor den Positivwörtern: „Not done“ ist nicht fertig, „Untested“ nicht getestet
_NEGATED_KEYS = (
    "notdone", "undone", "nichtfertig", "unfertig", "nichterledigt", "unresolved", "notresolved", "unreleased", "notreleased", "notclosed", "nichtgeschlossen",
    "nichtabgeschlossen", "unabgeschlossen", "incomplete", "unvollstandig", "unfinished", "notfinished", "notmerged", "unmerged", "nichtgemerged", "nichtgemergt",
    "untested", "nottested", "ungetestet", "nichtgetestet", "unreviewed", "notreviewed", "nichtgepruft", "ungepruft", "nichtuberpruft", "nichtreviewed")
_DONE_KEYS = (
    "done", "closed", "resolved", "fertig", "erledigt", "abgeschlossen", "geschlossen", "released", "deployed", "delivered", "ausgeliefert", "complete", "finished",
    "production", "produktion", "produktiv")
_MERGED_KEYS = ("merged", "gemerged", "gemergt", "zusammengefuhrt")
_TEST_KEYS = ("test", "abnahme", "acceptance", "verif", "validat")
_TEST_TOKENS = ("qa", "uat")
_REVIEW_KEYS = ("review", "uberpruf", "gepruft", "prufung", "prufen", "begutachtung")       # „In Review“, „Wird überprüft“, „Geprüft“, „In Prüfung“: zählt wie Merged


# Beispielnamen je Klasse für die Beschreibung in der App; tests/test_status.py prüft, dass jeder Name wirklich in seine Klasse fällt
STATUS_EXAMPLES = {
    "done": ("Done", "Closed", "Resolved", "Fertig", "Erledigt", "Abgeschlossen", "Released", "Deployed", "Live", "Ready4Prod", "In Production"),
    "test": ("In Test", "Testing", "Ready4Test", "QA", "UAT", "Abnahme", "Verification", "Getestet"),
    "merged": ("Merged", "Gemerged", "Zusammengeführt"),
    "review": ("In Review", "Code Review", "Wird überprüft", "Geprüft", "In Prüfung"),
    "other": ("Backlog", "To Do", "Specification", "Estimate", "In Arbeit", "In Progress", "On Hold", "Not done", "Nicht fertig", "Untested"),
    "rejected": ("Rejected", "Zurückgewiesen", "Won't do", "Abgelehnt", "Cancelled", "Duplicate", "Obsolete"),
}


def status_class(name: str) -> str:
    """Klasse eines Status nach seinem Namen (deutsch und englisch): rejected, done, merged, test, review oder other. Reihenfolge: zurückgewiesen; Verneinungen
    („Not done“) sind other; dann fertig-klingende Namen („Done“, „Closed“, „Erledigt“, „Released“, „…Prod“), merged, Test („In Test“, „Testing“, „QA“, „Abnahme“) und
    Review („In Review“, „Wird überprüft“); alles Übrige ist other."""
    key = name_key(name)
    if any(w in key for w in _REJECTED_KEYS):
        return "rejected"
    if any(w in key for w in _NEGATED_KEYS):
        return "other"
    tokens = {name_key(t) for t in re.split(r"[^\w]+", (name or "").lower()) if t}
    if any(w in key for w in _DONE_KEYS) or key.endswith("prod") or "live" in tokens:
        return "done"
    if any(w in key for w in _MERGED_KEYS):
        return "merged"
    if any(w in key for w in _TEST_KEYS) or tokens & set(_TEST_TOKENS):
        return "test"
    if any(w in key for w in _REVIEW_KEYS):
        return "review"
    return "other"


def is_done_status(name: str) -> bool:
    return status_class(name) == "done"


def is_rejected_status(name: str) -> bool:
    return status_class(name) == "rejected"


def rejected_indices(issues) -> frozenset[int]:
    """Indizes der Tickets, die selbst oder über ein übergeordnetes Ticket zurückgewiesen sind (die Tickets unter einem zurückgewiesenen Epic zählen auch nicht)."""
    by_key = {t.key: t for t in issues}
    out = {i for i, t in enumerate(issues) if is_rejected_status(t.status)}
    for i, t in enumerate(issues):
        current = by_key.get(t.parent)
        for _ in range(20):               # höchstens 20 Ebenen hoch; ein Zyklus in den Eltern-Verweisen endet damit
            if current is None:
                break
            if is_rejected_status(current.status):
                out.add(i)
                break
            current = by_key.get(current.parent)
    return frozenset(out)


def status_credit(status: str) -> float:
    """Gutschrift eines Status nach seinem Namen: fertig 1, Test 0,9, Merged oder Review 0,8, alles andere 0."""
    return C.STATUS_CLASS_CREDIT.get(status_class(status), 0.0)


def status_credits(statuses, overrides=()) -> dict[str, float]:
    """Gutschrift je Status nach dem Namen; `overrides` (Paare Status, Gutschrift) ersetzen einzelne Werte."""
    own = dict(overrides)
    return {s: float(own[s]) if s in own else status_credit(s) for s in statuses}


def apply_credit_edits(shown, edited_rows: dict) -> tuple[tuple[str, float], ...]:
    """Überträgt Änderungen der Tabelle (`edited_rows` von st.data_editor: {Zeile: {Spalte: Wert}}) auf die gezeigten Gutschriften (Paare Status, Gutschrift in 0..1).
    Die Spalte der Tabelle heißt `Gewicht (%)`; Werte werden auf 0 bis 100 begrenzt."""
    out = [[s, float(c)] for s, c in shown]
    for row, changes in edited_rows.items():
        if "Gewicht (%)" in changes and changes["Gewicht (%)"] is not None:
            out[int(row)][1] = min(max(float(changes["Gewicht (%)"]), 0.0), 100.0) / 100.0
    return tuple((s, c) for s, c in out)


def credit_overrides(base, credits) -> tuple[tuple[str, float], ...]:
    """Welche Gutschriften weichen vom Namen ab? `base` und `credits`: Paare Status, Gutschrift in 0..1 (nach Namen bzw. wie eingestellt); Rückgabe: nur die abweichenden."""
    own = dict(base)
    return tuple((s, float(c)) for s, c in credits if s in own and abs(float(c) - own[s]) > 1e-9)


def edited_overrides(old, base, shown, edited_rows: dict) -> tuple[tuple[str, float], ...]:
    """Abweichungen vom Namen nach einer Änderung der Tabelle: Die bisherigen für Status, die gerade nicht in der Tabelle stehen (anderes Teilprojekt), bleiben; für die gezeigten
    werden sie neu bestimmt. `old`: bisherige Abweichungen, `base`: Gutschriften nach Namen, `shown`: die gezeigten Gutschriften, `edited_rows`: Änderungen von st.data_editor."""
    shown_names = {s for s, _ in shown}
    kept = {s: c for s, c in old if s not in shown_names}
    kept.update(dict(credit_overrides(base, apply_credit_edits(shown, edited_rows))))
    return tuple(kept.items())


_NEW_KEYS = ("todo", "open", "backlog", "offen", "neu", "new", "selected", "ready", "specification", "spezifikation", "estimate", "schatzung")


def new_rank(name: str) -> int:
    """0 für Namen, die nach „noch nicht begonnen“ klingen (Backlog, To Do, Specification …), sonst 1: ordnet Status gleicher Gutschrift in die Reihenfolge des Workflows.
    Namen, die nach fertig, Test, Merged oder Review klingen („Ready4Test“), sind nie „noch nicht begonnen“."""
    key = name_key(name)
    return 0 if status_class(name) == "other" and any(w in key for w in _NEW_KEYS) else 1


# ---------------------------------------------------------------- Hierarchie

def children_of(issues) -> dict[str, list[int]]:
    """Indizes der direkten Kinder je Eltern-Schlüssel."""
    out: dict[str, list[int]] = {}
    for idx, issue in enumerate(issues):
        if issue.parent:
            out.setdefault(issue.parent, []).append(idx)
    return out


def subtree_keys(issues, root: str) -> set[str]:
    """Schlüssel des Tickets `root` und aller Tickets darunter (Kinder, Enkel, ...); Zyklen in den Eltern-Verweisen enden, ohne etwas doppelt zu zählen."""
    if root not in {t.key for t in issues}:
        raise ValueError(f"unbekannte Wurzel {root!r}")
    kids = children_of(issues)
    seen, stack = {root}, [root]
    while stack:
        for j in kids.get(stack.pop(), []):
            if issues[j].key not in seen:
                seen.add(issues[j].key)
                stack.append(issues[j].key)
    return seen


def scope_issues(issues, root: str = C.ROOT_ALL) -> tuple[Issue, ...]:
    """Teilprojekt als eigenständiger Datensatz: das Ticket `root` und alles darunter in der Reihenfolge der Daten. Die Wurzel verliert ihr übergeordnetes Ticket, damit nichts nach außen zeigt:
    Epic-Zuordnung, geerbter Sprint und Hierarchiestufen beginnen dann an der Wurzel. Ohne Wurzel bleibt alles."""
    if root == C.ROOT_ALL:
        return tuple(issues)
    keep = subtree_keys(issues, root)
    return tuple(replace(t, parent="") if t.key == root else t for t in issues if t.key in keep)


def select_atoms(issues, skip: frozenset[int] = frozenset()) -> list[int]:
    """Zählende Tickets: die Blätter des Ticket-Baums, also Tickets ohne Kinder, außer Epics (und höheren Ebenen). Tickets in `skip` (zurückgewiesene) sind keine Atome und gelten auch nicht
    als Kinder: Eine Story, deren Sub-Tasks alle zurückgewiesen sind, ist dann selbst ein Blatt."""
    parents = {t.parent for i, t in enumerate(issues) if i not in skip and t.parent}
    return [i for i, t in enumerate(issues) if i not in skip and not t.is_epic and t.key not in parents]


def tree_depths(issues) -> list[int]:
    """Tiefe jedes Tickets im Ticket-Baum (0 = oberste Stufe der Daten, bei einem Teilprojekt die Wurzel); die Stufe des Tickets im Sinne von „gleiche Stufe“."""
    depth = [0] * len(issues)
    for i, d, _ in tree_order(issues):
        depth[i] = d
    return depth


def tree_order(issues, root: str = C.ROOT_ALL) -> list[tuple[int, int, int]]:
    """Die Tickets als Wald in Tiefensuche-Reihenfolge: (Index, Tiefe, Index des Elternknotens im Baum oder -1). Wurzeln sind Tickets ohne Eltern in der Datei; ein Zyklus
    ohne Wurzel folgt am Ende und beginnt bei seinem ersten Ticket. Mit `root` nur dieser Teilbaum, die Wurzel in Tiefe 0."""
    index = {t.key: n for n, t in enumerate(issues)}
    kids = children_of(issues)
    out: list[tuple[int, int, int]] = []
    seen: set[int] = set()

    def walk(start: int) -> None:
        stack = [(start, 0, -1)]
        while stack:
            i, depth, parent = stack.pop()
            if i in seen:
                continue
            seen.add(i)
            out.append((i, depth, parent))
            for j in reversed(kids.get(issues[i].key, [])):
                stack.append((j, depth + 1, i))

    if root != C.ROOT_ALL:
        if root not in index:
            raise ValueError(f"unbekannte Wurzel {root!r}")
        walk(index[root])
        return out
    for n, t in enumerate(issues):
        if t.parent not in index or t.parent == t.key:
            walk(n)
    for n in range(len(issues)):
        walk(n)
    return out


def parent_root(issues, root: str) -> str:
    """Die Wurzel eine Stufe höher: das übergeordnete Ticket von `root`, wenn es als Wurzel taugt (siehe `root_choices`), sonst das ganze Projekt. Für das ganze Projekt selbst gibt es nichts darüber."""
    if root == C.ROOT_ALL:
        return C.ROOT_ALL
    parent = next((t.parent for t in issues if t.key == root), "")
    return parent if parent in dict(root_choices(issues)) else C.ROOT_ALL


def root_for_click(issues, key: str) -> str | None:
    """Wohin führt ein Klick auf das Ticket `key` in einem Diagramm? Auf ein Ticket, das als Wurzel taugt (siehe `root_choices`, also eines mit Kindern), und auf das ganze Projekt; sonst (Blatt,
    unbekannter Schlüssel, die Sammelwurzel „Projekt“ des Graphen) nirgendwohin (None)."""
    return key if key == C.ROOT_ALL or key in dict(root_choices(issues)) else None


def root_choices(issues) -> list[tuple[str, int]]:
    """Tickets, die als Wurzel einer Teilauswertung taugen (alle mit Kindern, außer Sub-Tasks), in der Reihenfolge des Baums mit ihrer Tiefe."""
    kids = children_of(issues)
    return [(issues[i].key, depth) for i, depth, _ in tree_order(issues) if issues[i].key in kids and not issues[i].is_subtask]


# ---------------------------------------------------------------- Gewichte

def atom_weights(issues, atoms, rule: str = C.DEFAULT_UNEST, basis=None, plan=None, distribute: bool = False) -> np.ndarray:
    """Gewicht je Atom: die Story Points des Tickets; fehlen sie, entscheidet die Regel (die Buchstaben stehen in `jira_constants`). Die Regeln mit Median nehmen den Median der geschätzten Atome
    aus `basis` (Voreinstellung: `atoms`, z. B. die gezählten Atome, wenn die Gewichte zurückgewiesener Atome bestimmt werden), und zwar aus derselben Gruppe wie das Ticket: A gleiche Stufe
    (Tiefe im Ticket-Baum), C gleicher Typ, D gleiches übergeordnetes Ticket, E gleiches Team; B gleiche Stufe im ganzen Plan (`plan`, Voreinstellung `issues`: die Stufe zählt dann in
    den Tiefen des ganzen Plans, nicht des Teilbaums); F die erste Gruppe der Kette Geschwister, Typ, Stufe, sonst der Median aller geschätzten Atome des ganzen Plans. Gibt es in der
    Gruppe kein geschätztes Atom, gilt 1. H setzt 1, I setzt 0 (das Ticket zählt dann nicht im Gewicht). Mit `distribute` teilen die Atome unter einer geschätzten, nicht
    zusammenfassenden Eltern-Story die Story Points der Story gleichmäßig unter sich auf, wenn keines von ihnen eigene Story Points hat; sonst gilt die Regel."""
    if rule not in C.UNEST_RULES:
        raise KeyError(rule)
    pool = [i for i in (atoms if basis is None else basis) if issues[i].points is not None]
    depth = tree_depths(issues)

    def table(key_of, members, source=issues):
        groups: dict = {}
        for i in members:
            groups.setdefault(key_of(i), []).append(source[i].points)
        return {k: float(median(v)) for k, v in groups.items()}
    by_level = table(lambda i: depth[i], pool)
    by_type = table(lambda i: issues[i].type.strip().lower(), pool)
    by_parent = table(lambda i: issues[i].parent, pool)
    by_team = table(lambda i: issues[i].team, pool)
    plan_issues = issues if plan is None else plan
    plan_atoms = select_atoms(plan_issues, skip=rejected_indices(plan_issues))
    plan_pool = [j for j in plan_atoms if plan_issues[j].points is not None]
    plan_depth = dict(zip((t.key for t in plan_issues), tree_depths(plan_issues)))
    plan_by_level = table(lambda j: plan_depth[plan_issues[j].key], plan_pool, plan_issues)
    plan_median = float(median([plan_issues[j].points for j in plan_pool])) if plan_pool else None

    def fill(i: int) -> float:
        t = issues[i]
        if rule == C.UNEST_ONE:
            return 1.0
        if rule == C.UNEST_IGNORE:
            return 0.0
        if rule == C.UNEST_MEDIAN:
            return by_level.get(depth[i], 1.0)
        if rule == C.UNEST_PLAN:
            return plan_by_level.get(plan_depth.get(t.key), 1.0)
        if rule == C.UNEST_TYPE:
            return by_type.get(t.type.strip().lower(), 1.0)
        if rule == C.UNEST_SIBLINGS:
            return by_parent.get(t.parent, 1.0)
        if rule == C.UNEST_TEAM:
            return by_team.get(t.team, 1.0)
        for found in (by_parent.get(t.parent), by_type.get(t.type.strip().lower()), by_level.get(depth[i]), plan_median):         # Rückfallkette
            if found is not None:
                return found
        return 1.0
    share: dict[int, float] = {}
    if distribute:
        by_key = {t.key: t for t in issues}
        members: dict[str, list[int]] = {}
        for i in atoms:
            members.setdefault(issues[i].parent, []).append(i)
        for parent_key, group in members.items():
            parent = by_key.get(parent_key)
            if parent is not None and not parent.is_epic and parent.points is not None and all(issues[i].points is None for i in group):
                share.update({i: parent.points / len(group) for i in group})
    return np.array([issues[i].points if issues[i].points is not None else share.get(i, fill(i)) for i in atoms], dtype=float)


# ---------------------------------------------------------------- Aggregationsebenen

@dataclass(frozen=True)
class Assignment:
    """Zuordnung der Atome zu Gruppen in Koordinatenform: Eintrag k ordnet Atom `atom[k]` der Gruppe `group[k]` mit Anteil `share[k]` zu (hier immer 1: ein Atom liegt in genau einer Gruppe)."""

    labels: tuple[str, ...]
    atom: np.ndarray    # Position in der Atomliste
    group: np.ndarray
    share: np.ndarray


def natural_key(label: str):
    """Sortierschlüssel mit Zahlen als Zahlen (Sprint 2 vor Sprint 10); Gruppen „(ohne …)“ zuletzt."""
    return (label.startswith("("), [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", label)])


def hierarchy_chains(issues) -> list[list[int]]:
    """Je Ticket die Kette der Tickets von der obersten Stufe bis zu ihm selbst (Indizes); Zyklen und fehlende Eltern enden an der Stelle, an der der Baum aufhört."""
    chains: list[list[int]] = [[] for _ in issues]
    for i, _, parent in tree_order(issues):
        chains[i] = (chains[parent] if parent >= 0 else []) + [i]
    return chains


def summary_level(root: str) -> int:
    """Hierarchiestufe der Zusammenfassung: immer die Tickets direkt unter der Wurzel, also Stufe 2 (Stufe 1 ist die Wurzel selbst); im ganzen Projekt, das keine Wurzel hat, die obersten Tickets (Stufe 1)."""
    return 1 if root == C.ROOT_ALL else 2


def level_labels(issues, atoms, level: int) -> list[str]:
    """Gruppe je Atom auf der Hierarchiestufe `level` (1 = oberste Stufe): das Ticket der Kette auf dieser Stufe, bei einem Atom auf genau dieser Stufe es selbst. Ein Atom, das höher
    steht, bekommt „(keine Stufe n)“."""
    chains = hierarchy_chains(issues)
    out = []
    for i in atoms:
        chain = chains[i]
        if len(chain) >= level:
            t = issues[chain[level - 1]]
            out.append(f"{t.key}: {t.summary}" if t.summary else t.key)
        else:
            out.append(f"(keine Stufe {level})")
    return out


def assign_groups(issues, atoms, level: int = 1) -> Assignment:
    """Ordnet jedes Atom der Gruppe seiner Hierarchiestufe `level` zu (siehe `level_labels`)."""
    per_atom = [[label] for label in level_labels(issues, atoms, level)]
    labels = tuple(sorted({g for gs in per_atom for g in gs}, key=natural_key))
    index = {g: n for n, g in enumerate(labels)}
    a_idx, g_idx, share = [], [], []
    for pos, gs in enumerate(per_atom):
        for g in gs:
            a_idx.append(pos)
            g_idx.append(index[g])
            share.append(1.0 / len(gs))
    return Assignment(labels, np.array(a_idx, dtype=int), np.array(g_idx, dtype=int), np.array(share, dtype=float))


def ratio(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    """Quotient je Eintrag; NaN, wo der Nenner nicht positiv ist (eine Gruppe ohne Gewicht hat keinen Fortschritt)."""
    out = np.full(len(denominator), np.nan)
    np.divide(numerator, denominator, out=out, where=denominator > 0)
    return out


@dataclass(frozen=True)
class GroupStats:
    labels: tuple[str, ...]
    weight: np.ndarray      # sum w
    credited: np.ndarray    # sum w*c
    done_weight: np.ndarray  # sum w über erledigte Atome
    count: np.ndarray       # Atome (anteilig)
    done_count: np.ndarray
    unestimated: np.ndarray  # Atome ohne Story Points (anteilig)

    @property
    def progress(self) -> np.ndarray:
        """Gewichteter Fortschritt je Gruppe in [0, 1]; NaN, wenn die Gruppe kein Gewicht hat."""
        return ratio(self.credited, self.weight)

    @property
    def progress_done(self) -> np.ndarray:
        return ratio(self.done_weight, self.weight)


def aggregate(assign: Assignment, w: np.ndarray, c: np.ndarray, done: np.ndarray, unest: np.ndarray) -> GroupStats:
    """Summiert Gewicht, Gutschrift und Zähler je Gruppe mit einem Scatter-Add (np.bincount)."""
    n = len(assign.labels)
    a, s = assign.atom, assign.share

    def total(values):
        return np.bincount(assign.group, weights=values[a] * s, minlength=n)
    return GroupStats(assign.labels, total(w), total(w * c), total(w * done), total(np.ones(len(w))), total(done.astype(float)), total(unest.astype(float)))


def overall(w: np.ndarray, c: np.ndarray, done: np.ndarray) -> tuple[float, float, float]:
    """Gesamtfortschritt über alle Atome: (gewichtet nach Status, nur erledigt nach Gewicht, nur erledigt nach Ticketanzahl); NaN ohne Gewicht bzw. Atome."""
    total = np.array([w.sum()])
    p_w, p_d = (float(ratio(np.array([x]), total)[0]) for x in (np.dot(w, c), np.dot(w, done)))
    p_n = float(done.sum() / len(done)) if len(done) else float("nan")
    return p_w, p_d, p_n


# ---------------------------------------------------------------- Hierarchiegraph

@dataclass(frozen=True)
class TreeGraph:
    """Knoten des Hierarchiegraphen, ein Eintrag je Knoten in Tiefensuche-Reihenfolge (Eltern vor Kindern). `x` ist die Tiefe, `y` die Zeile; Elternknoten stehen mittig
    vor ihren Kindern. `progress` ist NaN, wenn der Knoten nichts Messbares trägt."""

    keys: tuple[str, ...]
    titles: tuple[str, ...]
    types: tuple[str, ...]
    statuses: tuple[str, ...]
    x: np.ndarray
    y: np.ndarray
    parent: np.ndarray        # Position des Elternknotens, -1 für die Wurzel
    weight: np.ndarray
    progress: np.ndarray
    is_atom: np.ndarray
    is_leaf: np.ndarray       # ohne gezeichnete Kinder
    hidden: np.ndarray        # Zahl der Tickets darunter, die nicht gezeichnet werden (zusammengefasste Ebene)
    n_total: int              # Knoten vor dem Zusammenfassen
    shown_depth: int          # tiefste gezeichnete Ebene
    ignored: np.ndarray | None = None      # zurückgewiesene Knoten: zählen nicht, nichts messbar


def tree_graph(issues, atoms, w: np.ndarray, c: np.ndarray, credit_of: dict[str, float], root: str = C.ROOT_ALL, max_nodes: int = C.GRAPH_MAX_NODES,
               excluded: frozenset[int] = frozenset()) -> TreeGraph:
    """Gewicht und Fortschritt je Knoten des Hierarchiebaums. Ein Knoten trägt die Summe seiner Atome (er selbst, falls er eins ist, und alle darunter), der Fortschritt ist
    die gewichtete Gutschrift dieser Summe. Ein Blatt ohne Gewicht zeigt die Gutschrift seines Status (z. B. Sub-Tasks); alles andere ohne Gewicht bleibt leer. Ohne `root` steht
    ein Knoten „Projekt“ über allen Wurzeln. Über `max_nodes` hinaus wird die tiefste Ebene so lange zusammengefasst, bis der Graph passt."""
    order = tree_order(issues, root)
    shift = 0 if root != C.ROOT_ALL else 1
    n = len(order) + shift
    keys = [""] * n
    titles = [""] * n
    types = [""] * n
    statuses = [""] * n
    depth = np.zeros(n, dtype=int)
    parent = np.full(n, -1, dtype=int)
    node_issue = [-1] * n
    if shift:
        keys[0] = "Projekt"
    for p, (i, d, par) in enumerate(order, start=shift):
        node_issue[p] = i
        keys[p], titles[p], types[p], statuses[p] = issues[i].key, issues[i].summary, issues[i].type, issues[i].status
        depth[p] = d + shift
    pos_of_issue = {i: p for p, i in enumerate(node_issue) if i >= 0}
    for p, (_, _, par) in enumerate(order, start=shift):
        parent[p] = pos_of_issue[par] if par >= 0 else (0 if shift else -1)
    wsum = np.zeros(n)
    csum = np.zeros(n)
    is_atom = np.zeros(n, dtype=bool)
    for k, i in enumerate(atoms):
        p = pos_of_issue.get(i)
        if p is not None:
            wsum[p] += w[k]
            csum[p] += w[k] * c[k]
            is_atom[p] = True
    size = np.ones(n, dtype=int)
    for p in range(n - 1, 0, -1):          # Kinder stehen nach ihren Eltern (jeder Knoten außer der ersten hat einen): von hinten summieren
        wsum[parent[p]] += wsum[p]
        csum[parent[p]] += csum[p]
        size[parent[p]] += size[p]
    # zusammenfassen: tiefste Ebene, bei der höchstens max_nodes Knoten bleiben (mindestens die Wurzel)
    fits = np.nonzero(np.cumsum(np.bincount(depth)) <= max_nodes)[0]
    shown_depth = int(fits[-1]) if len(fits) else 0
    keep = [p for p in range(n) if depth[p] <= shown_depth]
    slot = {p: s for s, p in enumerate(keep)}
    kept_kids: dict[int, list[int]] = {}
    for p in keep:
        if parent[p] >= 0:
            kept_kids.setdefault(parent[p], []).append(p)
    y = {}
    row = 0
    for p in keep:                           # Blätter in Tiefensuche-Reihenfolge untereinander
        if p not in kept_kids:
            y[p] = float(row)
            row += 1
    for p in reversed(keep):
        if p in kept_kids:
            y[p] = (y[kept_kids[p][0]] + y[kept_kids[p][-1]]) / 2
    progress, weight, hidden = [], [], []
    for p in keep:
        weight.append(float(wsum[p]))
        if node_issue[p] in excluded:
            progress.append(float("nan"))
        elif wsum[p] > 0:
            progress.append(float(csum[p] / wsum[p]))
        elif p not in kept_kids and size[p] == 1 and node_issue[p] >= 0 and not issues[node_issue[p]].is_epic:
            progress.append(float(credit_of.get(issues[node_issue[p]].status, np.nan)))
        else:
            progress.append(float("nan"))
        hidden.append(int(size[p] - 1) if depth[p] == shown_depth else 0)
    return TreeGraph(
        tuple(keys[p] for p in keep), tuple(titles[p] for p in keep), tuple(types[p] for p in keep), tuple(statuses[p] for p in keep), np.array([depth[p] for p in keep]), np.array([y[p] for p in keep]),
        np.array([slot[parent[p]] if parent[p] >= 0 else -1 for p in keep], dtype=int), np.array(weight), np.array(progress), np.array([is_atom[p] for p in keep]),
        np.array([p not in kept_kids for p in keep]), np.array(hidden, dtype=int), n, shown_depth, np.array([node_issue[p] in excluded for p in keep]))
