"""
test_api.py – Testskript für Task 2.1 (Arbeitspaket 2).

Probiert die beiden APIs aus:
1. swisstopo:             Adresse -> Koordinaten
2. transport.opendata.ch: Verbindung -> Fahrzeit in Minuten

Ausführen (im Projektordner, mit aktivierter Umgebung):
    python scripts/test_api.py

KI-Hinweis: Erstellt mit Unterstützung von Claude (Anthropic), selbst geprüft und getestet.
"""

import requests

# --- Teil 1: swisstopo – Koordinaten einer Adresse ---

url_swisstopo = "https://api3.geo.admin.ch/rest/services/api/SearchServer"

# Parameter als Dictionary (wie in der Übung 06/07)
params_swisstopo = {}
params_swisstopo["searchText"] = "Bahnhofstrasse 1 Zürich"
params_swisstopo["type"] = "locations"

r1 = requests.get(url_swisstopo, params=params_swisstopo)
print("swisstopo Statuscode:", r1.status_code)

if r1.status_code == 200:
    daten = r1.json()                      # JSON -> Python-Dictionary
    erster_treffer = daten["results"][0]   # erster Eintrag der Liste "results"
    lat = erster_treffer["attrs"]["lat"]
    lon = erster_treffer["attrs"]["lon"]
    name = erster_treffer["attrs"]["label"]
    print("Gefunden:", name)
    print("Koordinaten:", lat, lon)
else:
    print("Abfrage fehlgeschlagen")

print()

# --- Teil 2: transport.opendata.ch – Fahrzeit einer Verbindung ---

url_transport = "https://transport.opendata.ch/v1/connections"

params_transport = {}
params_transport["from"] = "Rapperswil"
params_transport["to"] = "St. Gallen"

r2 = requests.get(url_transport, params=params_transport)
print("transport Statuscode:", r2.status_code)

if r2.status_code == 200:
    daten = r2.json()
    erste_verbindung = daten["connections"][0]
    dauer = erste_verbindung["duration"]   # Text, z. B. "00d00:42:00"
    print("Dauer als Text:", dauer)

    # Text in Minuten umrechnen: Zeichen an fester Position herausschneiden
    # "00d00:42:00" -> Tage = [0:2], Stunden = [3:5], Minuten = [6:8]
    tage = int(dauer[0:2])
    stunden = int(dauer[3:5])
    minuten = int(dauer[6:8])
    total_minuten = tage * 24 * 60 + stunden * 60 + minuten
    print("Fahrzeit in Minuten:", total_minuten)
else:
    print("Abfrage fehlgeschlagen")
