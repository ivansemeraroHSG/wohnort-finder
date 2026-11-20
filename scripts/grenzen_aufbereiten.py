"""Passt die BFS-Gemeindegrenzen (Stand 1.1.2025) an die Gemeindeliste 2026 an."""
# Ausführen im Projektordner:  python scripts/grenzen_aufbereiten.py
# Ergebnis: data/gemeindegrenzen_2026.geojson (wird von der Karte in der App gelesen)

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
QUELLE = ROOT / "data" / "raw" / "gemeindegrenzen" / "Communes_K4_20250101_4326.geojson"
GEMEINDEN = ROOT / "data" / "raw" / "gemeinden_2026.csv"
ZIEL = ROOT / "data" / "gemeindegrenzen_2026.geojson"

# Gemeinden, die zwischen dem 1.1.2025 und dem 1.1.2026 fusioniert haben
# oder eine neue BFS-Nummer bekamen: alte Nummer -> neue Nummer
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


def polygone(geometrie):
    """Gibt die Flächen einer Geometrie immer als Liste von Polygonen zurück."""
    if geometrie["type"] == "Polygon":
        return [geometrie["coordinates"]]
    return geometrie["coordinates"]


def main():
    """Fasst fusionierte Gemeinden zusammen und speichert sie mit BFS-Nummer 2026."""
    with open(QUELLE, encoding="utf-8") as datei:
        grenzen_2025 = json.load(datei)

    # Alle Flächen einer neuen Gemeinde sammeln (bei Fusionen mehrere alte Gemeinden)
    flaechen = {}
    for gemeinde in grenzen_2025["features"]:
        alte_nr = gemeinde["properties"]["GDENR"]
        neue_nr = FUSIONEN.get(alte_nr, alte_nr)
        flaechen.setdefault(neue_nr, []).extend(polygone(gemeinde["geometry"]))

    gemeinden = pd.read_csv(GEMEINDEN)
    namen = dict(zip(gemeinden["BfsCode"], gemeinden["Name"]))

    features = [
        {
            "type": "Feature",
            "id": bfs_nr,
            "properties": {"bfs_nr": bfs_nr, "name": namen.get(bfs_nr)},
            "geometry": {"type": "MultiPolygon", "coordinates": polygon_liste},
        }
        for bfs_nr, polygon_liste in flaechen.items()
    ]
    with open(ZIEL, "w", encoding="utf-8") as datei:
        json.dump({"type": "FeatureCollection", "features": features}, datei)

    # Kontrolle: Jede Gemeinde der Liste 2026 braucht genau eine Fläche
    ohne_flaeche = set(namen) - set(flaechen)
    ohne_gemeinde = set(flaechen) - set(namen)
    print(f"Flächen 2025: {len(grenzen_2025['features'])}, Gemeinden 2026: {len(features)}")
    print(f"Gemeinden ohne Fläche: {sorted(ohne_flaeche) or 'keine'}")
    print(f"Flächen ohne Gemeinde: {sorted(ohne_gemeinde) or 'keine'}")
    print(f"Fertig: {ZIEL}")


if __name__ == "__main__":
    main()