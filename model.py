"""
model.py – Machine Learning (Arbeitspaket 3).

Verantwortlich: <Name eintragen>

Enthält:
- k-means: Auswahl möglichst unterschiedlicher Gemeinden zum Bewerten
- logistische Regression: lernt aus den Bewertungen, was der Nutzerin wichtig ist
- Mietmodell: schätzt fehlende Mieten (wird in scripts/build_db.py genutzt)
"""

from __future__ import annotations

import pandas as pd

# Merkmale, mit denen alle Modelle arbeiten
FEATURES = ["steuer_chf", "miete_chf", "pendel_min"]

# Mindestanzahl Bewertungen, damit das Modell trainiert wird (sonst Fallback)
MIN_BEWERTUNGEN = 8


def select_for_rating(df: pd.DataFrame, n: int = 12) -> list[int]:
    """
    Wählt n möglichst unterschiedliche Gemeinden zum Bewerten aus (k-means).

    Parameter:
        df: DataFrame mit bfs_nr und den Spalten aus FEATURES
        n:  Anzahl Gemeinden bzw. Cluster

    Rückgabe: Liste mit den bfs_nr der ausgewählten Gemeinden
    """
    # TODO (AP 3): StandardScaler + KMeans(n_clusters=n); pro Cluster die Gemeinde nächst dem Zentrum
    raise NotImplementedError


def fit_preferences(df_bewertet: pd.DataFrame) -> dict:
    """
    Trainiert eine logistische Regression auf den Bewertungen.

    Parameter:
        df_bewertet: DataFrame mit FEATURES und der Spalte "gefaellt" (1 oder 0)

    Rückgabe: {"modell": trainiertes Modell, "scaler": Scaler,
               "gewichte": {"steuer_chf": 0.45, "pendel_min": 0.35, "miete_chf": 0.20}}
    """
    # TODO (AP 3): LogisticRegression; Gewichte = Beträge der Koeffizienten, auf 1 normiert
    raise NotImplementedError


def score_all(modell: dict, df: pd.DataFrame) -> pd.Series:
    """
    Berechnet für jede Gemeinde den Match-Score mit dem trainierten Modell.

    Rückgabe: Series mit Werten von 0 bis 100 (gleicher Index wie df)
    """
    # TODO (AP 3): predict_proba(...)[:, 1] * 100
    raise NotImplementedError


def train_rent_model(df_mit_miete: pd.DataFrame):
    """
    Trainiert ein Regressionsmodell für die Monatsmiete.

    Wird einmalig in scripts/build_db.py verwendet, um fehlende Mieten zu schätzen.
    Mit Train/Test-Split prüfen und den mittleren Fehler (MAE in CHF) notieren.
    """
    # TODO (AP 3): z. B. RandomForestRegressor oder LinearRegression
    raise NotImplementedError
