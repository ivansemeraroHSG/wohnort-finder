"""
data.py – Zugriff auf die SQLite-Datenbank (Arbeitspaket 1).

Verantwortlich: Ivan
Funktionen get_municipalities bis save_rating: mit Claude erstellt, angepasst von Ivan

Alle Funktionen geben pandas-DataFrames mit den vereinbarten Spaltennamen zurück:
bfs_nr, name, kanton, lat, lon, gemeindetyp, steuer_chf,
miete_chf, miete_geschaetzt, pendel_min, pendel_geschaetzt, score.
Verknüpft werden sie immer über bfs_nr.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

# Pfad zur Datenbank (wird von scripts/build_db.py erzeugt)
DB_PATH = Path(__file__).parent / "data" / "wohnort.db"

HAUSHALTE = ["ledig", "verheiratet", "verheiratet_2_kinder"]


def get_connection() -> sqlite3.Connection:
    """Öffnet eine Verbindung zur SQLite-Datenbank und gibt sie zurück."""
    return sqlite3.connect(DB_PATH)


def get_municipalities() -> pd.DataFrame:
    """
    Liefert alle Gemeinden.

    Rückgabe: DataFrame mit bfs_nr, name, kanton, lat, lon, gemeindetyp, typ_gruppe
    """
    with get_connection() as con:
        return pd.read_sql(
            "SELECT bfs_nr, name, kanton, lat, lon, gemeindetyp, typ_gruppe "
            "FROM gemeinden ORDER BY name",
            con,
        )


def get_tax(einkommen: int, haushalt: str) -> pd.DataFrame:
    """
    Liefert die Steuerbelastung pro Gemeinde für ein Einkommen und einen Haushaltstyp.

    In der Datenbank stehen nur einige Einkommensstufen (50'000 bis 300'000 CHF).
    Dazwischen wird linear interpoliert, ausserhalb gilt die nächste Stufe.

    Parameter:
        einkommen: Bruttoeinkommen in CHF pro Jahr
        haushalt:  "ledig", "verheiratet" oder "verheiratet_2_kinder"

    Rückgabe: DataFrame mit bfs_nr, steuer_chf (CHF pro Jahr)
    """
    if haushalt not in HAUSHALTE:
        raise ValueError(f"Unbekannter Haushalt: {haushalt}")
    with get_connection() as con:
        steuern = pd.read_sql(
            "SELECT bfs_nr, einkommen, steuer_chf FROM steuern WHERE haushalt = ?",
            con,
            params=(haushalt,),
        )
    # Eine Zeile pro Gemeinde, eine Spalte pro Einkommensstufe
    tabelle = steuern.pivot(index="bfs_nr", columns="einkommen", values="steuer_chf")
    stufen = tabelle.columns.to_numpy()
    werte = [np.interp(einkommen, stufen, zeile) for zeile in tabelle.to_numpy()]
    return pd.DataFrame({"bfs_nr": tabelle.index, "steuer_chf": np.round(werte)})


def get_rent(zimmer: int) -> pd.DataFrame:
    """
    Liefert die geschätzte Monatsmiete pro Gemeinde für eine Zimmerzahl.

    Das BFS publiziert Mieten nur pro Kanton und pro Gemeindetyp. Die Werte pro
    Gemeinde schätzt scripts/build_db.py aus beiden (Tabelle "mieten").

    Parameter:
        zimmer: Anzahl Zimmer, 1 bis 6 (6 = "6 und mehr")

    Rückgabe: DataFrame mit bfs_nr, miete_chf (CHF pro Monat), miete_geschaetzt (bool)
    """
    zimmer = min(max(int(zimmer), 1), 6)
    with get_connection() as con:
        mieten = pd.read_sql(
            "SELECT bfs_nr, miete_chf, miete_geschaetzt FROM mieten WHERE zimmer = ?",
            con,
            params=(zimmer,),
        )
    mieten["miete_geschaetzt"] = mieten["miete_geschaetzt"].astype(bool)
    return mieten


def save_rating(bfs_nr: int, gefaellt: bool, sitzung: str) -> None:
    """
    Speichert eine Bewertung (anonym) in der Tabelle "bewertungen".

    Parameter:
        bfs_nr:   BFS-Nummer der bewerteten Gemeinde
        gefaellt: True = gefällt, False = gefällt nicht
        sitzung:  zufällige ID der Sitzung (keine Personendaten)
    """
    with get_connection() as con:
        con.execute(
            "INSERT INTO bewertungen (sitzung, bfs_nr, gefaellt) VALUES (?, ?, ?)",
            (sitzung, int(bfs_nr), int(gefaellt)),
        )


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
