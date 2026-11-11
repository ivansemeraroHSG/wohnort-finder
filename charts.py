"""
charts.py – Grafiken und Tabellen (Arbeitspaket 4).

Verantwortlich: <Name eintragen>

Alle Funktionen geben eine Plotly-Figur oder einen DataFrame zurück.
In app.py werden sie mit st.plotly_chart(...) bzw. st.dataframe(...) angezeigt.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def map_chart(df: pd.DataFrame) -> go.Figure:
    """
    Schweizer Karte, Gemeinden nach Score eingefärbt.

    Parameter:
        df: DataFrame mit bfs_nr, name, score (und für den Hover steuer_chf, miete_chf, pendel_min)
    """
    # TODO (AP 4): plotly choropleth_map mit data/gemeinden.geojson
    raise NotImplementedError


def scatter_chart(df: pd.DataFrame, markiert: list[int] | None = None) -> go.Figure:
    """
    Scatterplot Miete (x) gegen Steuern (y), ein Punkt pro Gemeinde, Farbe = Score.

    Parameter:
        df:       DataFrame mit bfs_nr, name, miete_chf, steuer_chf, pendel_min, score
        markiert: bfs_nr, die hervorgehoben werden (Top 5, bewertete Gemeinden)
    """
    # TODO (AP 4): plotly.express.scatter, Achsen mit Einheiten beschriften
    raise NotImplementedError


def weights_chart(gewichte: dict) -> go.Figure:
    """Horizontale Balken: was das Modell gelernt hat (Steuern, Pendelzeit, Miete in %)."""
    # TODO (AP 4)
    raise NotImplementedError


def top5_chart(df: pd.DataFrame) -> go.Figure:
    """Vergleich von Steuern, Miete und Pendelzeit der fünf besten Gemeinden."""
    # TODO (AP 4)
    raise NotImplementedError


def rating_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    Tabelle der gerade zu bewertenden Gemeinden mit Steuern, Miete und Pendelzeit,
    formatiert für die Anzeige (deutsche Spaltennamen, Einheiten).
    """
    # TODO (AP 4)
    raise NotImplementedError
