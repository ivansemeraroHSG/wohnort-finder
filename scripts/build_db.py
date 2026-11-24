"""
build_db.py – baut die SQLite-Datenbank data/wohnort.db aus den Rohdaten in data/raw/.

Verantwortlich: Ivan (Arbeitspaket 1)
KI-Hinweis: Mit Claude (Anthropic) erstellt; am 24.11.2026 mit Claude vereinfacht
(Branch WF-5.6-Umbau).

Ausführen im Projektordner:  python scripts/build_db.py
Vorher muss scripts/grenzen_aufbereiten.py gelaufen sein (für die Koordinaten).
Die Datenbank wird bei jedem Lauf komplett neu gebaut.

Tabellen in der Datenbank (alle verknüpft über bfs_nr):
- gemeinden: bfs_nr, name, kanton, lat, lon
- steuern:   bfs_nr, haushalt, einkommen, steuer_chf
- mieten:    bfs_nr, zimmer, miete_chf
"""

import json
import sqlite3
from pathlib import Path

import pandas as pd

# Ordner des Projekts (eine Ebene über scripts/)
ORDNER = Path(__file__).parent.parent
RAW = ORDNER / "data" / "raw"
DB = ORDNER / "data" / "wohnort.db"
GRENZEN = ORDNER / "data" / "gemeindegrenzen_2026.geojson"

# Kantonskürzel in der Reihenfolge des BFS (CantonId 1 = ZH, 2 = BE, ...)
KANTON_KUERZEL = [
    "ZH", "BE", "LU", "UR", "SZ", "OW", "NW", "GL", "ZG", "FR", "SO", "BS", "BL",
    "SH", "AR", "AI", "SG", "GR", "AG", "TG", "TI", "VD", "VS", "NE", "GE", "JU",
]

# In den BFS-Miettabellen: Zimmerzahl -> Spalte mit der Miete (6 = "6 und mehr")
MIET_SPALTEN = {1: 3, 2: 5, 3: 7, 4: 9, 5: 11, 6: 13}

# Anzahl Zeilen unter «Schweiz» in den Miettabellen
ANZAHL_KANTONE = 26
ANZAHL_TYPGRUPPEN = 5


def typ_gruppe(typ):
    """
    Ordnet den Gemeindetyp (11 bis 33) einer der 5 Gruppen der BFS-Miettabelle zu.

    Erste Ziffer: 1 = städtisch, 2 = periurban, 3 = ländlich.
    Die drei städtischen Typen (11, 12, 13) bleiben einzeln (Gruppe 1, 2, 3),
    periurban wird Gruppe 4, ländlich Gruppe 5.
    """
    erste_ziffer = typ // 10
    zweite_ziffer = typ % 10
    if erste_ziffer == 1:
        return zweite_ziffer
    elif erste_ziffer == 2:
        return 4
    else:
        return 5


def mittelpunkte_laden():
    """
    Koordinaten jeder Gemeinde aus der Datei mit den Gemeindegrenzen.

    Eine Gemeinde kann aus mehreren Teilflächen bestehen (z. B. eine Exklave). Wir nehmen
    die grösste Teilfläche und davon den Mittelwert aller Eckpunkte. Als Mass für die Grösse
    dient das Rechteck um die Fläche (Breite × Höhe), das ist einfacher als die echte Fläche.
    """
    with open(GRENZEN, encoding="utf-8") as datei:
        grenzen = json.load(datei)

    zeilen = []
    for gemeinde in grenzen["features"]:
        # Grösste Teilfläche suchen. polygon[0] ist der Aussenrand, als Liste von [lon, lat].
        rand = []
        groesste = 0
        for polygon in gemeinde["geometry"]["coordinates"]:
            lons = []
            lats = []
            for lon, lat in polygon[0]:
                lons.append(lon)
                lats.append(lat)
            groesse = (max(lons) - min(lons)) * (max(lats) - min(lats))
            if groesse > groesste:
                groesste = groesse
                rand = polygon[0]
        # Mittelwert der Eckpunkte. Achtung: GeoJSON speichert [lon, lat].
        summe_lon = 0
        summe_lat = 0
        for lon, lat in rand:
            summe_lon = summe_lon + lon
            summe_lat = summe_lat + lat
        zeilen.append({
            "bfs_nr": gemeinde["properties"]["bfs_nr"],
            "lat": round(summe_lat / len(rand), 4),
            "lon": round(summe_lon / len(rand), 4),
        })
    return pd.DataFrame(zeilen)


def gemeinden_laden():
    """Gemeindeliste 2026 mit Kanton, Gemeindetyp-Gruppe und Koordinaten."""
    roh = pd.read_csv(RAW / "gemeinden_2026.csv")
    gemeinden = pd.DataFrame()
    gemeinden["bfs_nr"] = roh["BfsCode"]
    gemeinden["name"] = roh["Name"]
    gemeinden["kanton_id"] = roh["CantonId"]
    kantone = []
    for kanton_id in roh["CantonId"]:
        kantone.append(KANTON_KUERZEL[kanton_id - 1])   # Listen beginnen bei 0
    gemeinden["kanton"] = kantone
    gruppen = []
    for typ in roh["GDETYP2020_9"]:
        gruppen.append(typ_gruppe(typ))
    gemeinden["typ_gruppe"] = gruppen
    return gemeinden.merge(mittelpunkte_laden(), on="bfs_nr")


