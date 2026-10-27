"""Kennzahlen: `analyse` ruft die Einheiten des Kerns nur der Reihe nach auf. Es gibt keine Rechenoptionen außer Teilprojekt, Behandlung ungeschätzter Tickets und von Sub-Tasks und geänderten Status-Gewichten."""

from dataclasses import dataclass, field

import numpy as np

import jira_constants as C
import jira_core as A


@dataclass(frozen=True, kw_only=True)
class Settings:
    unest_rule: str = C.DEFAULT_UNEST                    # Gewicht eines Tickets ohne Story Points
    sub_rule: str = C.DEFAULT_SUB                        # Sub-Tasks einer Story: wie ungeschätzte Tickets, Story Points verteilen oder nur die Story zählen lassen
    level: int | None = None                             # Hierarchiestufe der Zusammenfassung (1 = oberste); ohne Angabe die Tickets direkt unter der Wurzel (siehe `summary_level`)
    root: str = C.ROOT_ALL                               # Teilprojekt: nur für den Graphen; die Tickets müssen schon mit `scope_issues` eingeschränkt sein
    overrides: tuple[tuple[str, float], ...] = ()        # geänderte Status-Gewichte: (Status, Gutschrift in 0..1)


@dataclass(frozen=True)
class Analysis:
    settings: Settings
    credits: dict[str, float]
    n_atoms: int
    weight: float
    progress: float            # gewichtet nach Status
    progress_done: float       # nur erledigt, nach Gewicht
    progress_count: float      # nur erledigt, nach Ticketanzahl
    n_unestimated: int
    stats: A.GroupStats
    tree: A.TreeGraph
    atoms: tuple[int, ...]      # Indizes der Atome in der Ticketliste (Grundlage der Tabellen)
    rejected_atoms: tuple[int, ...]      # zurückgewiesene Atome: zählen nicht
    w: np.ndarray               # Gewicht je Atom
    c: np.ndarray               # Gutschrift je Atom
    done: np.ndarray            # erledigt je Atom
    assign: A.Assignment        # Zuordnung der Atome zur Ebene
    plan: tuple                 # der ganze Plan, auf den sich die Mediane „im ganzen Plan“ beziehen (ohne Angabe die Tickets der Auswertung selbst)
    ctx: dict = field(default_factory=dict, compare=False, repr=False)      # Zwischenergebnisse zu diesen Tickets (siehe `A.cached`); die Tabellen und Regelvergleiche zu dieser Auswertung nutzen sie mit

    @property
    def level(self) -> int:
        return level_of(self.settings)

    @property
    def n_excluded(self) -> int:
        return len(self.rejected_atoms)


def level_of(settings: Settings) -> int:
    """Hierarchiestufe, auf der die Auswertung zusammenfasst: die eingestellte, sonst die Tickets direkt unter der Wurzel."""
    return A.summary_level(settings.root) if settings.level is None else settings.level


def de(x: float, digits: int = 1, sign: bool = False) -> str:
    """Zahl mit Dezimalpunkt; `sign` setzt ein Vorzeichen auch vor positive Werte (für Differenzen)."""
    return f"{x:{'+' if sign else ''}.{digits}f}"


def credit_text(credit: float) -> str:
    """Gutschrift eines Status mit Dezimalpunkt: eine Nachkommastelle, bei Bedarf zwei (0.8; 0.85; 1.0)."""
    text = f"{credit:.2f}"
    return text[:-1] if text.endswith("0") else text


def pct(x: float) -> str:
    return de(100 * x) + " %"


def or_dash(x: float, fmt) -> str:
    """`fmt(x)`, bei NaN (kein Gewicht, nichts messbar) ein Strich."""
    return "–" if np.isnan(x) else fmt(x)


def delta_points(value: float, reference: float) -> str | None:
    """Abstand „Wert minus Referenz“ in Prozentpunkten mit Vorzeichen; ohne Abstand (None), wenn einer der beiden Werte fehlt (NaN)."""
    return None if np.isnan(value) or np.isnan(reference) else f"{de(100 * (value - reference), sign=True)} Punkte"


