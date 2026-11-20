"""
api.py – Arbeitsort finden und Pendelzeiten abfragen (Arbeitspaket 2).

Verantwortlich: Gregor Weber

Genutzte APIs (beide ohne Schlüssel, kostenlos):
- swisstopo SearchServer: https://api3.geo.admin.ch/rest/services/api/SearchServer
- transport.opendata.ch:  https://transport.opendata.ch/v1/connections
"""

from __future__ import annotations

import math

import pandas as pd
import requests

SWISSTOPO_URL = "https://api3.geo.admin.ch/rest/services/api/SearchServer"
TRANSPORT_URL = "https://transport.opendata.ch/v1/connections"

# Schätzformel für die Pendelzeit: Minuten = PENDEL_A + PENDEL_B * km (Luftlinie).
# Die Werte stammen aus echten Verbindungen, siehe scripts/pendel_kalibrieren.py.
# PENDEL_A: fixe Zeit (zum Bahnhof gehen, warten, umsteigen)
# PENDEL_B: zusätzliche Minuten pro Kilometer Luftlinie
# Ergebnis vom 20.11.2026 (19 Verbindungen, Mo 07:30): mittlere Abweichung ca. 7 Minuten
PENDEL_A = 7.5
PENDEL_B = 0.76


def geocode(adresse: str) -> tuple[float, float, str] | None:
    """
    Sucht eine Adresse über swisstopo und gibt ihre Koordinaten zurück.

    Parameter:
        adresse: z. B. "Bahnhofstrasse 1, Zürich"

    Rückgabe: (lat, lon, gefundener Name) oder None, wenn nichts gefunden wurde
    """
    params = {}
    params["searchText"] = adresse
    params["type"] = "locations"

    # Ohne Internet würde requests.get() abstürzen statt einen Statuscode zu liefern,
    # darum hier abfangen. timeout: nach 10 Sek. aufgeben statt ewig warten.
    try:
        r = requests.get(SWISSTOPO_URL, params=params, timeout=10)
    except requests.exceptions.RequestException:
        return None

    if r.status_code != 200:
        return None

    treffer = r.json()["results"]
    if len(treffer) == 0:   # nichts gefunden, z. B. Tippfehler
        return None

    # Wir nehmen den ersten Treffer, weil swisstopo den besten zuerst liefert
    attrs = treffer[0]["attrs"]
    # Der Name enthält HTML-Formatierung (<b>, <i>), die wir nicht brauchen
    name = attrs["label"]
    for tag in ["<b>", "</b>", "<i>", "</i>"]:
        name = name.replace(tag, "")
    return (attrs["lat"], attrs["lon"], name)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Berechnet die Luftlinie zwischen zwei Punkten in Kilometern.

    Die Erde ist eine Kugel, darum reicht Pythagoras nicht ganz. Die
    Haversine-Formel berechnet die Distanz auf der Kugeloberfläche.
    Quelle der Formel: https://de.wikipedia.org/wiki/Haversine-Formel
    """
    erdradius_km = 6371

    # Die Winkelfunktionen in Python rechnen mit Radiant, nicht mit Grad
    lat1 = math.radians(lat1)
    lon1 = math.radians(lon1)
    lat2 = math.radians(lat2)
    lon2 = math.radians(lon2)

    d_lat = lat2 - lat1
    d_lon = lon2 - lon1
    a = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    return 2 * erdradius_km * math.asin(math.sqrt(a))


def dauer_in_minuten(dauer: str) -> int:
    """
    Wandelt die Fahrzeit von transport.opendata.ch in Minuten um.

    Beispiel: "00d01:12:00" (0 Tage, 1 Stunde, 12 Minuten) -> 72
    """
    tage = int(dauer[0:2])
    stunden = int(dauer[3:5])
    minuten = int(dauer[6:8])
    return tage * 24 * 60 + stunden * 60 + minuten


def schaetze_minuten(km: float) -> float:
    """Schätzt die ÖV-Pendelzeit in Minuten aus der Luftlinie in km."""
    return PENDEL_A + PENDEL_B * km


def commute_minutes(ziel_lat: float, ziel_lon: float,
                    gemeinden: pd.DataFrame, max_abfragen: int = 50) -> pd.DataFrame:
    """
    Liefert die Pendelzeit mit dem ÖV von jeder Gemeinde zum Arbeitsort.

    Vorgehen: Nur die nächsten bzw. besten Gemeinden (max_abfragen) werden live
    abgefragt; für alle anderen wird die Zeit aus der Luftlinie geschätzt.
    Resultate werden in der Tabelle "pendel_cache" zwischengespeichert.

    Parameter:
        ziel_lat, ziel_lon: Koordinaten des Arbeitsorts
        gemeinden:          DataFrame mit bfs_nr, name, lat, lon
        max_abfragen:       maximale Anzahl Live-Abfragen

    Rückgabe: DataFrame mit bfs_nr, pendel_min, pendel_geschaetzt
    """
    # Schritt 1: Luftlinie vom Arbeitsort zu jeder Gemeinde.
    # Geht für alle Gemeinden in Sekundenbruchteilen, weil kein Internet nötig ist.
    km_liste = []
    for index, zeile in gemeinden.iterrows():
        km = haversine_km(ziel_lat, ziel_lon, zeile["lat"], zeile["lon"])
        km_liste.append(km)

    resultat = pd.DataFrame()
    resultat["bfs_nr"] = gemeinden["bfs_nr"]
    resultat["km"] = km_liste

    # Schritt 2: Für alle Gemeinden zuerst die Schätzung eintragen
    resultat["pendel_min"] = schaetze_minuten(resultat["km"]).round(0)
    resultat["pendel_geschaetzt"] = True

    # Schritt 3 (Task 2.4): die max_abfragen nächsten Gemeinden live abfragen
    # und ihre Schätzung durch die echte Zeit ersetzen.

    return resultat[["bfs_nr", "pendel_min", "pendel_geschaetzt"]]


# --- Test: läuft nur bei "python api.py", nicht wenn app.py die Datei importiert ---
if __name__ == "__main__":
    test_adressen = [
        "Bahnhofstrasse 1, Zürich",
        "Dufourstrasse 50, St. Gallen",
        "Bundesplatz 3, Bern",
        "Wetzikon",
        "asdfghjkl",            # Unsinn: soll None geben, nicht abstürzen
    ]
    for adresse in test_adressen:
        print(adresse, "->", geocode(adresse))

    # Luftlinie Zürich HB – Bern Bahnhof, sollte ca. 95 km sein
    print("Zürich-Bern km:", round(haversine_km(47.378, 8.540, 46.949, 7.439), 1))

    # Pendelzeit-Schätzung mit den Fake-Gemeinden, Arbeitsort Zürich HB
    from data import fake_municipalities
    print(commute_minutes(47.378, 8.540, fake_municipalities()).head(10))
