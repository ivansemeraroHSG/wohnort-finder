"""
api.py – Arbeitsort und Pendeln: Koordinaten, Pendelzeiten und Pendelkosten (Arbeitspaket 2).

Verantwortlich: Gregor Weber
Mit Claude erstellt, angepasst von Gregor Weber

Genutzte APIs (alle kostenlos):
- swisstopo SearchServer:  Adresse -> Koordinaten
- transport.opendata.ch:   ÖV-Verbindungen
- openrouteservice Matrix: Auto und Velo. Braucht einen Schlüssel, lokal in
  .streamlit/secrets.toml, online in den Einstellungen von Streamlit Cloud.
"""

from __future__ import annotations

import math
import time
from datetime import date, timedelta

import pandas as pd
import requests
import streamlit as st

from data import (ARBEITSWOCHEN, AUTO_CHF_PRO_KM_TOTAL, AUTO_CHF_PRO_KM_VARIABEL,
                  get_cache_connection, oev_abopreis)

SWISSTOPO_URL = "https://api3.geo.admin.ch/rest/services/api/SearchServer"
TRANSPORT_URL = "https://transport.opendata.ch/v1/connections"
ORS_URL = "https://api.openrouteservice.org/v2/matrix/"

# --- Abfragen ---
TIMEOUT_SEK = 10          # danach aufgeben, statt die App hängen zu lassen
ORS_TIMEOUT_SEK = 30      # eine Matrix für alle 2'110 Gemeinden braucht einige Sekunden
GEOCODE_CACHE_SEK = 600   # nach 10 Min. neu fragen, damit ein Fehler (None) nicht hängen bleibt
ABFAHRT = "07:30"         # typische Pendlerzeit, macht alle Gemeinden vergleichbar
MAX_LIVE_ABFRAGEN = 50    # Fair Use von transport.opendata.ch
PAUSE_SEK = 0.2           # zwischen zwei ÖV-Abfragen, ebenfalls Fair Use
MAX_FEHLER_IN_FOLGE = 3   # so oft hintereinander keine Antwort: API gestört, Rest bleibt geschätzt

# --- ÖV ---
# Schätzung aus der Luftlinie: Minuten = PENDEL_A + PENDEL_B × km.
# Absichtlich optimistisch (eine Untergrenze): Von 314 echten Zeiten (20.11.2026) lag fast
# keine (unter 1 %) unter der Schätzung, im Schnitt waren sie 36 Min. länger. So fällt keine gute Gemeinde
# beim Filter «max. Pendelzeit» weg, bevor app.py ihre echte Zeit abfragt (Task 2.8).
# Eine Durchschnittsformel (24.3 + 1.61 × km) hätte z. B. Zug auf 64 statt 31 Min. geschätzt.
# Herleitung: scripts/pendel_kalibrieren.py, Prüfung: scripts/schaetzung_pruefen.py
PENDEL_A = 7.5    # Minuten fix: zur Haltestelle gehen, warten
PENDEL_B = 0.76   # Minuten pro km Luftlinie
# API hat geantwortet, aber keine Verbindung gefunden. Wird auch gecacht,
# damit wir nicht jedes Mal erneut vergeblich fragen.
KEINE_VERBINDUNG = -1
# Zum Namen findet der Fahrplan manchmal einen anderen Ort ("Herdern" -> Zürich, Herdernstrasse).
# 15 km, weil auch in den grössten Gemeinden das Dorf höchstens so weit vom Mittelpunkt liegt.
MAX_ABSTAND_HALTESTELLE_KM = 15

