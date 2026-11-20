"""Baut die SQLite-Datenbank data/wohnort.db aus den Rohdaten in data/raw."""
# Mit Claude erstellt, angepasst von Ivan
#
# Ausführen im Projektordner:  python scripts/build_db.py
# Die Datenbank wird bei jedem Lauf komplett neu gebaut.
# Vorher muss scripts/grenzen_aufbereiten.py gelaufen sein (für die Koordinaten).

import json
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
DB = ROOT / "data" / "wohnort.db"
GRENZEN = ROOT / "data" / "gemeindegrenzen_2026.geojson"

# Kantonskürzel in der offiziellen BFS-Reihenfolge (Position = CantonId)
KANTON_KUERZEL = [
    "ZH", "BE", "LU", "UR", "SZ", "OW", "NW", "GL", "ZG", "FR", "SO", "BS", "BL",
    "SH", "AR", "AI", "SG", "GR", "AG", "TG", "TI", "VD", "VS", "NE", "GE", "JU",
]

# In den BFS-Miettabellen steht neben jeder Miete ein Vertrauensintervall.
# Zimmerzahl -> Spaltennummer der Miete (6 = "6 und mehr")
MIET_SPALTEN = {1: 3, 2: 5, 3: 7, 4: 9, 5: 11, 6: 13}

# Die Miettabelle nach Gemeindetyp fasst die 9 Typen zu diesen 5 Gruppen zusammen
TYP_GRUPPEN = {
    1: "Städtisch, grosse Agglomeration",
    2: "Städtisch, mittelgrosse Agglomeration",
    3: "Städtisch, kleine oder ausserhalb Agglomeration",
    4: "Periurban",
    5: "Ländlich",
}


def typ_gruppe(typ):
    """Ordnet einen der 9 Gemeindetypen einer der 5 Gruppen der Miettabelle zu."""
    if pd.isna(typ):
        return None
    typ = int(typ)
    # Je nach Export sind die Typen als 11-33 oder als 1-9 codiert
    if typ > 9:
        erste_ziffer, zweite_ziffer = divmod(typ, 10)
    else:
        erste_ziffer, zweite_ziffer = (typ - 1) // 3 + 1, (typ - 1) % 3 + 1
    if erste_ziffer == 1:
        return zweite_ziffer  # die drei städtischen Typen bleiben einzeln
    return 4 if erste_ziffer == 2 else 5


def gemeinden_laden():
    """Gemeindeliste 2026, reduziert auf die Spalten, die die App braucht."""
    roh = pd.read_csv(RAW / "gemeinden_2026.csv")
    gemeinden = pd.DataFrame({
        "bfs_nr": roh["BfsCode"],
        "name": roh["Name"],
        "kanton_id": roh["CantonId"],
        "kanton": roh["CantonId"].apply(lambda nr: KANTON_KUERZEL[nr - 1]),
        "kanton_name": roh["Canton"],
        "bezirk": roh["District"],
        "gemeindetyp": roh["GDETYP2020_9"],
        "stadt_land": roh["STALAN2020"],
    })
    gemeinden["typ_gruppe"] = gemeinden["gemeindetyp"].apply(typ_gruppe)
    return gemeinden.merge(mittelpunkte_laden(), on="bfs_nr", how="left")


def mittelpunkt(ring):
    """Schwerpunkt und Fläche eines Polygons (Liste von [lon, lat]) nach der Gauss-Formel."""
    flaeche = sx = sy = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        kreuz = x1 * y2 - x2 * y1
        flaeche += kreuz
        sx += (x1 + x2) * kreuz
        sy += (y1 + y2) * kreuz
    flaeche /= 2
    return sx / (6 * flaeche), sy / (6 * flaeche), abs(flaeche)


def mittelpunkte_laden():
    """Koordinaten jeder Gemeinde: Schwerpunkt ihrer grössten Teilfläche."""
    with open(GRENZEN, encoding="utf-8") as datei:
        grenzen = json.load(datei)
    zeilen = []
    for gemeinde in grenzen["features"]:
        # polygon[0] ist der Aussenrand, die weiteren Ringe wären Löcher
        teile = [mittelpunkt(polygon[0]) for polygon in gemeinde["geometry"]["coordinates"]]
        lon, lat, _ = max(teile, key=lambda teil: teil[2])
        zeilen.append({"bfs_nr": gemeinde["properties"]["bfs_nr"],
                       "lat": round(lat, 4), "lon": round(lon, 4)})
    return pd.DataFrame(zeilen)


