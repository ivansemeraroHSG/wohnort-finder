"""
api.py – Arbeitsort und Pendeln: Koordinaten, Pendelzeiten und Pendelkosten (Arbeitspaket 2).

Verantwortlich: Gregor Weber
KI-Hinweis: Mit Claude (Anthropic) erstellt; am 24.11.2026 mit Claude vereinfacht
(Branch WF-5.6-Umbau). openrouteservice-Abfrage: umgesetzt im Team, mit Claude kommentiert.
Am 25.11.2026 mit Claude ergänzt (Branch WF-5.7): alle Verkehrsmittel vergleichen,
Abo-Wahl, Weg zur Haltestelle, echte ÖV-Zeiten für die Gemeinden, die man in der App sieht.

Genutzte APIs (alle kostenlos):
- swisstopo SearchServer:  Adresse -> Koordinaten (GET, wie in Übung 6/7)
- transport.opendata.ch:   ÖV-Verbindungen (GET, wie in Übung 7)
- openrouteservice:        Fahrzeit mit Auto und Velo (POST, braucht einen Schlüssel).
  Der Schlüssel steht lokal in .streamlit/secrets.toml, online in den Einstellungen
  von Streamlit Cloud (st.secrets, wie in der Streamlit-Demo von Übung 7).
"""

import math
import time
from datetime import date, timedelta

import pandas as pd
import requests
import streamlit as st

from data import auto_kosten, get_cache_connection, oev_kosten

SWISSTOPO_URL = "https://api3.geo.admin.ch/rest/services/api/SearchServer"
TRANSPORT_URL = "https://transport.opendata.ch/v1/connections"
ORS_URL = "https://api.openrouteservice.org/v2/matrix/"

# --- Einstellungen für die Abfragen ---
TIMEOUT_SEK = 10        # so lange auf eine Antwort warten, dann aufgeben
ORS_TIMEOUT_SEK = 30    # openrouteservice rechnet alle Gemeinden auf einmal, das dauert länger
ABFAHRT = "07:30"       # gleiche Abfahrtszeit für alle Gemeinden, damit man sie vergleichen kann
ANZAHL_LIVE = 50        # so viele nahe Gemeinden fragen wir live ab (Fair Use der API)
PAUSE_SEK = 0.2         # kurze Pause zwischen zwei Abfragen (Fair Use)
MAX_FEHLER = 3          # so viele Fehler hintereinander: API gestört, wir hören auf
KEINE_VERBINDUNG = -1   # API hat geantwortet, aber keine passende Verbindung gefunden
ZUGANG_MIN = 5          # Fussweg von zu Hause zur Haltestelle; der Fahrplan rechnet ab Haltestelle

# Bahn-Betriebspunkte (z. B. Weichen) sind keine Haltestellen. swisstopo schreibt
# das ins Feld «detail»; solche Treffer überspringen wir.
KEINE_HALTESTELLE = ["spurwechsel", "betriebspunkt", "anschlusspunkt", "abzweigung", "dienststation"]

# Findet der Fahrplan zum Gemeindenamen einen Ort, der weiter als 15 km vom
# Gemeinde-Mittelpunkt entfernt ist, war es der falsche Ort (z. B. eine gleichnamige Strasse).
MAX_ABSTAND_KM = 15

# --- Schätzung, wenn wir keine echte Zeit haben ---
# ÖV-Minuten = PENDEL_A + PENDEL_B × km Luftlinie.
# Die Werte hat das Team am 20.11.2026 aus echten ÖV-Verbindungen bestimmt (früheres
# Skript scripts/pendel_kalibrieren.py). Die Formel gibt eher zu kurze Zeiten; darum
# fragen wir die nahen Gemeinden live ab.
PENDEL_A = 7.5     # Minuten fix: zur Haltestelle gehen, warten
PENDEL_B = 0.76    # Minuten pro km Luftlinie
# Strassen sind länger als die Luftlinie: Strassen-km = Luftlinie × 1.35
UMWEG = 1.35
# Durchschnittstempo für die Schätzung (km/h)
TEMPO_KMH = {"auto": 76, "velo": 18}

