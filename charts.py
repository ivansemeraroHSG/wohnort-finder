"""
charts.py – Grafiken des Wohnort-Finders (Arbeitspaket 4).

Verantwortlich: Ivan
Mit Claude erstellt, angepasst von Ivan

Alle Funktionen geben eine Plotly-Figur zurück; app.py zeigt sie mit st.plotly_chart an.
Farben: jede Bedeutung hat überall dieselbe Farbe (Verkehrsmittel, Kostenteile).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

GRENZEN = Path(__file__).parent / "data" / "gemeindegrenzen_2026.geojson"

# Zurückhaltende, warme Farben; jede Palette mit einem Farbenblind-Test geprüft
# (scripts der dataviz-Richtlinien: alle Paare unterscheidbar, auch bei Rot-Grün-Schwäche)
VM_FARBEN = {"oev": "#2f6aa3", "auto": "#c0522c", "velo": "#c9961c"}      # Schieferblau, Terrakotta, Ocker
VM_TEXT = {"oev": "ÖV", "auto": "Auto", "velo": "Velo"}
KOSTEN_FARBEN = {"Steuern": "#1e8058", "Miete": "#bd8a2f", "Pendeln": "#a04673"}  # Waldgrün, Ocker, Pflaume
GRAU = "#c9c2b3"
TEXT = "#4a4842"
GITTER = "#e3ddcf"
HEUTE_FARBE = "#22211e"
SCHRIFT = "IBM Plex Sans, Helvetica Neue, Arial, sans-serif"


def chf(betrag):
    """Betrag als Text mit Schweizer Tausendertrennzeichen, z. B. 11'400."""
    return f"{betrag:,.0f}".replace(",", "'")


def layout(fig, titel_x, titel_y, hoehe=460):
    """Einheitliches, ruhiges Aussehen für alle Grafiken."""
    fig.update_layout(
        height=hoehe, margin=dict(l=10, r=20, t=40, b=10),
        separators=".'",   # Schweizer Schreibweise: 11'400
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family=SCHRIFT, color=TEXT),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
        hoverlabel=dict(bgcolor="#fffdf8", font=dict(family=SCHRIFT)),
    )
    fig.update_xaxes(title=titel_x, showgrid=True, gridcolor=GITTER, zeroline=False,
                     tickformat=",.0f", automargin=True)
    fig.update_yaxes(title=titel_y, showgrid=True, gridcolor=GITTER, zeroline=False,
                     tickformat=",.0f", automargin=True)
    return fig


def markierung(fig, df, nrs, x, y, name, symbol, farbe, beschriften):
    """Hebt einzelne Gemeinden hervor (heutiger Wohnort, Top 5)."""
    punkte = df[df["bfs_nr"].isin(nrs)].sort_values(x)
    # Beschriftungen abwechselnd oben und unten, damit nahe Punkte sich nicht überdecken
    positionen = ["top center", "bottom center"] * len(punkte)
    fig.add_trace(go.Scatter(
        x=punkte[x], y=punkte[y], name=name, mode="markers+text" if beschriften else "markers",
        text=punkte["name"], textposition=positionen[:len(punkte)], textfont=dict(color=TEXT, size=12),
        marker=dict(symbol=symbol, size=13, color=farbe, line=dict(color="#f7f4ee", width=2)),
        hovertemplate="<b>%{text}</b><extra></extra>",
    ))