def status_list(issues) -> list[str]:
    """Alle vorkommenden Status, sortiert nach Gutschrift (nach dem Namen), bei gleicher Gutschrift „noch nicht begonnen“ zuerst, dann nach Name."""
    return sorted({t.status for t in issues}, key=lambda s: (A.status_credit(s), A.new_rank(s), s.lower()))


@dataclass(frozen=True)
class _Counted:
    """Die zählenden Tickets mit Gewicht, Gutschrift und den drei Gesamtwerten: der Teil von `analyse`, den auch der Vergleich der Regeln braucht (ohne Gruppen und Graph)."""

    credit_of: dict[str, float]
    rejected: frozenset[int]
    atoms: list[int]
    rejected_atoms: tuple[int, ...]
    plan: tuple
    w: np.ndarray
    c: np.ndarray
    done: np.ndarray
    unest: np.ndarray
    overall: tuple[float, float, float]      # gewichtet, nur Done nach Gewicht, nur Done nach Anzahl


def _count(issues, settings: Settings, plan, ctx: dict | None = None) -> _Counted:
    """Die zählenden Tickets nach `settings`. Mit `ctx` (siehe `A.cached`) werden Teile, die von der Regel für ungeschätzte Tickets nicht abhängen, bei gleichen `issues` und `plan` nur einmal berechnet."""
    if settings.sub_rule not in C.SUB_RULES:
        raise KeyError(settings.sub_rule)
    if ctx is not None and ctx.setdefault("size", len(issues)) != len(issues):
        raise ValueError("Der Zwischenspeicher gehört zu anderen Tickets")
    subtasks_out = settings.sub_rule == C.SUB_SELF            # c: Sub-Tasks sind weder Atome noch Kinder
    credit_of = A.cached(ctx, ("credit_of", settings.overrides), lambda: A.status_credits(status_list(issues), settings.overrides))
    rejected = A.cached(ctx, "rejected", lambda: A.rejected_indices(issues))
    subtasks = frozenset(i for i, t in enumerate(issues) if t.is_subtask) if subtasks_out else frozenset()
    atoms = A.cached(ctx, ("atoms", subtasks_out), lambda: A.select_atoms(issues, skip=rejected | subtasks))
    rejected_atoms = A.cached(ctx, ("rejected_atoms", subtasks_out), lambda: tuple(i for i in A.select_atoms(issues, skip=subtasks) if i in rejected))
    plan = A.cached(ctx, "plan", lambda: tuple(issues) if plan is None else tuple(plan))
    w = A.atom_weights(issues, atoms, settings.unest_rule, plan=plan, distribute=settings.sub_rule == C.SUB_SHARE, ctx=ctx)
    c, done, unest = A.cached(ctx, ("atom_arrays", subtasks_out, settings.overrides), lambda: (
        np.array([credit_of[issues[i].status] for i in atoms], dtype=float), np.array([A.is_done_status(issues[i].status) for i in atoms], dtype=bool),
        np.array([issues[i].points is None for i in atoms], dtype=bool)))
    return _Counted(credit_of, rejected, atoms, rejected_atoms, plan, w, c, done, unest, A.overall(w, c, done))


def analyse(issues, settings: Settings | None = None, plan=None) -> Analysis:
    """Kennzahlen für die Tickets `issues` (bei einem Teilprojekt der Teilbaum, siehe `scope_issues`); `plan` sind alle Tickets des Plans für die Regeln, die den ganzen Plan brauchen."""
    settings = Settings() if settings is None else settings
    ctx: dict = {}
    n = _count(issues, settings, plan, ctx)
    first = A.assign_groups(issues, n.atoms, level_of(settings), ctx)
    stats = A.aggregate(first, n.w, n.c, n.done, n.unest)
    tree = A.tree_graph(issues, n.atoms, n.w, n.c, n.credit_of, settings.root, excluded=n.rejected, ctx=ctx)
    return Analysis(settings, n.credit_of, len(n.atoms), float(n.w.sum()), *n.overall, int(n.unest.sum()), stats, tree, tuple(n.atoms), n.rejected_atoms, n.w, n.c, n.done, first, n.plan, ctx)


