"""
api.py – Arbeitsort finden und Pendelzeiten abfragen (Arbeitspaket 2).

Verantwortlich: Gregor Weber

Genutzte APIs (alle kostenlos):
- swisstopo SearchServer: https://api3.geo.admin.ch/rest/services/api/SearchServer
- transport.opendata.ch:  https://transport.opendata.ch/v1/connections
- openrouteservice Matrix: https://api.openrouteservice.org/v2/matrix
  (braucht einen Schlüssel: lokal in .streamlit/secrets.toml, online in Streamlit Cloud)
"""

from __future__ import annotations

import math
import time
from datetime import date, timedelta

import pandas as pd
import requests
import streamlit as st

from data import get_cache_connection

SWISSTOPO_URL = "https://api3.geo.admin.ch/rest/services/api/SearchServer"
TRANSPORT_URL = "https://transport.opendata.ch/v1/connections"

# Schätzformel für die Pendelzeit: Minuten = PENDEL_A + PENDEL_B * km (Luftlinie).
# Die Werte stammen aus echten Verbindungen, siehe scripts/pendel_kalibrieren.py.
# PENDEL_A: fixe Zeit (zum Bahnhof gehen, warten, umsteigen)
# PENDEL_B: zusätzliche Minuten pro Kilometer Luftlinie
# Ergebnis vom 20.11.2026 (19 Verbindungen, Mo 07:30): mittlere Abweichung ca. 7 Minuten
PENDEL_A = 7.5
PENDEL_B = 0.76

# Rückgabewert von live_minuten(), wenn die API geantwortet, aber keine
# Verbindung gefunden hat (z. B. Ort ohne ÖV). Wird im Cache gespeichert,
# damit wir nicht jedes Mal erneut vergeblich fragen.
KEINE_VERBINDUNG = -1

# openrouteservice: Auto und Velo (Task 2.6)
ORS_URL = "https://api.openrouteservice.org/v2/matrix/"
PROFIL_AUTO = "driving-car"
PROFIL_VELO = "cycling-regular"
VERKEHRSMITTEL = {PROFIL_AUTO: "auto", PROFIL_VELO: "velo"}   # Präfix der Spaltennamen
ORS_TIMEOUT = 30   # eine Matrix für alle 2'110 Gemeinden braucht einige Sekunden
VELO_MAX_KM = 25   # Velo wird nur bis 45 Min. angeboten, weiter weg nicht abfragen

# Schätzung, wenn openrouteservice nicht antwortet: Luftlinie -> Strasse.
# Median aus echten Antworten vom 20.11.2026 (Arbeitsort Zürich HB,
# 2'084 Auto- und 212 Velorouten), siehe Test unten.
UMWEG = {PROFIL_AUTO: 1.35, PROFIL_VELO: 1.35}  # Strassen-km pro km Luftlinie
TEMPO_KMH = {PROFIL_AUTO: 76, PROFIL_VELO: 18}  # Durchschnitt auf der Strasse


# Streamlit führt app.py bei jedem Klick neu aus. Ohne Cache würde dieselbe
# Adresse jedes Mal neu bei swisstopo gesucht. ttl=600: nach 10 Minuten neu fragen,
# damit ein Ergebnis aus einer kurzen Störung (None) nicht ewig hängen bleibt.
@st.cache_data(ttl=600)
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


def naechster_montag() -> str:
    """
    Gibt das Datum des nächsten Montags als Text zurück, z. B. "2026-11-23".

    Wir fragen immer Montag 07:30 ab, damit alle Pendelzeiten vergleichbar sind
    (Wochenende oder Nacht hätten einen ganz anderen Fahrplan).
    """
    heute = date.today()
    tage_bis_montag = 7 - heute.weekday()   # weekday(): Montag = 0, Sonntag = 6
    montag = heute + timedelta(days=tage_bis_montag)
    return montag.isoformat()