def tradeoff_chart(df: pd.DataFrame, heute_nr: int, top_nrs: list[int]) -> go.Figure:
    """
    Pendelzeit gegen Gesamtkosten: jede Gemeinde ein Punkt, Farbe = bestes Verkehrsmittel.

    Gemeinden unten links sind günstig und nah, also gute Deals.
    """
    daten = df.dropna(subset=["pendel_min", "gesamtkosten"]).copy()
    daten["Verkehrsmittel"] = daten["bestes_vm"].map(VM_TEXT)
    fig = px.scatter(
        daten, x="pendel_min", y="gesamtkosten", color="Verkehrsmittel",
        color_discrete_map={VM_TEXT[k]: v for k, v in VM_FARBEN.items()},
        category_orders={"Verkehrsmittel": list(VM_TEXT.values())},
        custom_data=["name", "kanton", "steuer_chf", "miete_chf", "pendel_chf"],
    )
    fig.update_traces(
        marker=dict(size=8, opacity=0.6, line=dict(color="#f7f4ee", width=1)),
        hovertemplate=("<b>%{customdata[0]}</b> (%{customdata[1]})<br>"
                       "Gesamtkosten %{y:,.0f} CHF/Jahr<br>Pendelzeit %{x:.0f} Min.<br>"
                       "Steuern %{customdata[2]:,.0f} · Miete %{customdata[3]:,.0f}/Mt. · "
                       "Pendeln %{customdata[4]:,.0f}<extra></extra>"),
    )
    markierung(fig, daten, top_nrs, "pendel_min", "gesamtkosten", "Top 5", "diamond", HEUTE_FARBE, True)
    markierung(fig, daten, [heute_nr], "pendel_min", "gesamtkosten", "Heute", "star", HEUTE_FARBE, True)
    return layout(fig, "Pendelzeit pro Weg (Min.)", "Gesamtkosten (CHF pro Jahr)")


def scatter_chart(df: pd.DataFrame, heute_nr: int, top_nrs: list[int]) -> go.Figure:
    """Miete gegen Steuern: zeigt, dass tiefe Steuern oft mit hohen Mieten einhergehen."""
    fig = go.Figure(go.Scatter(
        x=df["miete_chf"], y=df["steuer_chf"], mode="markers", name="Alle Gemeinden",
        marker=dict(size=7, color=GRAU, opacity=0.6),
        text=df["name"], customdata=df["kanton"],
        hovertemplate="<b>%{text}</b> (%{customdata})<br>Miete %{x:,.0f} CHF/Monat<br>"
                      "Steuern %{y:,.0f} CHF/Jahr<extra></extra>",
    ))
    markierung(fig, df, top_nrs, "miete_chf", "steuer_chf", "Top 5", "diamond", VM_FARBEN["oev"], True)
    markierung(fig, df, [heute_nr], "miete_chf", "steuer_chf", "Heute", "star", HEUTE_FARBE, True)
    return layout(fig, "Miete (CHF pro Monat, geschätzt)", "Steuern (CHF pro Jahr)")


def kosten_balken(df: pd.DataFrame, heute_nr: int, top_nrs: list[int]) -> go.Figure:
    """Gesamtkosten der Top 5 und des heutigen Wohnorts, aufgeteilt in Steuern, Miete und Pendeln."""
    # Reihenfolge wie in der Rangliste: zuerst heute, dann Platz 1, 2, 3 ...
    reihen = df.set_index("bfs_nr").loc[[heute_nr] + list(top_nrs)].reset_index()
    namen = [f"{n} (heute)" if nr == heute_nr else n for n, nr in zip(reihen["name"], reihen["bfs_nr"])]
    teile = {"Steuern": reihen["steuer_chf"], "Miete": 12 * reihen["miete_chf"], "Pendeln": reihen["pendel_chf"]}

    fig = go.Figure()
    for teil, werte in teile.items():
        fig.add_trace(go.Bar(
            y=namen, x=werte, name=teil, orientation="h", marker=dict(color=KOSTEN_FARBEN[teil],
                                                                       line=dict(color="#f7f4ee", width=2)),
            hovertemplate=f"{teil}: %{{x:,.0f}} CHF<extra></extra>",
        ))
    # Total rechts neben jedem Balken
    fig.add_trace(go.Scatter(
        y=namen, x=reihen["gesamtkosten"], mode="text", showlegend=False, hoverinfo="skip",
        text=[f"  {chf(v)}" for v in reihen["gesamtkosten"]], textposition="middle right",
        textfont=dict(color=TEXT),
    ))
    fig.update_layout(barmode="stack", legend_traceorder="normal")
    fig = layout(fig, "CHF pro Jahr", None, hoehe=80 + 50 * len(namen))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(range=[0, reihen["gesamtkosten"].max() * 1.18])
    return fig


def lade_grenzen() -> dict:
    """GeoJSON der Gemeindegrenzen (Stand 2026, aus Task 1.3)."""
    with open(GRENZEN, encoding="utf-8") as datei:
        return json.load(datei)


