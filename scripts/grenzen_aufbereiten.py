"""
grenzen_aufbereiten.py – passt die BFS-Gemeindegrenzen (Stand 1.1.2025) an die Gemeinden 2026 an.

Verantwortlich: Ivan (Arbeitspaket 1)
KI-Hinweis: Mit Claude (Anthropic) erstellt; am 24.11.2026 mit Claude vereinfacht
(Branch WF-5.6-Umbau).

Warum braucht es das? Die Grenzen-Datei des BFS ist von 2025, unsere Gemeindeliste von 2026.
Dazwischen haben einige Gemeinden fusioniert. Dieses Skript gibt den Flächen der alten
Gemeinden die neue BFS-Nummer. build_db.py berechnet daraus die Koordinaten jeder Gemeinde.

Ausführen im Projektordner:  python scripts/grenzen_aufbereiten.py
Ergebnis: data/gemeindegrenzen_2026.geojson

GeoJSON ist ein Textformat für Karten. Python liest es mit json.load() als Dictionary ein,
genau wie die Antworten der APIs in Übung 6 und 7.
"""

import json
from pathlib import Path

import pandas as pd

ORDNER = Path(__file__).parent.parent
QUELLE = ORDNER / "data" / "raw" / "gemeindegrenzen" / "Communes_K4_20250101_4326.geojson"
GEMEINDEN = ORDNER / "data" / "raw" / "gemeinden_2026.csv"
ZIEL = ORDNER / "data" / "gemeindegrenzen_2026.geojson"

# Gemeinden, die zwischen dem 1.1.2025 und dem 1.1.2026 fusioniert haben oder
# eine neue BFS-Nummer bekamen: alte Nummer -> neue Nummer
# Quelle: Amtliches Gemeindeverzeichnis BFS, Mutationen 2025
FUSIONEN = {
    700: 6831,    # Moutier wechselt von BE zu JU
    2016: 2056,   # Fétigny -> Fétigny-Ménières
    2027: 2056,   # Ménières -> Fétigny-Ménières
    2278: 2262,   # Ulmiz -> Gurmels
    2520: 2525,   # Halten -> Kriegstetten
    2529: 2525,   # Oekingen -> Kriegstetten
    4122: 4095,   # Villnachern -> Brugg
    5064: 5073,   # Bodio -> Giornico
    5078: 5079,   # Prato (Leventina) -> Quinto
    5146: 5395,   # Astano -> Lema
    5149: 5395,   # Bedigliora -> Lema
    5181: 5395,   # Curio -> Lema
    5200: 5395,   # Miglieglia -> Lema
    5207: 5395,   # Novaggio -> Lema
}

# Grenzen 2025 einlesen
with open(QUELLE, encoding="utf-8") as datei:
    grenzen_2025 = json.load(datei)

# Alle Flächen pro Gemeinde 2026 sammeln (Dictionary: neue BFS-Nummer -> Liste von Flächen).
# Bei einer Fusion landen die Flächen mehrerer alter Gemeinden bei derselben neuen Nummer.
flaechen = {}
for gemeinde in grenzen_2025["features"]:
    alte_nr = gemeinde["properties"]["GDENR"]
    if alte_nr in FUSIONEN:
        neue_nr = FUSIONEN[alte_nr]
    else:
        neue_nr = alte_nr
    if neue_nr not in flaechen:
        flaechen[neue_nr] = []

    # Eine Gemeinde ist ein «Polygon» (eine Fläche) oder ein «MultiPolygon» (mehrere Flächen).
    # Wir speichern immer eine Liste von Flächen.
    geometrie = gemeinde["geometry"]
    if geometrie["type"] == "Polygon":
        flaechen[neue_nr].append(geometrie["coordinates"])
    else:
        for polygon in geometrie["coordinates"]:
            flaechen[neue_nr].append(polygon)

# Namen der Gemeinden 2026 (Dictionary: BFS-Nummer -> Name)
gemeinden = pd.read_csv(GEMEINDEN)
namen = {}
for nr, name in zip(gemeinden["BfsCode"], gemeinden["Name"]):
    namen[nr] = name

# Neue GeoJSON-Datei zusammenbauen: eine Fläche pro Gemeinde 2026
features = []
for bfs_nr in flaechen:
    features.append({
        "type": "Feature",
        "properties": {"bfs_nr": bfs_nr, "name": namen.get(bfs_nr)},
        "geometry": {"type": "MultiPolygon", "coordinates": flaechen[bfs_nr]},
    })
with open(ZIEL, "w", encoding="utf-8") as datei:
    json.dump({"type": "FeatureCollection", "features": features}, datei)

# Kontrolle: Jede Gemeinde der Liste 2026 braucht genau eine Fläche
ohne_flaeche = []
for nr in namen:
    if nr not in flaechen:
        ohne_flaeche.append(nr)
print("Flächen 2025:", len(grenzen_2025["features"]), "| Gemeinden 2026:", len(features))
print("Gemeinden ohne Fläche:", ohne_flaeche)
print("Fertig:", ZIEL)
