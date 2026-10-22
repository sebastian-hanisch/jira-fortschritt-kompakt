"""Plotly-Abbildungen: Fortschrittsbalken, Flächenansicht und Hierarchiegraph. Alle Achsen sind gesperrt (fixedrange), damit Touch-Geräte beim Scrollen nicht am Diagramm hängen bleiben."""

import numpy as np
import plotly.graph_objects as go

import jira_constants as C

MAX_BARS = 30      # mehr Balken lassen sich nicht mehr lesen; die Tabelle darunter zeigt alle Gruppen


def lock_axes(fig):
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    return fig


def _pct_text(progress: float, weight: float, unit: str) -> str:
    return "ohne Gewicht" if np.isnan(progress) else f"{100 * progress:.0f} % · {weight:.0f} {unit}".replace(".", ",")


def build_progress_bars(stats, unit: str):
    """Ein Balken je Gruppe, Länge = Gewicht: erledigt (dunkel), durch Status angerechnet (hell), offen (grau). Beschriftung rechts: Fortschritt und Gewicht."""
    order = sorted(np.argsort(-stats.weight, kind="stable")[:MAX_BARS])           # die gewichtsstärksten Gruppen, in der natürlichen Reihenfolge der Gruppen gezeigt
    labels = [stats.labels[i] for i in order]
    done = np.minimum(stats.done_weight[order], stats.credited[order])
    partial = np.maximum(stats.credited[order] - done, 0.0)
    rest = np.maximum(stats.weight[order] - done - partial, 0.0)
    prog = stats.progress[order]
    fig = go.Figure()
    for name, values, color in (("erledigt", done, C.COLOR_DONE), ("durch Status angerechnet", partial, C.COLOR_PARTIAL), ("offen", rest, C.COLOR_OPEN)):
        fig.add_trace(go.Bar(y=labels, x=values, orientation="h", name=name, marker_color=color, hovertemplate=f"%{{y}}<br>{name}: %{{x:.1f}} {unit}<extra></extra>"))
    top = float(max(stats.weight[order].max(), 1e-9)) if len(order) else 1.0
    for label, p, w in zip(labels, prog, stats.weight[order]):
        fig.add_annotation(x=w, y=label, text=" " + _pct_text(p, w, unit), showarrow=False, xanchor="left", font=dict(size=12))
    fig.update_layout(barmode="stack", height=max(240, 34 * len(labels) + 130), margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h", y=-0.45), plot_bgcolor="rgba(0,0,0,0)")
    fig.update_yaxes(autorange="reversed", automargin=True)
    fig.update_xaxes(title_text=f"Gewicht ({unit})", range=[0, top * 1.6])
    return lock_axes(fig)


def build_treemap(h):
    """Fläche = Gewicht, Farbe = Fortschritt (rot 0 %, gelb 50 %, grün 100 %). Ein Klick auf ein Epic zoomt hinein."""
    fig = go.Figure(go.Treemap(
        ids=list(h.ids), labels=list(h.labels), parents=list(h.parents), values=list(h.values), branchvalues="total",
        marker=dict(colors=list(h.progress), colorscale=C.COLOR_SCALE, cmin=0, cmax=1, colorbar=dict(title="Fortschritt", tickformat=".0%", nticks=5)),
        customdata=list(h.progress), texttemplate="%{label}<br>%{customdata:.0%}", hovertemplate="%{label}<br>Gewicht %{value:.1f}<br>Fortschritt %{customdata:.0%}<extra></extra>"))
    fig.update_layout(height=460, margin=dict(l=0, r=0, t=10, b=0))
    return fig


def _node_hover(g, k: int, unit: str) -> str:
    lines = [g.keys[k] + (f": {g.titles[k]}" if g.titles[k] else "")]
    if g.types[k] or g.statuses[k]:
        lines.append(" · ".join(x for x in (g.types[k], g.statuses[k]) if x))
    lines.append("kein Gewicht" if g.weight[k] <= 0 else f"Gewicht {g.weight[k]:.1f} {unit}".replace(".", ","))
    lines.append("kein Fortschritt messbar" if np.isnan(g.progress[k]) else f"Fortschritt {100 * g.progress[k]:.0f} %")
    if not g.is_atom[k] and g.is_leaf[k] and g.weight[k] <= 0 and not np.isnan(g.progress[k]):
        lines.append("zählt nicht selbst (Zählebene)")
    if g.ignored is not None and g.ignored[k]:
        lines.append("ausgeschlossen: zählt nicht (zurückgewiesen)")
    if g.hidden[k]:
        lines.append(f"{g.hidden[k]} Tickets darunter nicht gezeichnet")
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
    symbol = ["circle" if g.is_leaf[k] else "square" for k in range(n)]
    label_all = n <= C.GRAPH_LABEL_MAX
    text = [g.keys[k] if (label_all or not g.is_leaf[k]) else "" for k in range(n)]
    place = ["middle right" if g.is_leaf[k] else "top center" for k in range(n)]        # Knoten mit Kindern: Schlüssel über den Knoten, damit er nicht auf der Linie zu den Kindern liegt
    known = [k for k in range(n) if not np.isnan(g.progress[k])]
    unknown = [k for k in range(n) if np.isnan(g.progress[k])]
    if known:
        fig.add_trace(go.Scatter(
            x=[g.x[k] for k in known], y=[g.y[k] for k in known], mode="markers+text", text=[text[k] for k in known], textposition=[place[k] for k in known], textfont=dict(size=11),
            marker=dict(size=[size[k] for k in known], symbol=[symbol[k] for k in known], color=[g.progress[k] for k in known], colorscale=C.COLOR_SCALE, cmin=0, cmax=1,
                        line=dict(color="rgba(60,60,60,0.8)", width=1), colorbar=dict(title="Fortschritt", tickformat=".0%", nticks=5, len=0.5)),
            hovertext=[_node_hover(g, k, unit) for k in known], hoverinfo="text", showlegend=False))
    if unknown:
        fig.add_trace(go.Scatter(
            x=[g.x[k] for k in unknown], y=[g.y[k] for k in unknown], mode="markers+text", text=[text[k] for k in unknown], textposition=[place[k] for k in unknown], textfont=dict(size=11),
            marker=dict(size=[size[k] for k in unknown], symbol=[symbol[k] for k in unknown], color="rgba(190,190,190,0.9)", line=dict(color="rgba(60,60,60,0.8)", width=1)),
            hovertext=[_node_hover(g, k, unit) for k in unknown], hoverinfo="text", showlegend=False))
    depth = int(g.x.max()) if n else 0
    fig.update_xaxes(visible=False, range=[-0.4, depth + 1.8])
    fig.update_yaxes(visible=False, autorange="reversed")
    leaves = int(g.is_leaf.sum())
    fig.update_layout(height=int(min(2400, max(300, 17 * leaves + 60))), margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="rgba(0,0,0,0)", showlegend=False)
    return lock_axes(fig)
