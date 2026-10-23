"""Kennzahlen: `analyse` ruft die Einheiten des Kerns nur der Reihe nach auf. Es gibt keine Rechenoptionen außer Teilprojekt, Behandlung ungeschätzter Tickets, Ebene und geänderten Status-Gewichten."""

from dataclasses import dataclass

import numpy as np

import jira_constants as C
import jira_core as A


@dataclass(frozen=True, kw_only=True)
class Settings:
    dimension: str = C.DEFAULT_DIM
    unest_rule: str = C.DEFAULT_UNEST                    # Gewicht eines Tickets ohne Story Points
    level: int = 1                                       # Hierarchiestufe der Ebene „Hierarchiestufe“ (1 = oberste)
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
    hierarchy: A.Hierarchy
    tree: A.TreeGraph
    atoms: tuple[int, ...]      # Indizes der Atome in der Ticketliste (Grundlage der Tabellen)
    rejected_atoms: tuple[int, ...]      # zurückgewiesene Atome: zählen nicht
    w: np.ndarray               # Gewicht je Atom
    c: np.ndarray               # Gutschrift je Atom
    done: np.ndarray            # erledigt je Atom
    assign: A.Assignment        # Zuordnung der Atome zur Ebene

    @property
    def n_excluded(self) -> int:
        return len(self.rejected_atoms)


def de(x: float, digits: int = 1, sign: bool = False) -> str:
    """Zahl mit Dezimalkomma; `sign` setzt ein Vorzeichen auch vor positive Werte (für Differenzen)."""
    return f"{x:{'+' if sign else ''}.{digits}f}".replace(".", ",")


def pct(x: float) -> str:
    return de(100 * x) + " %"


def status_list(issues) -> list[str]:
    """Alle vorkommenden Status, sortiert nach Gutschrift (nach dem Namen), bei gleicher Gutschrift „noch nicht begonnen“ zuerst, dann nach Name."""
    return sorted({t.status for t in issues}, key=lambda s: (A.status_credit(s), A.new_rank(s), s.lower()))


def analyse(issues, settings: Settings = Settings()) -> Analysis:
    credit_of = A.status_credits(status_list(issues), settings.overrides)
    rejected = A.rejected_indices(issues)
    atoms = A.select_atoms(issues, skip=rejected)
    rejected_atoms = tuple(i for i in A.select_atoms(issues) if i in rejected)
    w = A.atom_weights(issues, atoms, settings.unest_rule)
    c = np.array([credit_of[issues[i].status] for i in atoms], dtype=float)
    done = np.array([A.is_done_status(issues[i].status) for i in atoms], dtype=bool)
    unest = np.array([issues[i].points is None for i in atoms], dtype=bool)
    p_w, p_d, p_n = A.overall(w, c, done)
    first = A.assign_groups(issues, atoms, settings.dimension, settings.level)
    stats = A.aggregate(first, w, c, done, unest)
    tree = A.tree_graph(issues, atoms, w, c, credit_of, settings.root, excluded=rejected)
    return Analysis(settings, credit_of, len(atoms), float(w.sum()), p_w, p_d, p_n, int(unest.sum()), stats, A.hierarchy(issues, atoms, w, c), tree, tuple(atoms), rejected_atoms, w, c, done, first)


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
