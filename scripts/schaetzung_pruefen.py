"""
schaetzung_pruefen.py – prüft die ÖV-Schätzformel in api.py an echten Zeiten (Task 2.9).

Liest alle echten ÖV-Zeiten aus data/cache.db (entstehen beim Benutzen der App) und
vergleicht sie mit der Schätzung. Die Schätzung soll eine Untergrenze sein: fast nie
länger als die echte Zeit, damit keine gute Gemeinde zu früh aus der Rangliste fällt.

Ausführen (im Projektordner, Umgebung aktiv):
    python scripts/schaetzung_pruefen.py

Mit Claude erstellt, angepasst von Gregor Weber
"""

import sys
from pathlib import Path

import pandas as pd

# Damit wir api.py und data.py aus dem Ordner scripts/ heraus importieren können
sys.path.append(str(Path(__file__).resolve().parent.parent))
from api import KEINE_VERBINDUNG, haversine_km, schaetze_minuten
from data import get_cache_connection, get_municipalities

# Zum Vergleich: Gerade durch die Punkte (Durchschnitt statt Untergrenze), Analyse 20.11.2026
DURCHSCHNITT_A = 24.3
DURCHSCHNITT_B = 1.61

con = get_cache_connection()
echte = pd.read_sql("SELECT bfs_nr, ziel, minuten FROM pendel_cache WHERE minuten != ?",
                    con, params=(KEINE_VERBINDUNG,))
con.close()
df = echte.merge(get_municipalities()[["bfs_nr", "name", "lat", "lon"]], on="bfs_nr")

km_liste = []
for index, zeile in df.iterrows():
    ziel_lat, ziel_lon = zeile["ziel"].split(",")   # im Cache als Text "lat,lon"
    km_liste.append(haversine_km(float(ziel_lat), float(ziel_lon), zeile["lat"], zeile["lon"]))
df["km"] = km_liste
df["untergrenze"] = schaetze_minuten(df["km"]).round(0)
df["durchschnitt"] = (DURCHSCHNITT_A + DURCHSCHNITT_B * df["km"]).round(0)

print(f"{len(df)} echte ÖV-Zeiten aus dem Cache")
for spalte in ["untergrenze", "durchschnitt"]:
    zu_lang = (df["minuten"] < df[spalte]).mean() * 100
    abweichung = (df["minuten"] - df[spalte]).abs().mean()
    print(f"{spalte:>12}: schätzt bei {zu_lang:.0f} % zu lang, mittlere Abweichung {abweichung:.0f} Min.")

print("\nBeispiele (Minuten):")
beispiele = df[df["name"].isin(["Zug", "Baden", "Schaffhausen", "Rapperswil-Jona"])]
print(beispiele[["name", "km", "minuten", "untergrenze", "durchschnitt"]].round(1).to_string(index=False))
