"""
pendel_kalibrieren.py – bestimmt die Schätzformel für die Pendelzeit (Task 2.3).

Fragt ein paar echte ÖV-Verbindungen ab, berechnet für jede die Luftlinie
und legt mit einer linearen Regression eine Gerade durch die Punkte:
    Minuten = a + b * km
Die Werte a und b werden danach in api.py bei PENDEL_A und PENDEL_B eingetragen.
Weil es Bahnhof-zu-Bahnhof-Verbindungen sind, ist die Formel eine Untergrenze; das ist
gewollt, siehe Kommentar in api.py und scripts/schaetzung_pruefen.py.

Muss nur einmal laufen. Ausführen (im Projektordner, Umgebung aktiv):
    python scripts/pendel_kalibrieren.py

KI-Hinweis: Erstellt mit Unterstützung von Claude (Anthropic), selbst geprüft und getestet.
"""

import sys
import time
from pathlib import Path

import pandas as pd
import requests
from sklearn.linear_model import LinearRegression

# Damit wir api.py aus dem Ordner scripts/ heraus importieren können
sys.path.append(str(Path(__file__).resolve().parent.parent))
from api import TRANSPORT_URL, dauer_in_minuten, geocode, haversine_km

# Bewusst gemischt: nah und weit, Stadt und Land, verschiedene Arbeitsorte
VERBINDUNGEN = [
    ("Wetzikon", "Zürich HB"),
    ("Uster", "Zürich HB"),
    ("Bülach", "Zürich HB"),
    ("Winterthur", "Zürich HB"),
    ("Baden", "Zürich HB"),
    ("Zug", "Zürich HB"),
    ("Rapperswil SG", "Zürich HB"),   # nur "Rapperswil" findet Rapperswil BE!
    ("Einsiedeln", "Zürich HB"),
    ("Frauenfeld", "Zürich HB"),
    ("Aarau", "Zürich HB"),
    ("Luzern", "Zürich HB"),
    ("Chur", "Zürich HB"),
    ("Basel", "Zürich HB"),         # weitere weite Strecken, damit nicht Chur
    ("Schaffhausen", "Zürich HB"),  # allein die Steigung bestimmt
    ("Glarus", "Zürich HB"),
    ("Wil SG", "St. Gallen"),
    ("Herisau", "St. Gallen"),
    ("Thun", "Bern"),
    ("Fribourg", "Bern"),
]

zeilen = []
for start, ziel in VERBINDUNGEN:
    ort_start = geocode(start)
    ort_ziel = geocode(ziel)
    if ort_start is None or ort_ziel is None:
        print("Ort nicht gefunden, übersprungen:", start, ziel)
        continue
    km = haversine_km(ort_start[0], ort_start[1], ort_ziel[0], ort_ziel[1])

    # Immer gleiche Abfahrtszeit wie in der App: Montag 07:30
    params = {}
    params["from"] = start
    params["to"] = ziel
    params["date"] = "2026-11-23"   # ein Montag
    params["time"] = "07:30"
    params["limit"] = 1
    r = requests.get(TRANSPORT_URL, params=params, timeout=15)
    if r.status_code != 200 or len(r.json()["connections"]) == 0:
        print("Keine Verbindung, übersprungen:", start, ziel)
        continue
    minuten = dauer_in_minuten(r.json()["connections"][0]["duration"])

    # Den gefundenen Namen mit ausgeben, damit man falsche Treffer sofort sieht
    print(f"{start:>13} -> {ziel:<11} {km:6.1f} km  {minuten:4d} Min.  ({ort_start[2]})")
    zeilen.append({"km": km, "minuten": minuten})
    time.sleep(1)   # kurze Pause, damit wir die API nicht überlasten (Fair Use)

df = pd.DataFrame(zeilen)

# Lineare Regression wie in Übung 05: Y = b0 + b1 * X
modell = LinearRegression()
modell.fit(df[["km"]], df["minuten"])
a = modell.intercept_
b = modell.coef_[0]

print()
print(f"Ergebnis: Minuten = {a:.1f} + {b:.2f} * km")
print(f"In api.py eintragen: PENDEL_A = {a:.1f} und PENDEL_B = {b:.2f}")

# Wie gut passt die Gerade? Mittlere Abweichung in Minuten
df["geschaetzt"] = modell.predict(df[["km"]])
abweichung = (df["minuten"] - df["geschaetzt"]).abs().mean()
print(f"Mittlere Abweichung der Schätzung: {abweichung:.0f} Minuten")
