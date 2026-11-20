"""
api.py – Arbeitsort finden und Pendelzeiten abfragen (Arbeitspaket 2).

Verantwortlich: Gregor Weber

Genutzte APIs (beide ohne Schlüssel, kostenlos):
- swisstopo SearchServer: https://api3.geo.admin.ch/rest/services/api/SearchServer
- transport.opendata.ch:  https://transport.opendata.ch/v1/connections
"""

from __future__ import annotations

import pandas as pd
import requests

SWISSTOPO_URL = "https://api3.geo.admin.ch/rest/services/api/SearchServer"
TRANSPORT_URL = "https://transport.opendata.ch/v1/connections"


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
    # Der Name enthält HTML-Fettschrift (<b>...</b>), die wir nicht brauchen
    name = attrs["label"].replace("<b>", "").replace("</b>", "")
    return (attrs["lat"], attrs["lon"], name)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Berechnet die Luftlinie zwischen zwei Punkten in Kilometern."""
    # TODO (AP 2): Haversine-Formel
    raise NotImplementedError


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
    # TODO (AP 2): Vorfilter, Live-Abfragen, Schätzung, Cache
    raise NotImplementedError


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
