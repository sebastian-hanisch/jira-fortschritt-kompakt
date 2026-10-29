"""Orakel-Test: Der Fortschritt wird ein zweites Mal aus der Definition gerechnet, ohne Code des Werkzeugs (kein numpy, keine Hilfsfunktionen aus `jira_core`), und mit `analyse` verglichen.

Die Definition (Abschnitt „So wird gerechnet“): Zählende Tickets sind die Blätter des Ticket-Baums (keine Epics; zurückgewiesene Tickets samt allem darunter fallen heraus). Gewicht ist
die Story-Points-Zahl, bei fehlender Zahl entscheidet die Regel A bis F, H oder I. Die Gutschrift folgt dem Statusnamen. Fortschritt = Summe(Gewicht · Gutschrift) / Summe(Gewicht).

Verglichen wird für Zufallsprojekte in allen Kombinationen aus Regel für ungeschätzte Tickets (8), Regel für Sub-Tasks (3) und Wurzel (ganzer Plan, Epics, Stories mit Sub-Tasks).
Die Statusnamen stammen aus `conftest.STATUSES`; ihre Gutschriften stehen hier ausdrücklich, damit auch die Erkennung der Namen unabhängig geprüft wird."""

import dataclasses
import math
import statistics
import types

import pytest

import jira_constants as C
import jira_core as A
import jira_evaluation as ev
from conftest import random_project

CREDIT = {"Backlog": 0.0, "Specification": 0.0, "In Arbeit": 0.0, "In Review": 0.8, "Merged": 0.8, "Ready4Test": 0.9, "Ready4Prod": 1.0}
DONE = {"Ready4Prod"}
UNEST = {"A": C.UNEST_MEDIAN, "B": C.UNEST_PLAN, "C": C.UNEST_TYPE, "D": C.UNEST_SIBLINGS, "E": C.UNEST_TEAM, "F": C.UNEST_CHAIN, "H": C.UNEST_ONE, "I": C.UNEST_IGNORE}
SUBS = {"a": C.SUB_RULE, "b": C.SUB_SHARE, "c": C.SUB_SELF}


def _depth(t, by_key):
    depth, seen = 0, {t.key}
    while t.parent in by_key and t.parent not in seen:
        t = by_key[t.parent]
        seen.add(t.key)
        depth += 1
    return depth


def _rejected(t, by_key):
    seen = set()
    while t is not None and t.key not in seen:
        if t.status == "Rejected":
            return True
        seen.add(t.key)
        t = by_key.get(t.parent)
    return False


def _atoms(items, sub):
    """Zählende Tickets nach der Definition."""
    by_key = {t.key: t for t in items}
    live = [t for t in items if not _rejected(t, by_key) and not (sub == "c" and t.is_subtask)]
    parents_with_live_child = {t.parent for t in live}
    return [t for t in live if t.type.lower() != "epic" and t.key not in parents_with_live_child]


def _median(values):
    return statistics.median(values) if values else None


def _or_one(value):
    return 1.0 if value is None else value


