"""
data.py – Zugriff auf die SQLite-Datenbank (Arbeitspaket 1).

Verantwortlich: <Name eintragen>

Alle Funktionen geben pandas-DataFrames mit den vereinbarten Spaltennamen zurück:
bfs_nr, name, kanton, lat, lon, gemeindetyp, einwohner, steuer_chf,
miete_chf, miete_geschaetzt, pendel_min, pendel_geschaetzt, score.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

# Pfad zur Datenbank (wird von scripts/build_db.py erzeugt)
DB_PATH = Path(__file__).parent / "data" / "wohnort.db"


def get_connection() -> sqlite3.Connection:
    """Öffnet eine Verbindung zur SQLite-Datenbank und gibt sie zurück."""
    return sqlite3.connect(DB_PATH)


def get_municipalities() -> pd.DataFrame:
    """
    Liefert alle Gemeinden.

    Rückgabe: DataFrame mit bfs_nr, name, kanton, lat, lon, gemeindetyp, einwohner
    """
    # TODO (AP 1): SQL-Abfrage auf die Tabelle "gemeinden"
    raise NotImplementedError


def get_tax(einkommen: int, haushalt: str) -> pd.DataFrame:
    """
    Liefert die Steuerbelastung pro Gemeinde für ein Einkommen und einen Haushaltstyp.

    Parameter:
        einkommen: Bruttoeinkommen in CHF pro Jahr
        haushalt:  "ledig", "verheiratet" oder "verheiratet_2_kinder"

    Rückgabe: DataFrame mit bfs_nr, steuer_chf (CHF pro Jahr)
    """
    # TODO (AP 1): Werte der nächsten Einkommensstufen lesen und linear interpolieren
    raise NotImplementedError


def get_rent(zimmer: int) -> pd.DataFrame:
    """
    Liefert die durchschnittliche Monatsmiete pro Gemeinde für eine Zimmerzahl.

    Parameter:
        zimmer: Anzahl Zimmer (z. B. 2, 3, 4)

    Rückgabe: DataFrame mit bfs_nr, miete_chf (CHF pro Monat), miete_geschaetzt (bool)
    """
    # TODO (AP 1): SQL-Abfrage auf die Tabelle "mieten"
    raise NotImplementedError


def save_rating(bfs_nr: int, gefaellt: bool, sitzung: str) -> None:
    """
    Speichert eine Bewertung (anonym) in der Tabelle "bewertungen".

    Parameter:
        bfs_nr:   BFS-Nummer der bewerteten Gemeinde
        gefaellt: True = gefällt, False = gefällt nicht
        sitzung:  zufällige ID der Sitzung (keine Personendaten)
    """
    # TODO (AP 1): INSERT in die Tabelle "bewertungen"
    raise NotImplementedError


def fake_municipalities(n: int = 30, seed: int = 42) -> pd.DataFrame:
    """
    Erzeugt erfundene Gemeinden mit allen vereinbarten Spalten.

    Damit können AP 3, 4 und 5 arbeiten, bevor die echten Daten bereit sind.

    Parameter:
        n:    Anzahl erfundener Gemeinden
        seed: Startwert für den Zufallsgenerator (gleiche Daten bei jedem Aufruf)

    Rückgabe: DataFrame mit allen Standardspalten (score ist leer)
    """
    rng = np.random.default_rng(seed)
    kantone = ["ZH", "SG", "ZG", "SZ", "BE", "LU", "AG", "TG"]
    df = pd.DataFrame({
        "bfs_nr": np.arange(1, n + 1),
        "name": [f"Testgemeinde {i}" for i in range(1, n + 1)],
        "kanton": rng.choice(kantone, n),
        # Koordinaten ungefähr innerhalb der Schweiz
        "lat": rng.uniform(46.2, 47.6, n).round(4),
        "lon": rng.uniform(6.5, 9.8, n).round(4),
        "gemeindetyp": rng.choice(["städtisch", "intermediär", "ländlich"], n),
        "einwohner": rng.integers(800, 40000, n),
        "steuer_chf": rng.integers(6000, 22000, n),
        "miete_chf": rng.integers(1300, 3200, n),
        "miete_geschaetzt": rng.choice([True, False], n),
        "pendel_min": rng.integers(10, 90, n),
        "pendel_geschaetzt": rng.choice([True, False], n),
    })
    df["score"] = np.nan
    return df