def map_chart(df: pd.DataFrame, grenzen: dict, ziel_lat: float, ziel_lon: float) -> go.Figure:
    """Karte: Gemeinden nach Ersparnis gegenüber heute eingefärbt (blau = günstiger, terrakotta = teurer)."""
    grenze = max(abs(df["ersparnis"].quantile(0.05)), abs(df["ersparnis"].quantile(0.95)))
    fig = px.choropleth_map(
        df, geojson=grenzen, locations="bfs_nr", featureidkey="properties.bfs_nr",
        color="ersparnis", range_color=(-grenze, grenze),
        color_continuous_scale=[(0, VM_FARBEN["auto"]), (0.5, "#ece7dc"), (1, VM_FARBEN["oev"])],
        custom_data=["name", "gesamtkosten", "pendel_min"],
        map_style="carto-positron", center={"lat": 46.8, "lon": 8.2}, zoom=6.4, opacity=0.8,
    )
    fig.update_traces(
        marker_line_width=0.2, marker_line_color="white",
        hovertemplate=("<b>%{customdata[0]}</b><br>Ersparnis %{z:,.0f} CHF/Jahr<br>"
                       "Gesamtkosten %{customdata[1]:,.0f} CHF<br>Pendelzeit %{customdata[2]:.0f} Min."
                       "<extra></extra>"),
    )
    fig.add_trace(go.Scattermap(
        lat=[ziel_lat], lon=[ziel_lon], mode="markers", name="Arbeitsort",
        marker=dict(size=14, color=HEUTE_FARBE), hovertemplate="Arbeitsort<extra></extra>",
    ))
    fig.update_layout(
        height=520, margin=dict(l=0, r=0, t=0, b=0), showlegend=False,
        coloraxis_colorbar=dict(title="Ersparnis<br>CHF/Jahr", tickformat=",.0f"),
        separators=".'", font=dict(family=SCHRIFT, color=TEXT),
    )
    return fig


def zeitwert_chart(antworten: pd.DataFrame, zeitwert: float | None) -> go.Figure:
    """
    Die Paarvergleiche der Nutzerin und der gelernte Zeitwert als Trennlinie.

    x = Minuten, die die nähere Gemeinde pro Strecke spart; y = wie viel sie pro Jahr mehr kostet.
    Unter der Linie lohnt sich die nähere Gemeinde (nach dem Modell), darüber die günstigere.
    """
    a_naeher = antworten["pendel_min_a"] < antworten["pendel_min_b"]
    gespart = (antworten["pendel_min_a"] - antworten["pendel_min_b"]).abs()
    mehrkosten = (antworten["gesamtkosten_a"] - antworten["gesamtkosten_b"]).where(
        a_naeher, antworten["gesamtkosten_b"] - antworten["gesamtkosten_a"])
    naeher_gewaehlt = (antworten["wahl_a"] == 1) == a_naeher

    fig = go.Figure()
    for gewaehlt, name, farbe in [(True, "Nähere gewählt", VM_FARBEN["oev"]),
                                  (False, "Günstigere gewählt", VM_FARBEN["auto"])]:
        auswahl = naeher_gewaehlt == gewaehlt
        fig.add_trace(go.Scatter(
            x=gespart[auswahl], y=mehrkosten[auswahl], mode="markers", name=name,
            marker=dict(size=11, color=farbe, line=dict(color="#f7f4ee", width=2)),
            hovertemplate="%{x:.0f} Min. kürzer, %{y:,.0f} CHF teurer<extra>" + name + "</extra>",
        ))
    if zeitwert is not None and len(gespart) > 0:
        x_max = gespart.max() * 1.1
        fig.add_trace(go.Scatter(
            x=[0, x_max], y=[0, zeitwert * x_max], mode="lines", name="Dein Zeitwert",
            line=dict(color=HEUTE_FARBE, width=2, dash="dash"), hoverinfo="skip",
        ))
    fig = layout(fig, "Minuten kürzer pro Strecke", "Mehrkosten pro Jahr (CHF)", hoehe=380)
    fig.update_yaxes(rangemode="tozero")
    fig.update_xaxes(rangemode="tozero")
    return fig