# --- openrouteservice ---
ORS_PROFIL = {"auto": "driving-car", "velo": "cycling-regular"}
VELO_MAX_KM = 25   # Velo nur für Gemeinden bis 25 km Luftlinie abfragen (weiter fährt kaum jemand)

ERDRADIUS_KM = 6371


def geocode(adresse):
    """
    Sucht eine Adresse bei swisstopo.

    Rückgabe: (lat, lon, gefundener Name) oder None, wenn nichts gefunden wurde.
    """
    params = {}
    params["searchText"] = adresse
    params["type"] = "locations"
    try:
        r = requests.get(SWISSTOPO_URL, params=params, timeout=TIMEOUT_SEK)
    except requests.exceptions.RequestException:   # z. B. kein Internet
        return None
    if r.status_code != 200:
        return None
    treffer = r.json()["results"]
    if len(treffer) == 0:
        return None

    # swisstopo liefert den besten Treffer zuerst. Betriebspunkte überspringen wir.
    attrs = treffer[0]["attrs"]
    for resultat in treffer:
        detail = resultat["attrs"].get("detail", "")
        ist_haltestelle = True
        for wort in KEINE_HALTESTELLE:
            if wort in detail:
                ist_haltestelle = False
        if ist_haltestelle:
            attrs = resultat["attrs"]
            break

    # Der Name enthält HTML wie <b>Zürich</b> <i>train</i>: <i>…</i> ganz weg, <b> und </b> weg
    name = attrs["label"]
    while "<i>" in name and "</i>" in name:
        start = name.index("<i>")
        ende = name.index("</i>") + len("</i>")
        name = name[:start] + name[ende:]
    name = name.replace("<b>", "").replace("</b>", "")
    return (attrs["lat"], attrs["lon"], name.strip())


def haversine_km(lat1, lon1, lat2, lon2):
    """Luftlinie in km zwischen zwei Punkten (Haversine-Formel, de.wikipedia.org/wiki/Haversine-Formel)."""
    # Die Erde ist eine Kugel, darum reicht Pythagoras nicht.
    # math.sin und math.cos rechnen in Radiant, nicht in Grad.
    lat1 = math.radians(lat1)
    lon1 = math.radians(lon1)
    lat2 = math.radians(lat2)
    lon2 = math.radians(lon2)
    d_lat = lat2 - lat1
    d_lon = lon2 - lon1
    a = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    return 2 * ERDRADIUS_KM * math.asin(math.sqrt(a))


def dauer_in_minuten(dauer):
    """Fahrzeit von transport.opendata.ch in Minuten, z. B. "00d01:12:00" -> 72."""
    tage = int(dauer[0:2])
    stunden = int(dauer[3:5])
    minuten = int(dauer[6:8])
    return tage * 24 * 60 + stunden * 60 + minuten


def naechster_montag():
    """Datum des nächsten Montags als Text, z. B. "2026-11-30"."""
    heute = date.today()
    tage_bis_montag = 7 - heute.weekday()   # weekday(): Montag = 0, Sonntag = 6
    return (heute + timedelta(days=tage_bis_montag)).isoformat()


def oev_ortsname(name):
    """Gemeindename in Fahrplan-Schreibweise, z. B. "Kilchberg (ZH)" -> "Kilchberg ZH"."""
    return name.replace(" (", " ").replace(")", "")


