"""
scoring.py – Wohnkosten pro Gemeinde (Arbeitspaket 5).

Verantwortlich: Ivan
Mit Claude erstellt, angepasst von Ivan

Die Wohnkosten sind die Grundlage des Rankings und der Fallback, wenn eine
Nutzerin noch zu wenige Gemeinden bewertet hat, um das ML-Modell zu trainieren.
"""

from __future__ import annotations

import pandas as pd

MONATE = 12


def wohnkosten(df: pd.DataFrame) -> pd.Series:
    """Wohnkosten in CHF pro Jahr: Steuern plus zwölf Monatsmieten."""
    return df["steuer_chf"] + MONATE * df["miete_chf"]
