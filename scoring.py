"""
scoring.py – einfaches Ranking mit festen Gewichten (Arbeitspaket 5).

Verantwortlich: <Name eintragen>

Wird für das MVP verwendet und später als Fallback, wenn eine Nutzerin
noch zu wenige Gemeinden bewertet hat, um das ML-Modell zu trainieren.
"""

from __future__ import annotations

import pandas as pd


def simple_score(df: pd.DataFrame, gewichte: dict) -> pd.Series:
    """
    Berechnet einen Score von 0 bis 100 als gewichtete Summe.

    Jedes Merkmal wird auf 0–1 normiert; tief ist gut, darum 1 - normierter Wert.

    Parameter:
        df:       DataFrame mit steuer_chf, miete_chf, pendel_min
        gewichte: z. B. {"steuer_chf": 0.45, "pendel_min": 0.35, "miete_chf": 0.20}

    Rückgabe: Series mit Scores 0–100 (gleicher Index wie df)
    """
    total = sum(gewichte.values()) or 1
    score = pd.Series(0.0, index=df.index)
    for spalte, gewicht in gewichte.items():
        werte = df[spalte]
        spannweite = werte.max() - werte.min()
        # Normieren auf 0–1; bei gleichen Werten überall 0.5
        normiert = (werte - werte.min()) / spannweite if spannweite else 0.5
        score += (1 - normiert) * gewicht / total
    return (score * 100).round(1)
