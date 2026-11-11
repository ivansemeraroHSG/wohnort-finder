"""
api.py – Arbeitsort finden und Pendelzeiten abfragen (Arbeitspaket 2).

Verantwortlich: <Name eintragen>

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
    # TODO (AP 2): requests.get(SWISSTOPO_URL, params={"searchText": adresse, "type": "locations"})
    raise NotImplementedError


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
