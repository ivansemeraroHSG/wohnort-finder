"""
steuern_laden.py – lädt die Steuerbelastung aller Gemeinden vom ESTV-Steuerrechner (einmalig).

Verantwortlich: Ivan (Arbeitspaket 1)
KI-Hinweis: Mit Claude (Anthropic) erstellt; Kommentare am 24.11.2026 mit Claude ergänzt
(Branch WF-5.6-Umbau).

Die ESTV hat keine offizielle API. Wir nutzen die Schnittstelle, mit der die Webseite
swisstaxcalculator.estv.admin.ch selbst ihre Karte füllt. Die Felder in «anfrage»
sind dieselben, die die Webseite beim geografischen Vergleich sendet.
Darum läuft das Skript nur einmal beim Aufbau der Daten und nie live in der App.
Ergebnis: data/raw/steuern_2026.csv (liegt schon im Projekt, muss nicht neu geladen werden).

Ausführen im Projektordner:  python scripts/steuern_laden.py
"""

import time
from pathlib import Path

import pandas as pd
import requests

URL = "https://swisstaxcalculator.estv.admin.ch/delegate/ost-integration/v1/maps/income-tax-values/DE"
STEUERJAHR = 2026
ZIEL = Path(__file__).resolve().parent.parent / "data" / "raw" / "steuern_2026.csv"

# Nummer des Haushaltstyps im ESTV-Formular -> unser Name
HAUSHALTE = {1: "ledig", 5: "verheiratet", 7: "verheiratet_2_kinder"}

# Bruttoarbeitseinkommen in CHF; für Werte dazwischen rechnet die App mit einem Dreisatz
EINKOMMEN = [50_000, 75_000, 100_000, 150_000, 200_000, 300_000]

PAUSE_SEK = 2  # inoffizielle Schnittstelle, darum bewusst langsam abfragen


def abfragen(haushalt_nr, einkommen):
    """Steuerbelastung aller Gemeinden für einen Haushaltstyp und ein Einkommen."""
    # Felder wie die Webseite sie beim geografischen Vergleich sendet.
    # confession 5 = keine Konfession, also ohne Kirchensteuer.
    # Pro Abfrage ist nur ein Einkommen möglich, mehrere führen zu einem Serverfehler.
    anfrage = {
        "massExportModelId": haushalt_nr,
        "belastungsVergleich": 2,
        "taxGroup": 99,
        "confession": 5,
        "incomes": [einkommen],
        "fortunes": [],
        "klasse": 1,
        "simKey": None,
        "simName": None,
        "years": [STEUERJAHR],
        "output": 1,
        "considerMaximumExposureLimit": False,
        "investmentIncome": None,
    }
    # POST statt GET, weil die Webseite die Anfrage als JSON schickt (wie bei openrouteservice)
    antwort = requests.post(URL, json=anfrage, timeout=60)
    antwort.raise_for_status()
    return antwort.json()["data"]


zeilen = []
for haushalt_nr, haushalt in HAUSHALTE.items():
    for einkommen in EINKOMMEN:
        print(f"{haushalt}, {einkommen} CHF ...")
        for g in abfragen(haushalt_nr, einkommen):
            zeilen.append({
                "bfs_nr": g["bfsId"],
                "gemeinde": g["municipality"],
                "kanton": g["canton"],
                "haushalt": haushalt,
                "einkommen": einkommen,
                "steuer_chf": g["totalAbsoluteTax"][0],
            })
        time.sleep(PAUSE_SEK)

steuern = pd.DataFrame(zeilen)
steuern.to_csv(ZIEL, index=False)
print(f"Fertig: {len(steuern)} Zeilen gespeichert in {ZIEL}")