def live_oev_minuten(gemeinde_name, gemeinde_lat, gemeinde_lon, ziel):
    """
    Echte ÖV-Fahrzeit von einer Gemeinde zum Arbeitsort (nächster Montag, 07:30).

    Parameter:
        gemeinde_name: Name der Gemeinde, z. B. "Uster"
        gemeinde_lat, gemeinde_lon: Mittelpunkt der Gemeinde (zur Kontrolle)
        ziel: Arbeitsort als Text "lat,lon"

    Rückgabe: Minuten der schnellsten Verbindung, KEINE_VERBINDUNG oder None (API nicht erreichbar)
    """
    params = {}
    params["from"] = oev_ortsname(gemeinde_name)
    params["to"] = ziel
    params["date"] = naechster_montag()
    params["time"] = ABFAHRT
    params["limit"] = 4   # vier Verbindungen, davon nehmen wir die schnellste
    try:
        r = requests.get(TRANSPORT_URL, params=params, timeout=TIMEOUT_SEK)
    except requests.exceptions.RequestException:
        return None
    # 429 = zu viele Anfragen, ab 500 = Störung beim Server
    if r.status_code == 429 or r.status_code >= 500:
        return None
    if r.status_code != 200:
        return KEINE_VERBINDUNG
    verbindungen = r.json()["connections"]
    if len(verbindungen) == 0:
        return KEINE_VERBINDUNG

    # Kontrolle: Liegt die Start-Haltestelle wirklich in der Nähe der Gemeinde?
    haltestelle = verbindungen[0]["from"]["station"]["coordinate"]   # x = lat, y = lon
    if haltestelle["x"] is not None:
        abstand = haversine_km(gemeinde_lat, gemeinde_lon, haltestelle["x"], haltestelle["y"])
        if abstand > MAX_ABSTAND_KM:
            return KEINE_VERBINDUNG

    # Die schnellste der Verbindungen suchen
    schnellste = None
    for verbindung in verbindungen:
        minuten = dauer_in_minuten(verbindung["duration"])
        if schnellste is None or minuten < schnellste:
            schnellste = minuten
    return schnellste


def oev_zeiten(ziel_lat, ziel_lon, gemeinden, extra_nrs=None, fortschritt=None):
    """
    ÖV-Pendelzeit von jeder Gemeinde zum Arbeitsort.

    Live abgefragt werden die ANZAHL_LIVE nächsten Gemeinden und alle Gemeinden in
    extra_nrs (die, die man in der App sieht). Alle anderen schätzen wir aus der Luftlinie.
    Echte Zeiten kommen in den Cache, damit wir nicht zweimal fragen.

    Parameter:
        gemeinden:   DataFrame mit bfs_nr, name, lat, lon
        extra_nrs:   Liste mit BFS-Nummern, die zusätzlich live abgefragt werden
        fortschritt: optional ein Fortschrittsbalken (st.progress) aus app.py

    Rückgabe: DataFrame mit bfs_nr, km, pendel_min, geschaetzt
    """
    # Schritt 1: Luftlinie und Schätzung für alle Gemeinden (ohne Internet, sehr schnell)
    luftlinie = []
    for lat, lon in zip(gemeinden["lat"], gemeinden["lon"]):
        luftlinie.append(haversine_km(ziel_lat, ziel_lon, lat, lon))
    resultat = pd.DataFrame()
    resultat["bfs_nr"] = gemeinden["bfs_nr"]
    resultat["name"] = gemeinden["name"]
    resultat["lat"] = gemeinden["lat"]
    resultat["lon"] = gemeinden["lon"]
    resultat["luftlinie"] = luftlinie
    resultat["km"] = (resultat["luftlinie"] * UMWEG).round(1)   # Strecken-km fürs Abo (Näherung)
    resultat["pendel_min"] = (PENDEL_A + PENDEL_B * resultat["luftlinie"]).round()
    resultat["geschaetzt"] = True

    # Schritt 2: Bekannte Zeiten aus dem Cache lesen (als Dictionary bfs_nr -> minuten)
    ziel = f"{ziel_lat:.4f},{ziel_lon:.4f}"
    con = get_cache_connection()
    cache = pd.read_sql("SELECT bfs_nr, minuten FROM oev_zeiten WHERE ziel = ?", con, params=(ziel,))
    bekannt = {}
    for bfs_nr, minuten in zip(cache["bfs_nr"], cache["minuten"]):
        bekannt[bfs_nr] = minuten

    # Schritt 3: Die nächsten Gemeinden und die extra_nrs live abfragen, wenn sie noch nicht im Cache sind
    naechste = resultat.sort_values("luftlinie").head(ANZAHL_LIVE)
    if extra_nrs is not None:
        extra = resultat[resultat["bfs_nr"].isin(extra_nrs)]
        naechste = pd.concat([naechste, extra]).drop_duplicates("bfs_nr")
    fehler_hintereinander = 0
    erledigt = 0
    for bfs_nr, name, lat, lon in zip(naechste["bfs_nr"], naechste["name"], naechste["lat"], naechste["lon"]):
        if fehler_hintereinander >= MAX_FEHLER:   # API gestört: Rest bleibt geschätzt
            break
        if bfs_nr not in bekannt:
            minuten = live_oev_minuten(name, lat, lon, ziel)
            if minuten is None:
                fehler_hintereinander = fehler_hintereinander + 1
            else:
                fehler_hintereinander = 0
                bekannt[bfs_nr] = minuten
                with con:
                    con.execute("INSERT INTO oev_zeiten (bfs_nr, ziel, minuten) VALUES (?, ?, ?)",
                                (int(bfs_nr), ziel, minuten))
            time.sleep(PAUSE_SEK)
        erledigt = erledigt + 1
        if fortschritt is not None:
            fortschritt.progress(erledigt / len(naechste))
    con.close()

    # Schritt 4: Schätzungen durch echte Zeiten ersetzen
    for index in resultat.index:
        bfs_nr = resultat.loc[index, "bfs_nr"]
        if bfs_nr in bekannt and bekannt[bfs_nr] != KEINE_VERBINDUNG:
            resultat.loc[index, "pendel_min"] = bekannt[bfs_nr] + ZUGANG_MIN
            resultat.loc[index, "geschaetzt"] = False

    return resultat[["bfs_nr", "km", "pendel_min", "geschaetzt"]]


