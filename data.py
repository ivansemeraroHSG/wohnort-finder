"""
data.py – Zugriff auf die Datenbank und feste Kostenwerte (Arbeitspaket 1).

Verantwortlich: Ivan
KI-Hinweis: Mit Claude (Anthropic) erstellt; am 24.11.2026 mit Claude vereinfacht
(Branch WF-5.6-Umbau).

Die Daten liegen in der SQLite-Datenbank data/wohnort.db (gebaut von scripts/build_db.py).
Wir lesen sie wie in Übung 7: Verbindung mit sqlite3, Abfrage mit pd.read_sql und SELECT.
Alle Tabellen werden über die BFS-Nummer (bfs_nr) der Gemeinde verknüpft.
"""

import sqlite3
from pathlib import Path

import pandas as pd

# Pfade zu den Datenbanken (Path wie in Übung 7)
DB_PATH = Path(__file__).parent / "data" / "wohnort.db"
# Zwischenspeicher (Cache) für API-Antworten. Eigene Datei, die nicht auf GitHub kommt
# (steht in .gitignore). So ändert sich wohnort.db beim Benutzen der App nicht.
CACHE_PATH = Path(__file__).parent / "data" / "cache.db"

# Haushaltstypen, für die wir Steuerdaten haben
HAUSHALTE = ["ledig", "verheiratet", "verheiratet_2_kinder"]

# Einkommen, für die wir Steuerdaten haben (CHF pro Jahr, brutto)
EINKOMMENSSTUFEN = [50000, 75000, 100000, 150000, 200000, 300000]

# --- Feste Kostenwerte fürs Pendeln (Quellen: data/raw/QUELLEN.md) ---

# Jahres-Strecken-Abo 2. Klasse: (bis so viele km, Preis pro Jahr in CHF).
# Abgelesen aus dem Tarif T650 von Alliance SwissPass (Ausgabe 01.06.2026).
OEV_PREISE = [
    (5, 684),
    (10, 999),
    (15, 1314),
    (20, 1602),
    (30, 1953),
    (40, 2295),
    (50, 2493),
    (60, 2682),
    (70, 2853),
    (80, 3024),
    (100, 3375),
    (120, 3717),
]
# Wer weiter fährt, kauft ein GA (2. Klasse, ab Dezember 2026)
GA_PREIS = 4095

# Auto, TCS-Kilometerkosten 2026: mit Kauf und Versicherung 74 Rp. pro km,
# nur Benzin, Unterhalt und Reifen 28 Rp. pro km (wenn man schon ein Auto hat)
AUTO_CHF_PRO_KM = 0.74
AUTO_CHF_PRO_KM_VORHANDEN = 0.28

# Arbeitswochen pro Jahr (52 Wochen minus Ferien und Feiertage)
ARBEITSWOCHEN = 46


def get_municipalities():
    """
    Liefert alle Gemeinden.

    Rückgabe: DataFrame mit bfs_nr, name, kanton, lat, lon
    """
    con = sqlite3.connect(DB_PATH)
    gemeinden = pd.read_sql("SELECT bfs_nr, name, kanton, lat, lon FROM gemeinden ORDER BY name", con)
    con.close()
    return gemeinden