def steuern_laden():
    """Steuern pro Gemeinde, Haushaltstyp und Einkommen (aus scripts/steuern_laden.py)."""
    roh = pd.read_csv(RAW / "steuern_2026.csv")
    return roh[["bfs_nr", "haushalt", "einkommen", "steuer_chf"]]


def miettabelle_laden(datei, anzahl_regionen):
    """Mieten 2024 aus einer BFS-Tabelle, eine Zeile pro Region und Zimmerzahl."""
    roh = pd.read_excel(RAW / datei, sheet_name="2024", header=None)
    # Die Regionen stehen direkt unter der Zeile "Schweiz"
    start = roh.index[roh[0].astype(str).str.strip() == "Schweiz"][0] + 1
    regionen = roh.iloc[start:start + anzahl_regionen]

    zeilen = []
    for nr, (_, region) in enumerate(regionen.iterrows(), start=1):
        for zimmer, spalte in MIET_SPALTEN.items():
            # "(1234)" = unsichere Schätzung des BFS, "X" = unterdrückt (wird zu leer)
            wert = str(region[spalte]).strip("() ")
            zeilen.append({
                "nr": nr,
                "region": str(region[0]).strip(),
                "zimmer": zimmer,
                "miete_chf": pd.to_numeric(wert, errors="coerce"),
            })
    return pd.DataFrame(zeilen)


def leere_tabellen_anlegen(con):
    """Tabellen, die erst die App beim Benutzen füllt."""
    con.execute("""
        CREATE TABLE bewertungen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sitzung TEXT,
            bfs_nr INTEGER,
            gefaellt INTEGER,
            zeitpunkt TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
    con.execute("""
        CREATE TABLE pendel_cache (
            bfs_nr INTEGER,
            ziel TEXT,
            minuten REAL,
            abgefragt_am TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (bfs_nr, ziel)
        )""")


def main():
    """Liest alle Rohdaten ein und schreibt sie neu in die Datenbank."""
    gemeinden = gemeinden_laden()
    steuern = steuern_laden()

    # Die Kantone stehen in der Tabelle in der offiziellen BFS-Reihenfolge, nr = CantonId
    mieten_kanton = miettabelle_laden("mieten_pro_kanton.xlsx", 26)
    mieten_kanton = mieten_kanton.rename(columns={"nr": "kanton_id"})
    mieten_typ = miettabelle_laden("mieten_pro_gemeindetyp.xlsx", len(TYP_GRUPPEN))
    mieten_typ = mieten_typ.rename(columns={"nr": "typ_gruppe"})

    DB.unlink(missing_ok=True)  # immer frisch aufbauen
    with sqlite3.connect(DB) as con:
        gemeinden.to_sql("gemeinden", con, index=False)
        steuern.to_sql("steuern", con, index=False)
        mieten_kanton.to_sql("mieten_kanton", con, index=False)
        mieten_typ.to_sql("mieten_typ", con, index=False)
        leere_tabellen_anlegen(con)

    # Kurze Kontrolle, ob alles zusammenpasst
    ohne_steuern = set(gemeinden["bfs_nr"]) - set(steuern["bfs_nr"])
    print(f"Gemeinden: {len(gemeinden)}, davon ohne Gruppe: {gemeinden['typ_gruppe'].isna().sum()}, "
          f"ohne Koordinaten: {gemeinden['lat'].isna().sum()}")
    print(f"Steuerzeilen: {len(steuern)}, Gemeinden ohne Steuerdaten: {len(ohne_steuern)}")
    print(f"Mieten Kanton: {mieten_kanton['miete_chf'].notna().sum()} Werte, "
          f"Mieten Gemeindetyp: {mieten_typ['miete_chf'].notna().sum()} Werte")
    print(f"Gemeindetypen in der Liste: {sorted(int(t) for t in gemeinden['gemeindetyp'].dropna().unique())}")
    print(f"Fertig: {DB}")


if __name__ == "__main__":
    main()
