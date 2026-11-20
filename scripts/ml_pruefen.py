"""Prüft das ML-Modell mit simulierten Testpersonen (Task 3.5)."""
# Mit Claude erstellt, angepasst von Ivan
#
# Ausführen im Projektordner:  python scripts/ml_pruefen.py
#
# Jede Testperson hat einen bekannten Wert der Pendelzeit (CHF pro Jahr und Minute).
# Sie beantwortet die Paarvergleiche der App wie ein Mensch: meistens passend zu
# ihrem Wert, aber nicht immer (Zufall). Danach prüfen wir, ob das Modell den Wert
# wiederfindet. Ergebnis als Tabelle für das README.

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # damit data.py usw. gefunden werden

from api import commute_minutes   # noqa: E402
from data import get_municipalities, get_rent, get_tax   # noqa: E402
from model import fit_preferences, make_pairs, select_for_rating   # noqa: E402
from scoring import wohnkosten   # noqa: E402

TESTPERSONEN = {"Sparfuchs": 50, "Ausgewogen": 300, "Zeitoptimiererin": 800}
DURCHLAEUFE = 200
# Wie zufällig eine Person entscheidet: Bei 1'000 CHF Unterschied wählt sie
# die bessere Gemeinde in rund 73 % der Fälle
UNSICHERHEIT_CHF = 1000
ARBEITSORT = (47.3779, 8.5403)   # Zürich HB
MAX_PENDEL = 60


def simulierte_vergleiche(gemeinden, paare, wert, rng):
    """Antworten einer Testperson mit bekanntem Wert der Pendelzeit."""
    zeilen = []
    for a, b in paare:
        ga, gb = gemeinden.loc[a], gemeinden.loc[b]
        # Wie viel besser ist A für diese Person (in CHF pro Jahr, Zeit eingerechnet)?
        vorteil_a = (gb["gesamtkosten"] + wert * gb["pendel_min"]) - (ga["gesamtkosten"] + wert * ga["pendel_min"])
        wahrscheinlichkeit_a = 1 / (1 + np.exp(-vorteil_a / UNSICHERHEIT_CHF))
        zeilen.append({
            "gesamtkosten_a": ga["gesamtkosten"], "pendel_min_a": ga["pendel_min"],
            "gesamtkosten_b": gb["gesamtkosten"], "pendel_min_b": gb["pendel_min"],
            "wahl_a": int(rng.random() < wahrscheinlichkeit_a),
        })
    return pd.DataFrame(zeilen)


def main():
    """Simuliert alle Testpersonen und druckt die Ergebnistabelle."""
    gemeinden = get_municipalities()
    df = gemeinden.merge(get_tax(100_000, "ledig"), on="bfs_nr").merge(get_rent(3), on="bfs_nr")
    df["gesamtkosten"] = wohnkosten(df)
    # Ohne Live-Abfragen (max_abfragen=0), damit der Test schnell und wiederholbar ist
    df = df.merge(commute_minutes(*ARBEITSORT, gemeinden, max_abfragen=0), on="bfs_nr")
    df = df[df["pendel_min"] <= MAX_PENDEL].reset_index(drop=True)

    auswahl = df[df["bfs_nr"].isin(select_for_rating(df))]
    paare = make_pairs(auswahl)
    nach_nr = df.set_index("bfs_nr")
    rng = np.random.default_rng(42)

    print(f"{len(paare)} Paarvergleiche, {DURCHLAEUFE} Durchläufe pro Testperson\n")
    print("| Testperson | wahrer Wert (CHF/Min.) | gelernt: Median | mittlere 50 % |")
    print("| --- | --- | --- | --- |")
    for name, wert in TESTPERSONEN.items():
        gelernt = []
        for _ in range(DURCHLAEUFE):
            modell = fit_preferences(simulierte_vergleiche(nach_nr, paare, wert, rng))
            if modell is not None:
                gelernt.append(modell["chf_pro_minute"])
        unten, mitte, oben = np.percentile(gelernt, [25, 50, 75]).round()
        print(f"| {name} | {wert} | {mitte:.0f} | {unten:.0f}–{oben:.0f} |")


if __name__ == "__main__":
    main()
