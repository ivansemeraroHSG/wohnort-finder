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

import math
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

# Pfad zur Datenbank (wird von scripts/build_db.py erzeugt)
DB_PATH = Path(__file__).parent / "data" / "wohnort.db"
# Zwischenspeicher für API-Antworten. Eigene Datei, die nicht auf GitHub kommt
# (.gitignore), damit sich wohnort.db beim Benutzen der App nicht ändert.
CACHE_PATH = Path(__file__).parent / "data" / "cache.db"

HAUSHALTE = ["ledig", "verheiratet", "verheiratet_2_kinder"]

# --- Kostenansätze fürs Pendeln (Task 1.7), Stand November 2026 ---
# GA Erwachsene 2. Klasse ab Fahrplanwechsel Dezember 2026 (Alliance SwissPass / SBB)
GA_PREIS = 4095
# Strecken-Abo, Tarif T650 von Alliance SwissPass (Ausgabe 01.06.2026, Ziffer 4.1):
# Grundpreis 1 Monat, Erwachsene, 2. Klasse in CHF pro km, mit Rabatt je weiter die Strecke
STRECKENABO_CHF_PRO_KM = 17.22
# (bis Kilometer, Anteil des Grundpreises) für jede Distanzstufe
STRECKENABO_STAFFELUNG = [(4, 1.0), (14, 0.406), (20, 0.375), (39, 0.227), (54, 0.131), (250, 0.112)]
# Jahres-Abo = 9 Monatspreise (T650, Ziffer 4.1.7)
MONATE_PRO_JAHRESABO = 9
# TCS Kilometerkosten 2026 (Musterauto, 15'000 km pro Jahr): total 74 Rp./km;
# variable Kosten (Energie, Unterhalt, Reifen) 4'135 CHF / 15'000 km = 28 Rp./km.
# Wer schon ein Auto hat, zahlt fürs Pendeln nur die variablen Kosten.
AUTO_CHF_PRO_KM_VARIABEL = 0.28
AUTO_CHF_PRO_KM_TOTAL = 0.74
# Arbeitswochen pro Jahr (52 Wochen minus Ferien und Feiertage)
ARBEITSWOCHEN = 46


def oev_abopreis(km: float) -> float:
    """
    Preis eines Jahres-Strecken-Abos (Erwachsene, 2. Klasse) in CHF nach Tarif T650.

    Parameter:
        km: Tarifkilometer der Strecke (ungefähr die Strassendistanz, nicht die Luftlinie)

    Rückgabe: Jahrespreis in CHF, höchstens der Preis des GA
    """
    km = max(4, math.ceil(km))   # Mindestpreis ist der Preis für 4 km
    monatspreis = 0.0
    bisher = 0
    for bis_km, anteil in STRECKENABO_STAFFELUNG:
        km_in_stufe = min(km, bis_km) - bisher
        if km_in_stufe <= 0:
            break
        monatspreis += km_in_stufe * STRECKENABO_CHF_PRO_KM * anteil
        bisher = bis_km
    # Der Tarif rundet auf den nächsten Franken auf
    return min(math.ceil(monatspreis) * MONATE_PRO_JAHRESABO, GA_PREIS)


def get_connection() -> sqlite3.Connection:
    """Öffnet eine Verbindung zur SQLite-Datenbank und gibt sie zurück."""
    return sqlite3.connect(DB_PATH)


def get_cache_connection() -> sqlite3.Connection:
    """Öffnet den Cache für API-Antworten und legt Datei und Tabellen bei Bedarf an."""
    con = sqlite3.connect(CACHE_PATH)
    with con:
        # ÖV-Fahrzeit pro Gemeinde und Arbeitsort (transport.opendata.ch)
        con.execute("""
            CREATE TABLE IF NOT EXISTS pendel_cache (
                bfs_nr INTEGER,
                ziel TEXT,
                minuten REAL,
                abgefragt_am TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (bfs_nr, ziel)
            )""")
        # Auto und Velo pro Gemeinde und Arbeitsort (openrouteservice, Task 2.6)
        con.execute("""
            CREATE TABLE IF NOT EXISTS route_cache (
                bfs_nr INTEGER,
                ziel TEXT,
                profil TEXT,
                minuten REAL,
                km REAL,
                abgefragt_am TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (bfs_nr, ziel, profil)
            )""")
    return con


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