def live_minuten(start: str, ziel: str) -> int | None:
    """
    Fragt bei transport.opendata.ch die Fahrzeit für eine Verbindung ab.

    Parameter:
        start, ziel: Koordinaten als Text "lat,lon". Mit Koordinaten statt Namen
                     gibt es keine Verwechslungen (z. B. Rapperswil SG und BE).

    Rückgabe: Fahrzeit in Minuten,
              KEINE_VERBINDUNG, wenn es keine Verbindung gibt (dauerhaft),
              None, wenn die API gerade nicht erreichbar ist (vorübergehend)
    """
    params = {}
    params["from"] = start
    params["to"] = ziel
    params["date"] = naechster_montag()
    params["time"] = "07:30"
    params["limit"] = 1

    try:
        r = requests.get(TRANSPORT_URL, params=params, timeout=10)
    except requests.exceptions.RequestException:
        return None

    # 429 = zu viele Anfragen, 500er = Störung beim Server: später nochmals versuchen
    if r.status_code == 429 or r.status_code >= 500:
        return None
    if r.status_code != 200:
        return KEINE_VERBINDUNG
    verbindungen = r.json()["connections"]
    if len(verbindungen) == 0:
        return KEINE_VERBINDUNG
    return dauer_in_minuten(verbindungen[0]["duration"])


