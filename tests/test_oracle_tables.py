"""Orakel-Test für die Tabellen: Status-Matrix und Fortschritt je Sprint werden ein zweites Mal aus der Definition gerechnet und mit den Tabellen des Werkzeugs verglichen.

Die Referenz nutzt nur Schleifen und Wörterbücher (Gewichte und Zählung stammen aus `solve` in `test_oracle_progress.py`, ebenfalls ohne Code des Werkzeugs). Verglichen wird für Zufallsprojekte
mit allen Regeln für ungeschätzte Tickets und für Sub-Tasks sowie für den ganzen Plan und mehrere Wurzeln. Jeder Wert jeder Zelle muss übereinstimmen."""

import pytest
from test_oracle_progress import CREDIT, DONE, SUBS, UNEST, _rejected, _roots, solve

import jira_constants as C
import jira_core as A
import jira_evaluation as ev
import jira_tables as T
from conftest import random_project

CREDIT_TEXT = {0.8: "0.8", 0.9: "0.9", 1.0: "1.0"}
NO_SPRINT = "(ohne Sprint)"


def _same(a, b):
    if a is None or b is None:
        return a is None and b is None
    return a == pytest.approx(b, rel=1e-9, abs=1e-12)


def _chain(t, by_key):
    """Die Tickets von der obersten Stufe bis `t`."""
    chain, seen = [t], {t.key}
    while chain[0].parent in by_key and chain[0].parent not in seen:
        chain.insert(0, by_key[chain[0].parent])
        seen.add(chain[0].key)
    return chain


def _row_ticket(t, root, by_key):
    """Beschriftung der Zeile und Ticket der Zusammenfassungsstufe (unter der Wurzel, im ganzen Plan die oberste Stufe); ohne diese Stufe „(keine Stufe n)“."""
    level = 2 if root else 1
    chain = _chain(t, by_key)
    if len(chain) < level:
        return f"(keine Stufe {level})", None
    top = chain[level - 1]
    return (f"{top.key}: {top.summary}" if top.summary else top.key), top


def _rejected_leaves(solved, sub):
    """Zurückgewiesene Blätter: Tickets ohne Kinder (egal in welchem Status), keine Epics, bei Regel c ohne Sub-Tasks."""
    candidates = [t for t in solved.scope if not (sub == "c" and t.is_subtask)]
    parents = {t.parent for t in candidates}
    return [t for t in candidates if t.type.lower() != "epic" and t.key not in parents and _rejected(t, solved.by_key)]


def expected_matrix(plan, root, unest, sub):
    solved = solve(plan, root, unest, sub)
    rows = {}

    def entry(t):
        label, _ = _row_ticket(t, root, solved.by_key)
        return rows.setdefault(label, {"by_status": {}, "rejected": 0.0, "credited": 0.0})
    for t in solved.atoms:
        row = entry(t)
        w = solved.weights[t.key]
        row["by_status"][t.status] = row["by_status"].get(t.status, 0.0) + w
        row["credited"] += w * CREDIT[t.status]
    for t in _rejected_leaves(solved, sub):
        entry(t)["rejected"] += t.points if t.points is not None else solved.fallback(t)
    statuses = {t.status for t in solved.atoms}
    done_statuses = {s for s in statuses if CREDIT[s] >= 0.9}
    return rows, statuses, done_statuses


def _check_matrix(got_rows, expected):
    rows, statuses, done_statuses = expected
    by_label = {r[T.ROW_COL]: r for r in got_rows}
    assert set(by_label) == set(rows) | ({T.SUM_LABEL} if rows else set())
    merged = {"by_status": {s: sum(r["by_status"].get(s, 0.0) for r in rows.values()) for s in statuses}, "rejected": sum(r["rejected"] for r in rows.values()),
              "credited": sum(r["credited"] for r in rows.values())}
    for label, row in {**rows, **({T.SUM_LABEL: merged} if rows else {})}.items():
        got = by_label[label]
        assert len(got) == 1 + len(statuses) + 4, label
        for s in statuses:
            head = s + (f" ({CREDIT_TEXT[CREDIT[s]]})" if CREDIT[s] > 0 else "")
            assert _same(got[head], row["by_status"].get(s, 0.0)), (label, s)
        net = sum(row["by_status"].values())
        assert _same(got[T.REJECTED_COL], row["rejected"]) and _same(got[T.TOTAL_NET_COL], net), label
        values = list(got.values())
        completed = sum(row["by_status"].get(s, 0.0) for s in done_statuses) / net if net > 0 and done_statuses else None
        assert _same(values[-2], completed) and _same(got[T.PROGRESS_COL], row["credited"] / net if net > 0 else None), label