def solve(plan, root, unest, sub):
    """Bestimmt aus der Definition den Ausschnitt (`scope`: die Tickets unter der Wurzel, die Wurzel ohne Eltern), die zählenden Tickets (`atoms`), ihre Gewichte (`weights`, nach Schlüssel) und die
    Ersatzregel (`fallback(ticket)`), auch für Tickets, die selbst nicht zählen. `plan` sind alle Tickets, `root` der Schlüssel der Wurzel oder leer."""
    plan_by_key = {t.key: t for t in plan}
    if root:
        keep, frontier = {root}, [root]
        while frontier:
            current = frontier.pop()
            for t in plan:
                if t.parent == current and t.key not in keep:
                    keep.add(t.key)
                    frontier.append(t.key)
        scope = [t if t.key != root else dataclasses.replace(t, parent="") for t in plan if t.key in keep]
    else:
        scope = list(plan)
    by_key = {t.key: t for t in scope}
    atoms = _atoms(scope, sub)
    pool = [a for a in atoms if a.points is not None]
    plan_pool = [a for a in _atoms(plan, sub) if a.points is not None]

    def level(t):
        return _depth(t, by_key)

    def fallback(t):
        if unest == "H":
            return 1.0
        if unest == "I":
            return 0.0
        if unest == "A":
            return _or_one(_median([a.points for a in pool if level(a) == level(t)]))
        if unest == "B":
            return _or_one(_median([a.points for a in plan_pool if _depth(a, plan_by_key) == _depth(plan_by_key[t.key], plan_by_key)]))
        if unest == "C":
            return _or_one(_median([a.points for a in pool if a.type.strip().lower() == t.type.strip().lower()]))
        if unest == "D":
            return _or_one(_median([a.points for a in pool if a.parent == t.parent]))
        if unest == "E":
            return _or_one(_median([a.points for a in pool if a.team == t.team]))
        for group in ([a for a in pool if a.parent == t.parent], [a for a in pool if a.type.strip().lower() == t.type.strip().lower()], [a for a in pool if level(a) == level(t)],
                      plan_pool):
            found = _median([a.points for a in group])
            if found is not None:
                return found
        return 1.0

    weights = {}
    for t in atoms:
        if t.points is not None:
            weights[t.key] = t.points
            continue
        shared = None
        if sub == "b":
            parent = by_key.get(t.parent)
            siblings = [a for a in atoms if a.parent == t.parent]
            if parent is not None and parent.type.lower() != "epic" and parent.points is not None and all(a.points is None for a in siblings):
                shared = parent.points / len(siblings)
        weights[t.key] = shared if shared is not None else fallback(t)
    return types.SimpleNamespace(scope=scope, by_key=by_key, atoms=atoms, weights=weights, fallback=fallback)


def reference(plan, root, unest, sub):
    """Rechnet Gewicht, Fortschritt, „nur Done“ und Anzahl aus der Definition (siehe `solve`)."""
    solved = solve(plan, root, unest, sub)
    atoms, weights = solved.atoms, solved.weights
    total = sum(weights.values())
    if total <= 0:
        return {"weight": total, "n": len(atoms), "progress": math.nan, "done": math.nan, "unestimated": sum(a.points is None for a in atoms)}
    return {"weight": total, "n": len(atoms), "progress": sum(weights[a.key] * CREDIT[a.status] for a in atoms) / total, "done": sum(weights[a.key] for a in atoms if a.status in DONE) / total,
            "unestimated": sum(a.points is None for a in atoms)}


def _roots(plan):
    """Ganzer Plan, alle Epics und bis zu drei Stories mit Sub-Tasks."""
    with_children = {t.parent for t in plan if t.parent}
    epics = [t.key for t in plan if t.type == "Epic"]
    stories = [t.key for t in plan if t.key in with_children and t.type != "Epic" and not t.is_subtask][:3]
    return [""] + epics + stories


def _same(a, b):
    return (math.isnan(a) and math.isnan(b)) or a == pytest.approx(b, rel=1e-9, abs=1e-12)


@pytest.mark.parametrize("seed", range(12))
def test_analyse_matches_the_reference_for_every_rule_combination_and_root(seed):
    plan = random_project(seed, n_epics=4)
    for root in _roots(plan):
        scoped = A.scope_issues(plan, root)
        for letter, unest in UNEST.items():
            for sub_letter, sub in SUBS.items():
                got = ev.analyse(scoped, ev.Settings(root=root, unest_rule=unest, sub_rule=sub), plan)
                want = reference(plan, root, letter, sub_letter)
                context = (seed, root, letter, sub_letter)
                assert got.n_atoms == want["n"] and got.n_unestimated == want["unestimated"], context
                assert _same(got.weight, want["weight"]) and _same(got.progress, want["progress"]), context
                assert _same(got.progress_done, want["done"]), context