def ors_schluessel():
    """Schlüssel für openrouteservice aus den Streamlit-Secrets, sonst None."""
    try:
        return st.secrets["ORS_KEY"]
    except (KeyError, FileNotFoundError):   # secrets.toml oder der Eintrag fehlt
        return None


def ors_abfrage(ziel_lat, ziel_lon, kandidaten, verkehrsmittel):
    """
    Eine Anfrage an openrouteservice: Fahrzeit und Strassen-km von allen Kandidaten zum Arbeitsort.

    Rückgabe: DataFrame mit bfs_nr, minuten, km oder None bei einem Fehler
    """
    schluessel = ors_schluessel()
    if schluessel is None:
        return None

    # Liste aller Orte. openrouteservice will [lon, lat], also umgekehrt als swisstopo.
    # Ort Nummer 0 ist der Arbeitsort, danach kommen die Gemeinden (Nummer 1, 2, 3 ...).
    orte = [[ziel_lon, ziel_lat]]
    for lat, lon in zip(kandidaten["lat"], kandidaten["lon"]):
        orte.append([lon, lat])

    # Was wir wissen wollen, als Dictionary (wird als JSON geschickt)
    anfrage = {}
    anfrage["locations"] = orte
    anfrage["sources"] = list(range(1, len(orte)))   # Start: alle Gemeinden
    anfrage["destinations"] = [0]                    # Ziel: nur der Arbeitsort
    anfrage["metrics"] = ["duration", "distance"]    # Zeit und Distanz
    anfrage["units"] = "km"

    # POST statt GET, weil die Liste der Orte zu lang für die Adresszeile ist.
    # Der Schlüssel kommt in den Header (wie beim Yelp-Beispiel in Übung 7).
    headers = {"Authorization": schluessel}
    try:
        r = requests.post(ORS_URL + ORS_PROFIL[verkehrsmittel], json=anfrage,
                          headers=headers, timeout=ORS_TIMEOUT_SEK)
    except requests.exceptions.RequestException:
        return None
    if r.status_code != 200:
        return None

    # Antwort: pro Gemeinde eine Liste mit genau einem Wert (wir haben nur ein Ziel)
    daten = r.json()
    zeilen = []
    for bfs_nr, dauer, distanz in zip(kandidaten["bfs_nr"], daten["durations"], daten["distances"]):
        if dauer[0] is not None:   # None = keine Route gefunden, z. B. autofreie Gemeinde
            zeilen.append({"bfs_nr": int(bfs_nr), "minuten": dauer[0] / 60, "km": distanz[0]})
    if len(zeilen) == 0:
        return None
    return pd.DataFrame(zeilen)