# --- Auto und Velo ---
PROFIL_AUTO = "driving-car"
PROFIL_VELO = "cycling-regular"
VERKEHRSMITTEL = {PROFIL_AUTO: "auto", PROFIL_VELO: "velo"}   # Präfix der Spaltennamen
# Schätzung, falls openrouteservice nicht antwortet: Median aus 2'084 Auto- und
# 212 Velorouten nach Zürich HB (20.11.2026)
UMWEG = {PROFIL_AUTO: 1.35, PROFIL_VELO: 1.35}   # Strassen-km pro km Luftlinie
TEMPO_KMH = {PROFIL_AUTO: 76, PROFIL_VELO: 18}
VELO_MAX_MIN = 45   # länger fährt kaum jemand täglich Velo
VELO_MAX_KM = 25    # Luftlinie; weiter weg dauert es sowieso länger als VELO_MAX_MIN

# --- Kosten ---
MONATE = 12
FAHRTEN_PRO_TAG = 2   # hin und zurück

ERDRADIUS_KM = 6371


@st.cache_data(ttl=GEOCODE_CACHE_SEK)   # app.py läuft bei jedem Klick neu
def geocode(adresse: str) -> tuple[float, float, str] | None:
    """Adresse -> (lat, lon, gefundener Name) über swisstopo, None wenn nichts gefunden."""
    params = {"searchText": adresse, "type": "locations"}
    try:
        r = requests.get(SWISSTOPO_URL, params=params, timeout=TIMEOUT_SEK)
    except requests.exceptions.RequestException:   # z. B. kein Internet
        return None
    if r.status_code != 200 or len(r.json()["results"]) == 0:
        return None

    attrs = r.json()["results"][0]["attrs"]   # swisstopo liefert den besten Treffer zuerst
    name = attrs["label"]
    for tag in ["<b>", "</b>", "<i>", "</i>"]:   # HTML-Formatierung, für uns unnötig
        name = name.replace(tag, "")
    # Manche Treffer beginnen mit dem Namen der Datenquelle, z. B. "haltestellen_ Zürich HB"
    if "_ " in name:
        name = name.split("_ ", 1)[1]
    return (attrs["lat"], attrs["lon"], name.strip())


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Luftlinie in km (Haversine-Formel, https://de.wikipedia.org/wiki/Haversine-Formel)."""
    # Auf der Erdkugel reicht Pythagoras nicht; math rechnet in Radiant statt Grad
    lat1 = math.radians(lat1)
    lon1 = math.radians(lon1)
    lat2 = math.radians(lat2)
    lon2 = math.radians(lon2)
    d_lat = lat2 - lat1
    d_lon = lon2 - lon1
    a = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    return 2 * ERDRADIUS_KM * math.asin(math.sqrt(a))


def dauer_in_minuten(dauer: str) -> int:
    """Fahrzeit von transport.opendata.ch in Minuten, z. B. "00d01:12:00" -> 72."""
    tage = int(dauer[0:2])
    stunden = int(dauer[3:5])
    minuten = int(dauer[6:8])
    return tage * 24 * 60 + stunden * 60 + minuten


def schaetze_minuten(km: float) -> float:
    """Geschätzte ÖV-Pendelzeit in Minuten aus der Luftlinie (Untergrenze, siehe oben)."""
    return PENDEL_A + PENDEL_B * km


def naechster_montag() -> str:
    """Datum des nächsten Montags, z. B. "2026-11-23"."""
    heute = date.today()
    tage_bis_montag = 7 - heute.weekday()   # weekday(): Montag = 0, Sonntag = 6
    return (heute + timedelta(days=tage_bis_montag)).isoformat()


def oev_ortsname(name: str) -> str:
    """BFS-Name in Fahrplan-Schreibweise, z. B. "Kilchberg (ZH)" -> "Kilchberg ZH"."""
    return name.replace(" (", " ").replace(")", "")


def live_minuten(start: str, ziel: str,
                 pruef_lat: float | None = None, pruef_lon: float | None = None) -> int | None:
    """
    ÖV-Fahrzeit in Minuten, Abfahrt nächster Montag um ABFAHRT.

    start, ziel: Ortsname oder "lat,lon". pruef_lat/pruef_lon: Gemeinde-Mittelpunkt;
    liegt die gefundene Start-Haltestelle zu weit davon weg, gilt sie als falscher Ort.
    Rückgabe: Minuten, KEINE_VERBINDUNG (dauerhaft) oder None (API gerade nicht erreichbar).
    """
    params = {"from": start, "to": ziel, "date": naechster_montag(), "time": ABFAHRT, "limit": 1}
    try:
        r = requests.get(TRANSPORT_URL, params=params, timeout=TIMEOUT_SEK)
    except requests.exceptions.RequestException:
        return None
    # 429 = zu viele Anfragen, 500er = Störung beim Server: später nochmals versuchen
    if r.status_code == 429 or r.status_code >= 500:
        return None
    if r.status_code != 200 or len(r.json()["connections"]) == 0:
        return KEINE_VERBINDUNG

    verbindung = r.json()["connections"][0]
    if pruef_lat is not None:
        haltestelle = verbindung["from"]["station"]["coordinate"]   # x = lat, y = lon
        if haltestelle["x"] is not None:
            abstand = haversine_km(pruef_lat, pruef_lon, haltestelle["x"], haltestelle["y"])
            if abstand > MAX_ABSTAND_HALTESTELLE_KM:
                return KEINE_VERBINDUNG
    return dauer_in_minuten(verbindung["duration"])


def commute_minutes(ziel_lat: float, ziel_lon: float,
                    gemeinden: pd.DataFrame, max_abfragen: int = MAX_LIVE_ABFRAGEN,
                    fortschritt=None, zusaetzlich: list[int] | None = None) -> pd.DataFrame:
    """
    ÖV-Pendelzeit von jeder Gemeinde zum Arbeitsort.

    Die nächsten Gemeinden und die aus «zusaetzlich» werden live abgefragt, alle
    anderen aus der Luftlinie geschätzt. Antworten landen im Cache (pendel_cache).

    Parameter:
        gemeinden:   DataFrame mit bfs_nr, name, lat, lon
        fortschritt: optional ein Fortschrittsbalken aus app.py (st.progress)
        zusaetzlich: optional bfs_nr, die ausser den nächsten live abgefragt werden (Task 2.8)

    Rückgabe: DataFrame mit bfs_nr, pendel_min, pendel_geschaetzt
    """
    # Schritt 1: Luftlinie und Schätzung für alle Gemeinden (ohne Internet, sehr schnell)
    km_liste = []
    for index, zeile in gemeinden.iterrows():
        km_liste.append(haversine_km(ziel_lat, ziel_lon, zeile["lat"], zeile["lon"]))
    resultat = pd.DataFrame()
    resultat["bfs_nr"] = gemeinden["bfs_nr"]
    resultat["km"] = km_liste
    resultat["pendel_min"] = schaetze_minuten(resultat["km"]).round(0)
    resultat["pendel_geschaetzt"] = True

    # Schritt 2: Welche Gemeinden live abfragen?
    ziel = f"{ziel_lat:.4f},{ziel_lon:.4f}"
    abfragen = resultat.sort_values("km").head(max_abfragen)
    if zusaetzlich is not None:
        extra = resultat[resultat["bfs_nr"].isin(zusaetzlich)]
        abfragen = pd.concat([abfragen, extra]).drop_duplicates("bfs_nr")

    # Schritt 3: Alles schon Bekannte auf einmal aus dem Cache laden, auch aus früheren
    # Aufrufen (z. B. Runden in app.py). Live gefragt wird nur, was dort fehlt.
    con = get_cache_connection()
    cache = pd.read_sql("SELECT bfs_nr, minuten FROM pendel_cache WHERE ziel = ?",
                        con, params=(ziel,))
    bekannt = dict(zip(cache["bfs_nr"], cache["minuten"]))   # bfs_nr -> minuten

    fehler_in_folge = 0
    erledigt = 0
    for index, zeile in abfragen.iterrows():
        if fehler_in_folge >= MAX_FEHLER_IN_FOLGE:   # Notbremse, API wohl gestört
            break
        bfs_nr = int(zeile["bfs_nr"])
        if bfs_nr not in bekannt:
            gemeinde = gemeinden.loc[index]
            # Mit dem Namen findet der Fahrplan die Haltestelle im Dorf. Der Flächen-
            # mittelpunkt liegt bei grossen Gemeinden oft am Berg, weit weg davon.
            minuten = live_minuten(oev_ortsname(gemeinde["name"]), ziel,
                                   gemeinde["lat"], gemeinde["lon"])
            if minuten == KEINE_VERBINDUNG:   # Notlösung: ab dem Mittelpunkt
                minuten = live_minuten(f"{gemeinde['lat']:.4f},{gemeinde['lon']:.4f}", ziel)

            if minuten is None:
                fehler_in_folge += 1
            else:
                fehler_in_folge = 0
                bekannt[bfs_nr] = minuten
                with con:
                    con.execute(
                        "INSERT OR REPLACE INTO pendel_cache (bfs_nr, ziel, minuten) VALUES (?, ?, ?)",
                        (bfs_nr, ziel, minuten),
                    )
            time.sleep(PAUSE_SEK)

        erledigt += 1
        if fortschritt is not None:
            fortschritt.progress(erledigt / len(abfragen))
    con.close()

    # Schritt 4: Schätzungen durch alle bekannten echten Zeiten ersetzen
    for index, zeile in resultat.iterrows():
        minuten = bekannt.get(int(zeile["bfs_nr"]))
        if minuten is not None and minuten != KEINE_VERBINDUNG:
            resultat.loc[index, "pendel_min"] = minuten
            resultat.loc[index, "pendel_geschaetzt"] = False

    return resultat[["bfs_nr", "pendel_min", "pendel_geschaetzt"]]


def ors_schluessel() -> str | None:
    """API-Schlüssel für openrouteservice aus den Streamlit-Secrets, sonst None."""
    try:
        return st.secrets["ORS_KEY"]
    except (KeyError, FileNotFoundError):   # secrets.toml oder Eintrag fehlt
        return None


def ors_abfrage(ziel_lat: float, ziel_lon: float,
                kandidaten: pd.DataFrame, profil: str) -> pd.DataFrame | None:
    """Eine Matrix-Anfrage an openrouteservice: bfs_nr, minuten, km oder None bei Fehler."""
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
                          headers={"Authorization": schluessel}, timeout=ORS_TIMEOUT_SEK)
    except requests.exceptions.RequestException:
        return None
    if r.status_code != 200:
        return None

    daten = r.json()   # pro Gemeinde eine Liste mit genau einem Wert (ein Ziel)
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

    Rückgabe: DataFrame mit bfs_nr, <vm>_km, <vm>_min, <vm>_geschaetzt (<vm> = auto oder velo)
    """
    vm = VERKEHRSMITTEL[profil]
    ziel = f"{ziel_lat:.4f},{ziel_lon:.4f}"

    # Schritt 1: Schätzung aus der Luftlinie für alle Gemeinden
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

    # Schritt 2: echte Werte aus dem Cache, sonst einmal bei openrouteservice holen
    con = get_cache_connection()
    echte = pd.read_sql("SELECT bfs_nr, minuten, km FROM route_cache WHERE ziel = ? AND profil = ?",
                        con, params=(ziel, profil))
    if len(echte) == 0:
        if profil == PROFIL_VELO:
            kandidaten = kandidaten[kandidaten["luftlinie"] <= VELO_MAX_KM]
        echte = ors_abfrage(ziel_lat, ziel_lon, kandidaten, profil)
        if echte is not None:
            speichern = echte.copy()   # copy: ziel und profil braucht nur der Cache
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


def bestes_verkehrsmittel(optionen: dict, max_min: float, zeitwert: float | None) -> str | None:
    """
    Bestes Verkehrsmittel aus {"oev": (minuten, chf), ...}.

    Ohne Zeitwert das günstigste, sonst das mit den tiefsten Kosten + Zeitwert × Minuten;
    nur bis max_min. Ist keins schnell genug, das schnellste.
    """
    bestes = None
    beste_punkte = None
    for vm in optionen:
        minuten, chf = optionen[vm]
        if minuten > max_min:
            continue
        if zeitwert is None:
            punkte = chf
        else:
            punkte = chf + zeitwert * minuten
        if beste_punkte is None or punkte < beste_punkte:
            bestes = vm
            beste_punkte = punkte

    # Keins schnell genug: app.py filtert die Gemeinde über die max. Pendelzeit ohnehin weg
    if bestes is None:
        for vm in optionen:
            if bestes is None or optionen[vm][0] < optionen[bestes][0]:
                bestes = vm
    return bestes


def pendel_optionen(gemeinden: pd.DataFrame, pendel: pd.DataFrame,
                    routen: pd.DataFrame, eingaben: dict) -> pd.DataFrame:
    """
    Zeit und Kosten pro Jahr für ÖV, Auto und Velo sowie das beste Verkehrsmittel.

    Parameter:
        pendel:   Ergebnis von commute_minutes() (ÖV)
        routen:   route_matrix() für Auto und Velo, verknüpft über bfs_nr
        eingaben: {"verkehrsmittel": ["oev", "auto", "velo"], "buerotage": 5,
                   "hat_auto": False, "parkplatz_chf": 0, "hat_ga": False,
                   "max_pendel_min": 45, "zeitwert": None}
                  zeitwert = CHF pro Jahr für 1 Minute pro Weg (von AP 3), None = noch keiner

    Rückgabe: DataFrame mit bfs_nr, oev_geschaetzt, oev/auto/velo_min und _chf,
              bestes_vm, pendel_min, pendel_chf (nicht gewählte Verkehrsmittel leer)
    """
    df = gemeinden[["bfs_nr"]].merge(pendel, on="bfs_nr").merge(routen, on="bfs_nr")
    df = df.rename(columns={"pendel_min": "oev_min", "pendel_geschaetzt": "oev_geschaetzt"})

    gewaehlt = eingaben["verkehrsmittel"]
    if eingaben["hat_auto"]:
        auto_chf_pro_km = AUTO_CHF_PRO_KM_VARIABEL
    else:
        auto_chf_pro_km = AUTO_CHF_PRO_KM_TOTAL
    fahrten_pro_jahr = FAHRTEN_PRO_TAG * eingaben["buerotage"] * ARBEITSWOCHEN

    zeilen = []
    for index, g in df.iterrows():
        zeile = {"bfs_nr": g["bfs_nr"], "oev_geschaetzt": g["oev_geschaetzt"]}
        optionen = {}
        if "oev" in gewaehlt:
            # Tarif-km des Abos: Strassen-km als Näherung, die Bahn ist ähnlich lang
            if eingaben["hat_ga"]:
                oev_chf = 0
            else:
                oev_chf = oev_abopreis(g["auto_km"])
            optionen["oev"] = (g["oev_min"], oev_chf)
        if "auto" in gewaehlt:
            auto_chf = g["auto_km"] * fahrten_pro_jahr * auto_chf_pro_km + MONATE * eingaben["parkplatz_chf"]
            optionen["auto"] = (g["auto_min"], round(auto_chf))
        if "velo" in gewaehlt and g["velo_min"] <= VELO_MAX_MIN:
            optionen["velo"] = (g["velo_min"], 0)

        for vm in ["oev", "auto", "velo"]:
            if vm in optionen:
                zeile[f"{vm}_min"] = optionen[vm][0]
                zeile[f"{vm}_chf"] = optionen[vm][1]
            else:
                zeile[f"{vm}_min"] = None
                zeile[f"{vm}_chf"] = None

        bestes = bestes_verkehrsmittel(optionen, eingaben["max_pendel_min"], eingaben["zeitwert"])
        zeile["bestes_vm"] = bestes
        if bestes is None:   # gar kein Verkehrsmittel gewählt
            zeile["pendel_min"] = None
            zeile["pendel_chf"] = None
        else:
            zeile["pendel_min"] = optionen[bestes][0]
            zeile["pendel_chf"] = optionen[bestes][1]
        zeilen.append(zeile)
    return pd.DataFrame(zeilen)


# --- Test: läuft nur bei "python api.py", nicht wenn app.py die Datei importiert ---
if __name__ == "__main__":
    from data import fake_municipalities, get_municipalities

    for adresse in ["Bahnhofstrasse 1, Zürich", "Zürich HB", "Wetzikon", "asdfghjkl"]:
        print(adresse, "->", geocode(adresse))   # Unsinn soll None geben, nicht abstürzen
    print("Zürich-Bern km (ca. 95):", round(haversine_km(47.378, 8.540, 46.949, 7.439), 1))

    # ÖV mit Fake-Gemeinden: 2. Aufruf soll dank Cache sofort fertig sein
    for aufruf in [1, 2]:
        startzeit = time.time()
        df = commute_minutes(47.378, 8.540, fake_municipalities())
        print(f"ÖV {aufruf}. Aufruf: {time.time() - startzeit:.1f} Sek.,",
              (df["pendel_geschaetzt"] == False).sum(), "echte Zeiten")
    # Die Fake-Gemeinden haben BFS-Nummern 1–30, die es auch echt gibt: Testeinträge löschen
    con = get_cache_connection()
    with con:
        con.execute("DELETE FROM pendel_cache WHERE ziel = ?", ("47.3780,8.5400",))
    con.close()

    # Auto und Velo mit echten Gemeinden, Arbeitsort Zürich HB
    alle = get_municipalities()
    print("openrouteservice-Schlüssel gefunden:", ors_schluessel() is not None)
    for profil in [PROFIL_AUTO, PROFIL_VELO]:
        vm = VERKEHRSMITTEL[profil]
        startzeit = time.time()
        routen = route_matrix(47.378, 8.540, alle, profil)
        print(f"{vm}: {time.time() - startzeit:.1f} Sek.,",
              (routen[f"{vm}_geschaetzt"] == False).sum(), "echte Werte")

    # Pendelkosten (Task 2.7): drei von Hand nachgerechnete Fälle Rapperswil-Jona -> Zürich HB
    pendel = commute_minutes(47.378, 8.540, alle)
    routen = route_matrix(47.378, 8.540, alle, PROFIL_AUTO).merge(
        route_matrix(47.378, 8.540, alle, PROFIL_VELO), on="bfs_nr")
    rj = alle[alle["name"] == "Rapperswil-Jona"]["bfs_nr"].iloc[0]
    eingaben = {"verkehrsmittel": ["oev", "auto", "velo"], "buerotage": 5, "hat_auto": False,
                "parkplatz_chf": 0, "hat_ga": False, "max_pendel_min": 60, "zeitwert": None}
    erwartet = [({}, 14603), ({"hat_auto": True}, 5526), ({"hat_auto": True, "parkplatz_chf": 200}, 7926)]
    for aenderung, auto_chf in erwartet:
        e = eingaben.copy()   # copy: die Grundeingaben sollen für den nächsten Fall gleich bleiben
        e.update(aenderung)
        zeile = pendel_optionen(alle, pendel, routen, e).set_index("bfs_nr").loc[rj]
        print(f"Rapperswil-Jona {aenderung}: Auto {zeile['auto_chf']} CHF (erwartet {auto_chf}),",
              f"ÖV {zeile['oev_chf']} CHF (erwartet 2349)")
