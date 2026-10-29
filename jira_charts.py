"""Plotly-Abbildungen: Fortschrittsbalken, Kachelansicht und Teilprojektbaum. Alle Achsen sind gesperrt (fixedrange), damit Touch-Geräte beim Scrollen nicht am Diagramm hängen bleiben."""

import html
from dataclasses import dataclass

import numpy as np
import plotly.graph_objects as go

import jira_constants as C

MAX_BARS = 30      # mehr Balken lassen sich nicht mehr lesen; die Tabelle darunter zeigt alle Gruppen


def lock_axes(fig):
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    return fig


def _pct_text(progress: float, weight: float, unit: str) -> str:
    return "ohne Gewicht" if np.isnan(progress) else f"{100 * progress:.0f} % · {weight:.2f} {unit}"


def build_progress_bars(stats, unit: str):
    """Ein Balken je Gruppe, Länge = Gewicht: erledigt (dunkel), durch Status angerechnet (hell), offen (grau). Beschriftung rechts: Fortschritt und Gewicht."""
    order = sorted(np.argsort(-stats.weight, kind="stable")[:MAX_BARS])           # die gewichtsstärksten Gruppen, in der natürlichen Reihenfolge der Gruppen gezeigt
    labels = [_plain(stats.labels[i]) for i in order]
    done = np.minimum(stats.done_weight[order], stats.credited[order])
    partial = np.maximum(stats.credited[order] - done, 0.0)
    rest = np.maximum(stats.weight[order] - done - partial, 0.0)
    prog = stats.progress[order]
    fig = go.Figure()
    for name, values, color in (("erledigt", done, C.COLOR_DONE), ("durch Status angerechnet", partial, C.COLOR_PARTIAL), ("offen", rest, C.COLOR_OPEN)):
        fig.add_trace(go.Bar(y=labels, x=values, orientation="h", name=name, marker_color=color, hovertemplate=f"%{{y}}<br>{name}: %{{x:.2f}} {unit}<extra></extra>"))
    top = float(max(stats.weight[order].max(), 1e-9)) if len(order) else 1.0
    fig.update_layout(annotations=[dict(x=w, y=label, text=" " + _pct_text(p, w, unit), showarrow=False, xanchor="left", font=dict(size=12)) for label, p, w in zip(labels, prog, stats.weight[order])])
    fig.update_layout(barmode="stack", height=max(240, 34 * len(labels) + 130), margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h", y=-0.45), plot_bgcolor="rgba(0,0,0,0)")
    fig.update_yaxes(autorange="reversed", automargin=True)
    fig.update_xaxes(title_text=f"Gewicht ({unit})", range=[0, top * 1.6])
    return lock_axes(fig)


def squarify(values, x: float, y: float, w: float, h: float) -> list[tuple[float, float, float, float]]:
    """Quadratisches Treemap-Layout (Bruls, Huizing, van Wijk): ein Rechteck (x, y, Breite, Höhe) je Wert, Fläche proportional zum Wert, zusammen genau das Rechteck (x, y, w, h). Die Reihenfolge der
    Rechtecke ist die der Werte (alle > 0). Große Werte zuerst gibt die ansehnlicheren Rechtecke."""
    if not len(values) or w <= 0 or h <= 0:
        return []
    order = sorted(range(len(values)), key=lambda i: -values[i])
    scale = w * h / float(sum(values))
    areas = [values[i] * scale for i in order]
    out: dict[int, tuple[float, float, float, float]] = {}

    def worst(row, side):
        s = sum(row)
        return max(side * side * max(row) / (s * s), s * s / (side * side * min(row)))
    pos = 0
    while pos < len(areas):
        side = min(w, h)
        row = [areas[pos]]
        pos += 1
        while pos < len(areas) and worst(row + [areas[pos]], side) <= worst(row, side):
            row.append(areas[pos])
            pos += 1
        first = pos - len(row)
        s = sum(row)
        if w >= h:                                  # die Reihe wird eine Spalte links
            rw, ry = s / h, y
            for n, a in enumerate(row):
                out[order[first + n]] = (x, ry, rw, a / rw)
                ry += a / rw
            x, w = x + rw, w - rw
        else:                                       # die Reihe wird eine Zeile oben
            rh, rx = s / w, x
            for n, a in enumerate(row):
                out[order[first + n]] = (rx, y, a / rh, rh)
                rx += a / rh
            y, h = y + rh, h - rh
    return [out[i] for i in range(len(values))]


@dataclass(frozen=True)
class Tile:
    """Eine Kachel der Kachelansicht: Rechteck, Schlüssel des Tickets, Stufe (1 = unter der Wurzel, 2 = darunter), Gewicht, Fortschritt (NaN = nichts messbar) und ob sie sich öffnen lässt (hat Kinder)."""

    key: str
    title: str
    level: int
    x: float
    y: float
    w: float
    h: float
    weight: float
    progress: float
    drillable: bool
    framed: bool        # Kachel der Stufe 1, in der die Kinder als Kacheln liegen (die Beschriftung steht dann in einer Kopfzeile)
    node: int


TILE_W, TILE_H = 100.0, 58.0       # Zeichenfläche der Kacheln (Einheiten sind frei, nur das Seitenverhältnis zählt)
TILE_PAD, TILE_HEAD = 0.5, 3.6     # Rand und Kopfzeile einer Kachel der Stufe 1, die Kinder enthält


def tile_layout(g) -> list[Tile]:
    """Kacheln für die Kinder der Wurzel des Teilprojektbaums (Knoten 0) und deren Kinder, Fläche = Gewicht. Knoten ohne Gewicht (zurückgewiesen, ohne Story Points bei „nicht zählen“) haben keine Kachel."""
    kids: dict[int, list[int]] = {}
    for k in range(len(g.keys)):
        if g.parent[k] >= 0:
            kids.setdefault(int(g.parent[k]), []).append(k)

    def heavy(parent: int) -> list[int]:
        return sorted((k for k in kids.get(parent, []) if g.weight[k] > 0), key=lambda k: -g.weight[k])

    def tile(k: int, rect, level: int, framed: bool) -> Tile:
        return Tile(g.keys[k], g.titles[k], level, *rect, float(g.weight[k]), float(g.progress[k]), bool(not g.is_leaf[k] or g.hidden[k] > 0), framed, k)
    tiles: list[Tile] = []
    outer = heavy(0)
    for k, rect in zip(outer, squarify([float(g.weight[k]) for k in outer], 0.0, 0.0, TILE_W, TILE_H)):
        x, y, w, h = rect
        inner = heavy(k)
        framed = bool(inner) and w > 2 * TILE_PAD + 4 and h > TILE_HEAD + TILE_PAD + 2
        tiles.append(tile(k, rect, 1, framed))
        if framed:
            for kk, r in zip(inner, squarify([float(g.weight[kk]) for kk in inner], x + TILE_PAD, y + TILE_HEAD, w - 2 * TILE_PAD, h - TILE_HEAD - TILE_PAD)):
                tiles.append(tile(kk, r, 2, False))
    return tiles


def progress_rgb(p: float) -> tuple[int, int, int]:
    """Farbe zum Fortschritt auf der Skala rot (0 %), gelb (50 %), grün (100 %) als (R, G, B); grau, wenn nichts messbar ist."""
    if p != p:
        return 190, 190, 190
    stops = [(stop, tuple(int(code[i:i + 2], 16) for i in (1, 3, 5))) for stop, code in C.COLOR_SCALE]
    p = min(max(p, 0.0), 1.0)
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if p <= p1:
            t = (p - p0) / (p1 - p0)
            r, gr, b = (round(a + (b_ - a) * t) for a, b_ in zip(c0, c1))
            return r, gr, b
    return stops[-1][1]


def progress_color(p: float, alpha: float = 1.0) -> str:
    """Farbe zum Fortschritt (siehe `progress_rgb`) als rgba-Text."""
    r, g, b = progress_rgb(p)
    return f"rgba({r},{g},{b},{alpha})"


def text_color_on(p: float) -> str:
    """Schriftfarbe mit gutem Kontrast auf der Kachelfarbe zum Fortschritt `p`: weiß auf dunklen, fast schwarz auf hellen Farben."""
    r, g, b = progress_rgb(p)
    return "#ffffff" if 0.299 * r + 0.587 * g + 0.114 * b < 150 else "#1f2933"


def selected_key(points) -> str:
    """Schlüssel des angeklickten Knotens bzw. der angeklickten Kachel aus den Punkten einer Plotly-Auswahl (die Schlüssel stehen in `customdata`); leer ohne Auswahl und bei mehreren
    verschiedenen Schlüsseln (z. B. nach einem Aufziehen eines Rahmens)."""
    keys = set()
    for point in points or []:
        data = point.get("customdata") if isinstance(point, dict) else None
        if isinstance(data, (list, tuple)):
            data = data[0] if data else None
        if isinstance(data, str) and data:
            keys.add(data)
    return next(iter(keys)) if len(keys) == 1 else ""


TILE_LABEL_MIN_W, TILE_LABEL_MIN_H, TILE_LABEL2_MIN_H = 6.5, 2.6, 4.4      # so groß muss eine Kachel (in Zeicheneinheiten) mindestens sein, damit der Schlüssel bzw. Schlüssel und Fortschritt hineinpassen


def tile_label(t: Tile) -> str:
    """Beschriftung einer Kachel ohne Kopfzeile: Schlüssel und Fortschritt, nur der Schlüssel in flachen Kacheln, leer in zu kleinen und in Kacheln mit Kopfzeile."""
    if t.framed or t.w < TILE_LABEL_MIN_W or t.h < TILE_LABEL_MIN_H:
        return ""
    if t.h >= TILE_LABEL2_MIN_H and t.progress == t.progress:
        return f"{t.key}<br>{100 * t.progress:.0f} %"
    return t.key


def build_tiles(g, unit: str):
    """Kachelansicht: Fläche = Gewicht, Farbe = Fortschritt. Die Kinder der Wurzel sind große Kacheln mit einer Kopfzeile, ihre Kinder liegen als kleinere Kacheln darin. Jede Kachel ist ein Balken und in der
    ganzen Fläche anklickbar (`customdata` = Schlüssel); Kacheln mit Kindern lassen sich per Klick als Teilprojekt öffnen, Kacheln ohne Kinder reagieren nicht."""
    tiles = tile_layout(g)
    fig = go.Figure()
    # Die kleinen Kacheln (Stufe 2) liegen innerhalb der großen. Bei überlappenden Balken wählt Plotly für Tooltip und Klick den ersten Trace; er soll die kleine Kachel sein, nicht der Rahmen des
    # Elternknotens. Deshalb steht Stufe 2 in der Trace-Reihenfolge vorn und wird über `zorder` trotzdem vorn gezeichnet.
    for level in (2, 1):
        sel = [t for t in tiles if t.level == level]
        if not sel:
            continue
        hover = [_node_hover(g, t.node, unit) + ("<br><i>Klick: als Teilprojekt öffnen</i>" if t.drillable else "") for t in sel]
        fig.add_trace(go.Bar(
            x=[t.x + t.w / 2 for t in sel], y=[t.h for t in sel], base=[t.y for t in sel], width=[t.w for t in sel], customdata=[[t.key] for t in sel],
            marker=dict(color=[progress_color(t.progress, 0.35 if t.framed else 1.0) for t in sel], line=dict(color="white", width=2 if level == 1 else 1)),
            hovertext=hover, hoverinfo="text", showlegend=False, zorder=level,
            selected=dict(marker=dict(opacity=1)), unselected=dict(marker=dict(opacity=1))))
    notes = []
    for t in tiles:         # Beschriftungen als Annotationen: Der Text von Balken würde bei einer Auswahl (Klick) abgedunkelt, eine Annotation nicht
        if t.framed:
            notes.append(dict(x=t.x + 0.7, y=t.y + 0.4, xanchor="left", yanchor="top", showarrow=False, font=dict(size=12),
                              text=f"<b>{t.key}</b> {100 * t.progress:.0f} %" if t.progress == t.progress else f"<b>{t.key}</b>"))
        elif tile_label(t):
            notes.append(dict(x=t.x + t.w / 2, y=t.y + t.h / 2, xanchor="center", yanchor="middle", showarrow=False, font=dict(size=11, color=text_color_on(t.progress)), text=tile_label(t)))
    fig.update_layout(annotations=notes, barmode="overlay", bargap=0, height=520, margin=dict(l=0, r=0, t=10, b=0), plot_bgcolor="rgba(0,0,0,0)", showlegend=False)
    fig.update_xaxes(visible=False, range=[0, TILE_W], fixedrange=True)
    fig.update_yaxes(visible=False, range=[TILE_H, 0], fixedrange=True)
    return fig


def _plain(text: str) -> str:
    """Text aus den Daten (Titel, Schlüssel, Status) für Plotly: Plotly liest in Beschriftungen und Tooltips einige HTML-Zeichen („<b>“, „<br>“) als Formatierung; mit Entitäten erscheint der Text, wie er ist."""
    return html.escape(text, quote=False)


def _node_hover(g, k: int, unit: str) -> str:
    lines = [_plain(g.keys[k]) + (f": {_plain(g.titles[k])}" if g.titles[k] else "")]
    if g.types[k] or g.statuses[k]:
        lines.append(" · ".join(_plain(x) for x in (g.types[k], g.statuses[k]) if x))
    lines.append("kein Gewicht" if g.weight[k] <= 0 else f"Gewicht {g.weight[k]:.2f} {unit}")
    lines.append("kein Fortschritt messbar" if np.isnan(g.progress[k]) else f"Fortschritt {100 * g.progress[k]:.0f} %")
    if not g.is_atom[k] and g.is_leaf[k] and g.weight[k] <= 0 and not np.isnan(g.progress[k]):
        lines.append("zählt nicht selbst (Zählebene)")
    if g.ignored is not None and g.ignored[k]:
        lines.append("ausgeschlossen: zählt nicht (zurückgewiesen)")
    if g.hidden[k]:
        lines.append(f"{g.hidden[k]} Tickets darunter sind im Sammelknoten „Rest“ zusammengefasst")
    return "<br>".join(lines)


def build_tree_graph(g, unit: str):
    """Hierarchiebaum von links nach rechts: Knotengröße = Gewicht (Summe der Atome darunter), Farbe = Fortschritt, Quadrat = fasst Tickets zusammen, Kreis = Blatt oder Ticket
    ohne Kinder, grau = nichts messbar. Die Beschriftung zeigt den Schlüssel; alle Angaben stehen im Hover."""
    n = len(g.keys)
    xs, ys = [], []
    for k in range(n):
        q = int(g.parent[k])
        if q >= 0:
            mid = (g.x[q] + g.x[k]) / 2
            xs += [g.x[q], mid, mid, g.x[k], None]
            ys += [g.y[q], g.y[q], g.y[k], g.y[k], None]
    fig = go.Figure(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color="rgba(130,130,130,0.55)", width=1.2), hoverinfo="skip", showlegend=False))
    top = float(g.weight.max()) if n else 0.0
    size = np.array([9.0 if top <= 0 or g.weight[k] <= 0 else 9.0 + 25.0 * np.sqrt(g.weight[k] / top) for k in range(n)])
    rest = g.is_rest if g.is_rest is not None else np.zeros(n, dtype=bool)
    symbol = ["diamond" if rest[k] else "circle" if g.is_leaf[k] else "square" for k in range(n)]
    label_all = n <= C.GRAPH_LABEL_MAX
    known = [k for k in range(n) if not np.isnan(g.progress[k])]
    unknown = [k for k in range(n) if np.isnan(g.progress[k])]
    if known:
        fig.add_trace(go.Scatter(
            x=[g.x[k] for k in known], y=[g.y[k] for k in known], mode="markers",
            marker=dict(size=[size[k] for k in known], symbol=[symbol[k] for k in known], color=[g.progress[k] for k in known], colorscale=C.COLOR_SCALE, cmin=0, cmax=1,
                        line=dict(color="rgba(60,60,60,0.8)", width=1), colorbar=dict(title="Fortschritt", tickformat=".0%", nticks=5, len=0.5)),
            hovertext=[_node_hover(g, k, unit) for k in known], hoverinfo="text", showlegend=False, customdata=[g.keys[k] for k in known],
            selected=dict(marker=dict(opacity=1)), unselected=dict(marker=dict(opacity=1))))
    if unknown:
        fig.add_trace(go.Scatter(
            x=[g.x[k] for k in unknown], y=[g.y[k] for k in unknown], mode="markers",
            marker=dict(size=[size[k] for k in unknown], symbol=[symbol[k] for k in unknown], color="rgba(190,190,190,0.9)", line=dict(color="rgba(60,60,60,0.8)", width=1)),
            hovertext=[_node_hover(g, k, unit) for k in unknown], hoverinfo="text", showlegend=False, customdata=[g.keys[k] for k in unknown],
            selected=dict(marker=dict(opacity=1)), unselected=dict(marker=dict(opacity=1))))
    notes = []
    for k in range(n):          # Beschriftung als Annotation (siehe build_tiles); Blätter rechts vom Knoten, Knoten mit Kindern darüber, damit der Schlüssel nicht auf der Linie zu den Kindern liegt
        if not (label_all or not g.is_leaf[k]):
            continue
        radius = size[k] / 2
        if g.is_leaf[k]:
            notes.append(dict(x=g.x[k], y=g.y[k], text=_plain(g.keys[k]), showarrow=False, xanchor="left", yanchor="middle", xshift=radius + 3, font=dict(size=11)))
        else:
            notes.append(dict(x=g.x[k], y=g.y[k], text=_plain(g.keys[k]), showarrow=False, xanchor="center", yanchor="bottom", yshift=radius + 2, font=dict(size=11)))
    depth = int(g.x.max()) if n else 0
    fig.update_xaxes(visible=False, range=[-0.4, depth + 1.8])
    fig.update_yaxes(visible=False, autorange="reversed")
    leaves = int(g.is_leaf.sum())
    fig.update_layout(annotations=notes, height=int(min(2400, max(300, 17 * leaves + 60))), margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="rgba(0,0,0,0)", showlegend=False)
    return lock_axes(fig)