def route_zeiten(ziel_lat, ziel_lon, gemeinden, verkehrsmittel):
    """
    Fahrzeit und Strassen-km mit Auto oder Velo von jeder Gemeinde zum Arbeitsort.

    Parameter:
        gemeinden:      DataFrame mit bfs_nr, lat, lon
        verkehrsmittel: "auto" oder "velo"

    Rückgabe: DataFrame mit bfs_nr, km, pendel_min, geschaetzt
    """
    # Schritt 1: Schätzung aus der Luftlinie für alle Gemeinden
    luftlinie = []
    for lat, lon in zip(gemeinden["lat"], gemeinden["lon"]):
        luftlinie.append(haversine_km(ziel_lat, ziel_lon, lat, lon))
    resultat = pd.DataFrame()
    resultat["bfs_nr"] = gemeinden["bfs_nr"]
    resultat["lat"] = gemeinden["lat"]
    resultat["lon"] = gemeinden["lon"]
    resultat["luftlinie"] = luftlinie
    resultat["km"] = (resultat["luftlinie"] * UMWEG).round(1)
    resultat["pendel_min"] = (resultat["km"] / TEMPO_KMH[verkehrsmittel] * 60).round()
    resultat["geschaetzt"] = True

    # Schritt 2: Echte Werte aus dem Cache. Fehlen sie, einmal bei openrouteservice holen.
    ziel = f"{ziel_lat:.4f},{ziel_lon:.4f}"
    con = get_cache_connection()
    echte = pd.read_sql("SELECT bfs_nr, minuten, km FROM route_cache WHERE ziel = ? AND profil = ?",
                        con, params=(ziel, verkehrsmittel))
    if len(echte) == 0:
        kandidaten = resultat
        if verkehrsmittel == "velo":
            kandidaten = resultat[resultat["luftlinie"] <= VELO_MAX_KM]
        echte = ors_abfrage(ziel_lat, ziel_lon, kandidaten, verkehrsmittel)
        if echte is not None:
            for bfs_nr, minuten, km in zip(echte["bfs_nr"], echte["minuten"], echte["km"]):
                with con:
                    con.execute("INSERT INTO route_cache (bfs_nr, ziel, profil, minuten, km) "
                                "VALUES (?, ?, ?, ?, ?)", (bfs_nr, ziel, verkehrsmittel, minuten, km))
    con.close()

    # Schritt 3: Schätzungen durch die echten Werte ersetzen
    if echte is not None:
        resultat = resultat.set_index("bfs_nr")
        for bfs_nr, minuten, km in zip(echte["bfs_nr"], echte["minuten"], echte["km"]):
            resultat.loc[bfs_nr, "pendel_min"] = round(minuten)
            resultat.loc[bfs_nr, "km"] = round(km, 1)
            resultat.loc[bfs_nr, "geschaetzt"] = False
        resultat = resultat.reset_index()

    return resultat[["bfs_nr", "km", "pendel_min", "geschaetzt"]]