def commute_minutes(ziel_lat: float, ziel_lon: float,
                    gemeinden: pd.DataFrame, max_abfragen: int = 50,
                    fortschritt=None) -> pd.DataFrame:
    """
    Liefert die Pendelzeit mit dem ÖV von jeder Gemeinde zum Arbeitsort.

    Vorgehen: Nur die nächsten bzw. besten Gemeinden (max_abfragen) werden live
    abgefragt; für alle anderen wird die Zeit aus der Luftlinie geschätzt.
    Resultate werden in der Tabelle "pendel_cache" zwischengespeichert.

    Parameter:
        ziel_lat, ziel_lon: Koordinaten des Arbeitsorts
        gemeinden:          DataFrame mit bfs_nr, name, lat, lon
        max_abfragen:       maximale Anzahl Live-Abfragen
        fortschritt:        optional ein Fortschrittsbalken aus app.py (st.progress),
                            der während der Live-Abfragen nachgeführt wird

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

    # Schritt 3: Die nächsten Gemeinden sind für die Nutzerin am wichtigsten,
    # darum ersetzen wir bei ihnen die Schätzung durch die echte Fahrzeit.
    ziel = f"{ziel_lat:.4f},{ziel_lon:.4f}"
    naechste = resultat.sort_values("km").head(max_abfragen)

    # Der Cache liegt in data/cache.db und wird bei Bedarf angelegt (siehe data.py)
    con = get_cache_connection()
    fehler_in_folge = 0
    erledigt = 0
    for index, zeile in naechste.iterrows():
        # Notbremse: Antwortet die API dreimal hintereinander nicht, ist sie wohl
        # gestört. Dann nicht weiter warten, die restlichen Gemeinden bleiben geschätzt.
        if fehler_in_folge >= 3:
            break

        bfs_nr = int(zeile["bfs_nr"])

        # 3a: Zuerst im Cache nachsehen, ob wir diese Verbindung schon kennen
        gespeichert = con.execute(
            "SELECT minuten FROM pendel_cache WHERE bfs_nr = ? AND ziel = ?",
            (bfs_nr, ziel),
        ).fetchone()

        if gespeichert is not None:
            minuten = gespeichert[0]
        else:
            # 3b: Noch nicht im Cache: live abfragen und für das nächste Mal speichern
            gemeinde = gemeinden.loc[index]
            start = f"{gemeinde['lat']:.4f},{gemeinde['lon']:.4f}"
            minuten = live_minuten(start, ziel)
            if minuten is None:
                fehler_in_folge += 1
            else:
                fehler_in_folge = 0
            # Auch "keine Verbindung" speichern, nur vorübergehende Fehler (None) nicht
            if minuten is not None:
                with con:
                    con.execute(
                        "INSERT OR REPLACE INTO pendel_cache (bfs_nr, ziel, minuten) VALUES (?, ?, ?)",
                        (bfs_nr, ziel, minuten),
                    )
            time.sleep(0.2)   # kurze Pause, damit wir die API nicht überlasten (Fair Use)

        # Ohne echte Fahrzeit bleibt einfach die Schätzung stehen
        if minuten is not None and minuten != KEINE_VERBINDUNG:
            resultat.loc[index, "pendel_min"] = minuten
            resultat.loc[index, "pendel_geschaetzt"] = False

        erledigt += 1
        if fortschritt is not None:
            fortschritt.progress(erledigt / len(naechste))
    con.close()

    return resultat[["bfs_nr", "pendel_min", "pendel_geschaetzt"]]


def ors_schluessel() -> str | None:
    """API-Schlüssel für openrouteservice aus den Streamlit-Secrets, sonst None."""
    try:
        return st.secrets["ORS_KEY"]
    except (KeyError, FileNotFoundError):   # secrets.toml oder Eintrag fehlt
        return None


# Mit Claude erstellt, angepasst von Gregor Weber
def ors_abfrage(ziel_lat: float, ziel_lon: float,
                kandidaten: pd.DataFrame, profil: str) -> pd.DataFrame | None:
    """
    Eine Matrix-Anfrage an openrouteservice: alle Kandidaten -> Arbeitsort.

    Rückgabe: DataFrame mit bfs_nr, minuten, km oder None bei einem Fehler
    """
    schluessel = ors_schluessel()
    if schluessel is None:
        return None

    # openrouteservice will [lon, lat], also umgekehrt als swisstopo.
    # Ort 0 ist der Arbeitsort, danach kommen die Gemeinden.
    orte = [[ziel_lon, ziel_lat]]
    for index, zeile in kandidaten.iterrows():
        orte.append([zeile["lon"], zeile["lat"]])

    anfrage = {
        "locations": orte,
        "sources": list(range(1, len(orte))),   # alle Gemeinden
        "destinations": [0],                     # nur der Arbeitsort
        "metrics": ["duration", "distance"],
        "units": "km",
    }
    try:
        r = requests.post(ORS_URL + profil, json=anfrage,
                          headers={"Authorization": schluessel}, timeout=ORS_TIMEOUT)
    except requests.exceptions.RequestException:
        return None
    if r.status_code != 200:
        return None

    # Pro Gemeinde eine Liste mit genau einem Wert, weil es nur ein Ziel gibt
    daten = r.json()
    zeilen = []
    for bfs_nr, dauer, distanz in zip(kandidaten["bfs_nr"], daten["durations"], daten["distances"]):
        if dauer[0] is None:   # keine Route gefunden, z. B. autofreie Gemeinde
            continue
        zeilen.append({"bfs_nr": int(bfs_nr), "minuten": dauer[0] / 60, "km": distanz[0]})
    if len(zeilen) == 0:
        return None
    return pd.DataFrame(zeilen)


def route_matrix(ziel_lat: float, ziel_lon: float,
                 gemeinden: pd.DataFrame, profil: str) -> pd.DataFrame:
    """
    Fahrzeit und Strassen-km mit Auto oder Velo von jeder Gemeinde zum Arbeitsort.

    Parameter:
        gemeinden: DataFrame mit bfs_nr, lat, lon
        profil:    PROFIL_AUTO oder PROFIL_VELO

    Rückgabe: DataFrame mit bfs_nr, <vm>_min, <vm>_km, <vm>_geschaetzt
              (<vm> = auto oder velo)
    """
    vm = VERKEHRSMITTEL[profil]
    ziel = f"{ziel_lat:.4f},{ziel_lon:.4f}"

    # Schritt 1: für alle Gemeinden eine Schätzung aus der Luftlinie
    kandidaten = gemeinden[["bfs_nr", "lat", "lon"]].copy()   # copy: wir fügen eine Spalte an
    km_liste = []
    for index, zeile in kandidaten.iterrows():
        km_liste.append(haversine_km(ziel_lat, ziel_lon, zeile["lat"], zeile["lon"]))
    kandidaten["luftlinie"] = km_liste

    resultat = pd.DataFrame()
    resultat["bfs_nr"] = kandidaten["bfs_nr"]
    resultat[f"{vm}_km"] = (kandidaten["luftlinie"] * UMWEG[profil]).round(1)
    resultat[f"{vm}_min"] = (resultat[f"{vm}_km"] / TEMPO_KMH[profil] * 60).round(0)
    resultat[f"{vm}_geschaetzt"] = True
    resultat = resultat.set_index("bfs_nr")

    # Schritt 2: echte Werte zuerst im Cache suchen, sonst bei openrouteservice holen
    con = get_cache_connection()
    echte = pd.read_sql("SELECT bfs_nr, minuten, km FROM route_cache WHERE ziel = ? AND profil = ?",
                        con, params=(ziel, profil))
    if len(echte) == 0:
        if profil == PROFIL_VELO:
            kandidaten = kandidaten[kandidaten["luftlinie"] <= VELO_MAX_KM]
        echte = ors_abfrage(ziel_lat, ziel_lon, kandidaten, profil)
        if echte is not None:
            speichern = echte.copy()   # copy: ziel und profil nur für den Cache
            speichern["ziel"] = ziel
            speichern["profil"] = profil
            with con:
                speichern.to_sql("route_cache", con, if_exists="append", index=False)
    con.close()

    # Schritt 3: Schätzungen durch die echten Werte ersetzen
    if echte is not None:
        for index, zeile in echte.iterrows():
            bfs_nr = int(zeile["bfs_nr"])
            resultat.loc[bfs_nr, f"{vm}_min"] = round(zeile["minuten"])
            resultat.loc[bfs_nr, f"{vm}_km"] = round(zeile["km"], 1)
            resultat.loc[bfs_nr, f"{vm}_geschaetzt"] = False

    return resultat.reset_index()


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

    # Pendelzeiten mit den Fake-Gemeinden, Arbeitsort Zürich HB.
    # Zweimal aufrufen: Der zweite Aufruf soll dank Cache sofort fertig sein.
    from data import fake_municipalities
    gemeinden = fake_municipalities()

    startzeit = time.time()
    df = commute_minutes(47.378, 8.540, gemeinden)
    print(f"1. Aufruf: {time.time() - startzeit:.1f} Sekunden")

    startzeit = time.time()
    df = commute_minutes(47.378, 8.540, gemeinden)
    print(f"2. Aufruf: {time.time() - startzeit:.1f} Sekunden")

    print(df.sort_values("pendel_min").head(10))
    print("Davon mit echter Fahrzeit:", (df["pendel_geschaetzt"] == False).sum())

    # Was steht im Cache? Zeigt, wie viele Orte keine Verbindung hatten (-1)
    con = get_cache_connection()
    cache = pd.read_sql("SELECT minuten FROM pendel_cache WHERE ziel = '47.3780,8.5400'", con)
    con.close()
    print("Im Cache gespeichert:", len(cache), "davon ohne Verbindung:", (cache["minuten"] == KEINE_VERBINDUNG).sum())

    # Testeinträge wieder löschen: Die Fake-Gemeinden haben BFS-Nummern 1–30,
    # die es auch echt gibt. Sonst stünden falsche Zeiten im Cache.
    con = get_cache_connection()
    with con:
        con.execute("DELETE FROM pendel_cache WHERE ziel = ?", ("47.3780,8.5400",))
    con.close()

    # --- Auto und Velo mit openrouteservice, echte Gemeinden, Arbeitsort Zürich HB ---
    from data import get_municipalities
    alle = get_municipalities()
    print()
    print("openrouteservice-Schlüssel gefunden:", ors_schluessel() is not None)
    for profil in [PROFIL_AUTO, PROFIL_VELO]:
        vm = VERKEHRSMITTEL[profil]
        startzeit = time.time()
        routen = route_matrix(47.378, 8.540, alle, profil)
        print(f"{vm} 1. Aufruf: {time.time() - startzeit:.1f} Sekunden")
        startzeit = time.time()
        routen = route_matrix(47.378, 8.540, alle, profil)
        print(f"{vm} 2. Aufruf: {time.time() - startzeit:.1f} Sekunden")
        echt = routen[routen[f"{vm}_geschaetzt"] == False]
        print(f"{vm}: {len(echt)} echte Werte, {len(routen) - len(echt)} geschätzt")

        # Werte für die Schätzung bestimmen: Umweg und Tempo im Durchschnitt
        echt = echt.merge(alle[["bfs_nr", "name", "lat", "lon"]], on="bfs_nr")
        luftlinie = [haversine_km(47.378, 8.540, lat, lon) for lat, lon in zip(echt["lat"], echt["lon"])]
        umweg = (echt[f"{vm}_km"] / pd.Series(luftlinie)).median()
        tempo = (echt[f"{vm}_km"] / echt[f"{vm}_min"] * 60).median()
        print(f"{vm}: Umweg {umweg:.2f}, Tempo {tempo:.0f} km/h -> in UMWEG und TEMPO_KMH eintragen")
        print(echt.sort_values(f"{vm}_min")[["name", f"{vm}_min", f"{vm}_km"]].head(5))