def miettabelle_laden(dateiname, anzahl_regionen):
    """
    Mieten 2024 aus einer BFS-Excel-Tabelle: eine Zeile pro Region und Zimmerzahl.

    Die Zeile «Schweiz» bekommt die Nummer 0, die Regionen darunter 1, 2, 3 ...
    """
    roh = pd.read_excel(RAW / dateiname, sheet_name="2024", header=None)

    # Die Zeile suchen, in der in der ersten Spalte «Schweiz» steht
    start = 0
    for i in range(len(roh)):
        if str(roh.iloc[i, 0]).strip() == "Schweiz":
            start = i
            break

    zeilen = []
    for nr in range(anzahl_regionen + 1):   # Schweiz + alle Regionen
        region = roh.iloc[start + nr]
        for zimmer, spalte in MIET_SPALTEN.items():
            # Das BFS schreibt unsichere Werte in Klammern "(1234)" und unterdrückte als "X"
            text = str(region[spalte]).replace("(", "").replace(")", "").strip()
            if text == "X":
                miete = None
            else:
                miete = float(text)
            zeilen.append({"nr": nr, "zimmer": zimmer, "miete_chf": miete})
    return pd.DataFrame(zeilen)


def mieten_schaetzen(gemeinden, mieten_kanton, mieten_typ):
    """
    Geschätzte Monatsmiete pro Gemeinde und Zimmerzahl.

    Das BFS hat keine Mieten pro Gemeinde. Wir schätzen:
        Miete = Kantonsmiete × (Miete des Gemeindetyps / Miete Schweiz)
    Beispiel: Ländliche Gemeinden sind schweizweit ca. 14 % günstiger als der Durchschnitt,
    also nehmen wir für eine ländliche Gemeinde die Kantonsmiete minus 14 %.
    """
    # Nachschlage-Tabellen als Dictionaries: (nr, zimmer) -> Miete
    kanton = {}
    for nr, zimmer, miete in zip(mieten_kanton["nr"], mieten_kanton["zimmer"], mieten_kanton["miete_chf"]):
        kanton[(nr, zimmer)] = miete
    typ = {}
    for nr, zimmer, miete in zip(mieten_typ["nr"], mieten_typ["zimmer"], mieten_typ["miete_chf"]):
        typ[(nr, zimmer)] = miete

    zeilen = []
    for bfs_nr, kanton_id, gruppe in zip(gemeinden["bfs_nr"], gemeinden["kanton_id"], gemeinden["typ_gruppe"]):
        for zimmer in MIET_SPALTEN:
            miete_kanton = kanton[(kanton_id, zimmer)]
            miete_typ = typ[(gruppe, zimmer)]
            miete_schweiz = kanton[(0, zimmer)]   # Nummer 0 = Schweiz
            if pd.isna(miete_kanton):
                # Kantonswert vom BFS unterdrückt: dann gilt der Wert des Gemeindetyps
                miete = miete_typ
            else:
                miete = miete_kanton * miete_typ / miete_schweiz
            zeilen.append({"bfs_nr": bfs_nr, "zimmer": zimmer, "miete_chf": round(miete)})
    return pd.DataFrame(zeilen)


# --- Hauptprogramm ---
gemeinden = gemeinden_laden()
steuern = pd.read_csv(RAW / "steuern_2026.csv")[["bfs_nr", "haushalt", "einkommen", "steuer_chf"]]
mieten_kanton = miettabelle_laden("mieten_pro_kanton.xlsx", ANZAHL_KANTONE)
mieten_typ = miettabelle_laden("mieten_pro_gemeindetyp.xlsx", ANZAHL_TYPGRUPPEN)
mieten = mieten_schaetzen(gemeinden, mieten_kanton, mieten_typ)

# Alte Datenbank löschen und neu schreiben (df.to_sql schreibt eine Tabelle in die Datenbank)
if DB.exists():
    DB.unlink()
con = sqlite3.connect(DB)
gemeinden[["bfs_nr", "name", "kanton", "lat", "lon"]].to_sql("gemeinden", con, index=False)
steuern.to_sql("steuern", con, index=False)
mieten.to_sql("mieten", con, index=False)
con.close()

# Kurze Kontrolle
print("Gemeinden:", len(gemeinden), "| ohne Koordinaten:", gemeinden["lat"].isna().sum())
print("Steuerzeilen:", len(steuern))
print("Mietzeilen:", len(mieten), "| leer:", mieten["miete_chf"].isna().sum())
print("Fertig:", DB)