def pendeln_berechnen(ziel_lat, ziel_lon, gemeinden, eingaben, extra_nrs=None, fortschritt=None):
    """
    Pendelzeit und Pendelkosten pro Jahr für alle Gemeinden und alle gewählten Verkehrsmittel.
    Pro Gemeinde wählen wir das beste Verkehrsmittel (siehe bestes_verkehrsmittel).

    Parameter:
        eingaben:  Dictionary aus app.py mit verkehrsmittel (Liste), buerotage, hat_auto,
                   oev_abo und max_pendel
        extra_nrs: BFS-Nummern, für die wir die ÖV-Zeit sicher live abfragen

    Rückgabe: DataFrame mit bfs_nr, pro Verkehrsmittel <vm>_min, <vm>_chf, <vm>_geschaetzt
              und für das beste: verkehrsmittel, pendel_min, pendel_chf, geschaetzt
    """
    pendel = pd.DataFrame()
    pendel["bfs_nr"] = gemeinden["bfs_nr"]

    for vm in eingaben["verkehrsmittel"]:
        if vm == "oev":
            zeiten = oev_zeiten(ziel_lat, ziel_lon, gemeinden, extra_nrs, fortschritt)
        else:
            zeiten = route_zeiten(ziel_lat, ziel_lon, gemeinden, vm)

        # Kosten pro Jahr für jede Gemeinde
        kosten = []
        for km in zeiten["km"]:
            if vm == "oev":
                kosten.append(oev_kosten(km, eingaben["oev_abo"]))
            elif vm == "auto":
                kosten.append(auto_kosten(km, eingaben["buerotage"], eingaben["hat_auto"]))
            else:
                kosten.append(0)   # Velo fahren kostet (fast) nichts

        # Spalten umbenennen, z. B. pendel_min -> oev_min, und an die Tabelle anhängen
        spalten = pd.DataFrame()
        spalten["bfs_nr"] = zeiten["bfs_nr"]
        spalten[vm + "_min"] = zeiten["pendel_min"]
        spalten[vm + "_chf"] = kosten
        spalten[vm + "_geschaetzt"] = zeiten["geschaetzt"]
        pendel = pendel.merge(spalten, on="bfs_nr")

    # Pro Gemeinde das beste Verkehrsmittel und seine Werte
    beste = []
    for index in pendel.index:
        beste.append(bestes_verkehrsmittel(pendel.loc[index], eingaben["verkehrsmittel"], eingaben["max_pendel"]))
    pendel["verkehrsmittel"] = beste
    minuten = []
    kosten = []
    geschaetzt = []
    for index, vm in zip(pendel.index, beste):
        minuten.append(pendel.loc[index, vm + "_min"])
        kosten.append(pendel.loc[index, vm + "_chf"])
        geschaetzt.append(pendel.loc[index, vm + "_geschaetzt"])
    pendel["pendel_min"] = minuten
    pendel["pendel_chf"] = kosten
    pendel["geschaetzt"] = geschaetzt
    return pendel


def bestes_verkehrsmittel(zeile, verkehrsmittel, max_pendel):
    """
    Das beste Verkehrsmittel für eine Gemeinde.

    Regel: Von den Verkehrsmitteln, die innerhalb der maximalen Pendelzeit liegen,
    nehmen wir das günstigste. Passt keines, nehmen wir das schnellste.

    Parameter:
        zeile:          eine Zeile aus pendeln_berechnen mit <vm>_min und <vm>_chf
        verkehrsmittel: Liste der gewählten Verkehrsmittel, z. B. ["oev", "auto"]
        max_pendel:     maximale Pendelzeit pro Strecke in Minuten
    """
    # Zuerst: das schnellste (falls keines in die maximale Pendelzeit passt)
    schnellstes = verkehrsmittel[0]
    for vm in verkehrsmittel:
        if zeile[vm + "_min"] < zeile[schnellstes + "_min"]:
            schnellstes = vm

    # Dann: das günstigste von denen, die in die maximale Pendelzeit passen
    guenstigstes = None
    for vm in verkehrsmittel:
        if zeile[vm + "_min"] <= max_pendel:
            if guenstigstes is None or zeile[vm + "_chf"] < zeile[guenstigstes + "_chf"]:
                guenstigstes = vm

    if guenstigstes is None:
        return schnellstes
    return guenstigstes


# --- Kurzer Test: läuft nur bei "python api.py", nicht wenn app.py die Datei importiert ---
if __name__ == "__main__":
    for adresse in ["Bahnhofstrasse 1, Zürich", "Zürich HB", "Wetzikon", "asdfghjkl"]:
        print(adresse, "->", geocode(adresse))   # Unsinn soll None geben, nicht abstürzen
    print("Zürich-Bern km (ca. 95):", round(haversine_km(47.378, 8.540, 46.949, 7.439), 1))
    print("00d01:12:00 ->", dauer_in_minuten("00d01:12:00"), "Minuten (erwartet 72)")
