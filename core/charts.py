import plotly.graph_objects as go
from plotly.subplots import make_subplots
from .models import CollectResult, ParsedQuery


def choose_chart(query: ParsedQuery, result: CollectResult) -> str:
    if query.wants_relation and len(result.units) >= 2:
        return "scatter"
    if result.df["date"].nunique() == 1 and result.df["region"].nunique() > 1:
        return "bar"
    return "line"


def build_chart(query: ParsedQuery, result: CollectResult):
    kind = choose_chart(query, result)
    df, units = result.df, result.units
    keys = list(units)
    title = f"{query.period_label} {query.region or ''} " + ", ".join(units[k][0] for k in keys)

    if kind == "scatter":
        x, y = keys[0], keys[1]
        fig = go.Figure(go.Scatter(x=df[x], y=df[y], mode="markers", name=df["region"].iloc[0]))
        fig.update_layout(title=title.strip(),
                          xaxis_title=f"{units[x][0]} ({units[x][1]})",
                          yaxis_title=f"{units[y][0]} ({units[y][1]})")
        return fig

    fig = make_subplots(rows=len(keys), cols=1, shared_xaxes=True, vertical_spacing=0.08)
    for i, k in enumerate(keys, start=1):
        label, unit = units[k]
        for region, g in df.groupby("region"):
            if kind == "bar":
                tr = go.Bar(x=g["date"], y=g[k], name=f"{region} {label}")
            else:
                tr = go.Scatter(x=g["date"], y=g[k], mode="lines+markers", name=f"{region} {label}")
            fig.add_trace(tr, row=i, col=1)
        fig.update_yaxes(title_text=f"{label} ({unit})", row=i, col=1)
    fig.update_xaxes(title_text="날짜", row=len(keys), col=1)
    fig.update_layout(title=title.strip(), height=320 * len(keys) + 80, legend_title_text="범례")
    return fig