def _sprints_of(t, by_key):
    while not t.sprints and t.parent in by_key:
        t = by_key[t.parent]
    return t.sprints


def expected_sprints(plan, root, unest, sub):
    solved = solve(plan, root, unest, sub)
    groups = {}
    for t in solved.atoms:
        sprints = _sprints_of(t, solved.by_key)
        label = sprints[-1] if sprints else NO_SPRINT
        g = groups.setdefault(label, {"n": 0, "w": 0.0, "credited": 0.0, "done": 0.0, "carried": 0, "carried_w": 0.0})
        w = solved.weights[t.key]
        g["n"] += 1
        g["w"] += w
        g["credited"] += w * CREDIT[t.status]
        g["done"] += w if t.status in DONE else 0.0
        if len(sprints) > 1:
            g["carried"] += 1
            g["carried_w"] += w
    order = sorted(groups, key=lambda label: (label == NO_SPRINT, 0 if label == NO_SPRINT else int(label.split()[-1])))
    return order, groups


def _check_sprints(got_rows, expected):
    order, groups = expected
    assert [r[T.SPRINT_COL] for r in got_rows] == (order + [T.SUM_LABEL] if order else [])
    total = {key: sum(g[key] for g in groups.values()) for key in ("n", "w", "credited", "done", "carried", "carried_w")}
    for row in got_rows:
        g = total if row[T.SPRINT_COL] == T.SUM_LABEL else groups[row[T.SPRINT_COL]]
        label = row[T.SPRINT_COL]
        assert row[T.TICKETS_COL] == g["n"] and _same(row[T.SPRINT_WEIGHT_COL], g["w"]), label
        assert _same(row[T.PROGRESS_COL], g["credited"] / g["w"] if g["w"] > 0 else None), label
        assert _same(row[T.SPRINT_DONE_COL], g["done"] / g["w"] if g["w"] > 0 else None), label
        assert row[T.CARRIED_COUNT_COL] == g["carried"] and _same(row[T.CARRIED_WEIGHT_COL], g["carried_w"]), label


@pytest.mark.parametrize("seed", range(8))
def test_the_tables_match_the_reference_for_every_rule_combination_and_root(seed):
    plan = random_project(seed, n_epics=4)
    for root in _roots(plan):
        scoped = A.scope_issues(plan, root)
        for letter, unest in UNEST.items():
            for sub_letter, sub in SUBS.items():
                a = ev.analyse(scoped, ev.Settings(root=root, unest_rule=unest, sub_rule=sub), plan)
                context = (seed, root, letter, sub_letter)
                try:
                    _check_matrix(T.status_matrix(scoped, a)[0], expected_matrix(plan, root, letter, sub_letter))
                    _check_sprints(T.sprint_rows(scoped, a), expected_sprints(plan, root, letter, sub_letter))
                except AssertionError as exc:
                    raise AssertionError(f"{context}: {exc}") from exc
    assert C.NO_SPRINT == NO_SPRINT


def test_the_random_projects_contain_the_cases_the_tables_must_get_right():
    """Damit das Orakel nicht ins Leere läuft: Es kommen zurückgewiesene Blätter, mitgenommene Tickets, Tickets ohne Sprint, Zeilen ohne Stufe und ungeschätzte Tickets vor."""
    seen = dict.fromkeys(("rejected", "carried", "no_sprint", "no_level", "unestimated"), False)
    for seed in range(8):
        plan = random_project(seed, n_epics=4)
        for root in _roots(plan):
            scoped = A.scope_issues(plan, root)
            a = ev.analyse(scoped, ev.Settings(root=root), plan)
            matrix = T.status_matrix(scoped, a)[0]
            seen["rejected"] |= any(r[T.REJECTED_COL] > 0 for r in matrix)
            seen["no_level"] |= any(r[T.ROW_COL].startswith("(keine Stufe") for r in matrix)
            sprints = T.sprint_rows(scoped, a)
            seen["carried"] |= any(r[T.CARRIED_COUNT_COL] > 0 for r in sprints)
            seen["no_sprint"] |= any(r[T.SPRINT_COL] == NO_SPRINT for r in sprints)
            seen["unestimated"] |= a.n_unestimated > 0
    assert all(seen.values()), seen