def headline(issues, settings: Settings, plan=None, ctx: dict | None = None) -> tuple[float, float, int, int]:
    """Gesamtfortschritt, Gesamtgewicht, Zahl der Tickets ohne Story Points und Zahl der zählenden Tickets: dieselben Werte wie `analyse`, aber ohne Gruppen und Graph (für den Vergleich der Regeln).
    `ctx`: ein leeres Wörterbuch, das der Aufrufer für eine Reihe von Aufrufen mit denselben Tickets und demselben Plan teilt (siehe `A.cached`)."""
    n = _count(issues, settings, plan, ctx)
    return n.overall[0], float(n.w.sum()), int(n.unest.sum()), len(n.atoms)


def sprint_stats(issues, a: Analysis) -> A.GroupStats:
    """Gewicht und Fortschritt je Sprint: jedes zählende Ticket in seinem letzten Sprint (siehe `A.sprint_labels`), mit den Gewichten und Gutschriften der Auswertung `a`."""
    first = A.assign_labels([[label] for label in A.sprint_labels(issues, a.atoms, a.ctx)])
    return A.aggregate(first, a.w, a.c, a.done, np.array([issues[i].points is None for i in a.atoms], dtype=bool))


def unestimated_note(n_unestimated: int, n_atoms: int, rule: str = C.DEFAULT_UNEST) -> tuple[str, str]:
    """Wie viele Tickets haben keine Story Points, und was macht die gewählte Regel daraus?"""
    if n_atoms == 0:
        return "warning", "Es gibt keine zählenden Tickets."
    if n_unestimated == 0:
        return "success", f"Alle {n_atoms} Tickets haben Story Points."
    share = 100 * n_unestimated / n_atoms
    text = f"{n_unestimated} von {n_atoms} Tickets ({de(share)} %) haben keine Story Points; Regel: {rule}."
    if rule == C.UNEST_IGNORE:
        text += " Diese Tickets tauchen im Fortschritt nicht auf, auch wenn sie noch offen sind."
    return ("warning" if share >= 20 else "info"), text


def check_consistency(a: Analysis, tol: float = 1e-9) -> list[str]:
    """Unabhängiger Prüfer, der auch in der App läuft: Jede Verletzung ist eine Meldung. Erwartet werden Fortschritt in [0, 1] und Gruppen, deren Gewichte und Zähler sich zum
    Gesamtwert summieren (Mehrfachwerte werden anteilig verteilt)."""
    problems = []
    for name, value in (("gewichtet", a.progress), ("nur Done (Gewicht)", a.progress_done), ("nur Done (Anzahl)", a.progress_count)):
        if not np.isnan(value) and not -tol <= value <= 1 + tol:
            problems.append(f"Gesamtfortschritt {name} liegt außerhalb von 0 bis 100 %: {value:.4f}")
    if abs(float(a.stats.weight.sum()) - a.weight) > tol * max(1.0, a.weight):
        problems.append(f"Gruppengewichte summieren sich zu {float(a.stats.weight.sum()):.6f}, erwartet {a.weight:.6f}")
    if abs(float(a.stats.count.sum()) - a.n_atoms) > tol * max(1, a.n_atoms):
        problems.append(f"Gruppen zählen {float(a.stats.count.sum()):.6f} Tickets, erwartet {a.n_atoms}")
    if a.weight > 0 and abs(float(a.stats.credited.sum()) / a.weight - a.progress) > tol:
        problems.append(f"Die Beiträge der Gruppen summieren sich zu {float(a.stats.credited.sum()) / a.weight:.6f}, der Gesamtfortschritt ist {a.progress:.6f}")
    return problems