def get_tax(einkommen, haushalt):
    """
    Liefert die Einkommenssteuer pro Gemeinde (CHF pro Jahr).

    In der Datenbank stehen nur die Einkommen aus EINKOMMENSSTUFEN. Für ein Einkommen
    dazwischen rechnen wir mit einem Dreisatz zwischen der Stufe darunter und darüber.
    Beispiel: 125'000 CHF liegt genau in der Mitte zwischen 100'000 und 150'000,
    also nehmen wir die Steuer in der Mitte zwischen diesen beiden Stufen.

    Parameter:
        einkommen: Bruttoeinkommen in CHF pro Jahr
        haushalt:  "ledig", "verheiratet" oder "verheiratet_2_kinder"

    Rückgabe: DataFrame mit bfs_nr, steuer_chf
    """
    # Einkommen auf den Bereich begrenzen, für den wir Daten haben
    if einkommen < EINKOMMENSSTUFEN[0]:
        einkommen = EINKOMMENSSTUFEN[0]
    if einkommen > EINKOMMENSSTUFEN[-1]:
        einkommen = EINKOMMENSSTUFEN[-1]

    # Die Stufe darunter und die Stufe darüber suchen
    unten = EINKOMMENSSTUFEN[0]
    oben = EINKOMMENSSTUFEN[1]
    for i in range(len(EINKOMMENSSTUFEN) - 1):
        if EINKOMMENSSTUFEN[i] <= einkommen <= EINKOMMENSSTUFEN[i + 1]:
            unten = EINKOMMENSSTUFEN[i]
            oben = EINKOMMENSSTUFEN[i + 1]
            break

    # Steuern für beide Stufen aus der Datenbank lesen
    abfrage = "SELECT bfs_nr, steuer_chf FROM steuern WHERE haushalt = ? AND einkommen = ?"
    con = sqlite3.connect(DB_PATH)
    steuer_unten = pd.read_sql(abfrage, con, params=(haushalt, unten))
    steuer_oben = pd.read_sql(abfrage, con, params=(haushalt, oben))
    con.close()

    # Beide Tabellen nebeneinander stellen (verknüpft über bfs_nr)
    steuer_unten = steuer_unten.rename(columns={"steuer_chf": "steuer_unten"})
    steuer_oben = steuer_oben.rename(columns={"steuer_chf": "steuer_oben"})
    steuern = steuer_unten.merge(steuer_oben, on="bfs_nr")

    # Dreisatz: Wie weit liegt das Einkommen zwischen den beiden Stufen? (0 = unten, 1 = oben)
    anteil = (einkommen - unten) / (oben - unten)
    steuern["steuer_chf"] = steuern["steuer_unten"] + anteil * (steuern["steuer_oben"] - steuern["steuer_unten"])
    steuern["steuer_chf"] = steuern["steuer_chf"].round()
    return steuern[["bfs_nr", "steuer_chf"]]


def get_rent(zimmer):
    """
    Liefert die geschätzte Monatsmiete pro Gemeinde für eine Zimmerzahl.

    Das BFS publiziert Mieten nur pro Kanton und pro Gemeindetyp. Die Miete pro
    Gemeinde schätzt scripts/build_db.py aus diesen beiden Werten.

    Parameter:
        zimmer: Anzahl Zimmer, 1 bis 6 (6 bedeutet "6 und mehr")

    Rückgabe: DataFrame mit bfs_nr, miete_chf (CHF pro Monat)
    """
    con = sqlite3.connect(DB_PATH)
    mieten = pd.read_sql("SELECT bfs_nr, miete_chf FROM mieten WHERE zimmer = ?", con, params=(zimmer,))
    con.close()
    return mieten


def get_cache_connection():
    """Öffnet den Cache für API-Antworten und legt die Tabellen an, falls sie fehlen."""
    con = sqlite3.connect(CACHE_PATH)
    with con:
        # ÖV-Fahrzeit pro Gemeinde und Arbeitsort (transport.opendata.ch)
        con.execute("""
            CREATE TABLE IF NOT EXISTS oev_zeiten (
                bfs_nr INTEGER,
                ziel TEXT,
                minuten REAL
            )""")
        # Auto- und Velozeit pro Gemeinde und Arbeitsort (openrouteservice)
        con.execute("""
            CREATE TABLE IF NOT EXISTS route_cache (
                bfs_nr INTEGER,
                ziel TEXT,
                profil TEXT,
                minuten REAL,
                km REAL
            )""")
    return con


def oev_kosten(km):
    """ÖV-Kosten pro Jahr in CHF: Jahres-Strecken-Abo aus der Tabelle OEV_PREISE, sonst GA."""
    for bis_km, preis in OEV_PREISE:
        if km <= bis_km:
            return preis
    return GA_PREIS


def auto_kosten(km, buerotage, hat_auto):
    """
    Auto-Kosten pro Jahr in CHF.

    Parameter:
        km:        Strassendistanz für eine Strecke
        buerotage: Tage pro Woche, an denen man ins Büro fährt
        hat_auto:  True = Auto ist schon da, es zählen nur die Fahrkosten
    """
    if hat_auto:
        preis_pro_km = AUTO_CHF_PRO_KM_VORHANDEN
    else:
        preis_pro_km = AUTO_CHF_PRO_KM
    # hin und zurück = 2 Strecken pro Bürotag
    km_pro_jahr = km * 2 * buerotage * ARBEITSWOCHEN
    return round(km_pro_jahr * preis_pro_km)


# --- Kurzer Test: läuft nur bei "python data.py", nicht wenn app.py die Datei importiert ---
if __name__ == "__main__":
    print(get_municipalities().head())
    print(get_tax(125000, "ledig").head())
    print(get_rent(3).head())
    print("ÖV 12 km:", oev_kosten(12), "CHF, ÖV 200 km:", oev_kosten(200), "CHF")
    print("Auto 20 km, 5 Tage:", auto_kosten(20, 5, False), "CHF")
