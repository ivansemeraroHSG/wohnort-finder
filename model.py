"""
model.py – Machine Learning (Arbeitspaket 3).

Verantwortlich: Ivan
Mit Claude erstellt, angepasst von Ivan

Ablauf:
1. k-means wählt möglichst unterschiedliche Gemeinden aus (günstig/teuer, nah/weit).
2. Daraus entstehen Paare mit einem echten Trade-off: eine Gemeinde ist günstiger,
   die andere näher. Die Nutzerin wählt jeweils die Gemeinde, die sie lieber hätte.
3. Eine logistische Regression lernt aus diesen Entscheiden, wie viel CHF pro Jahr
   der Nutzerin eine Minute Pendelzeit (pro Weg) wert ist.
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

# Merkmale: Kosten pro Jahr und Pendelzeit pro Weg
MERKMALE = ["gesamtkosten", "pendel_min"]

# Darunter ist das Modell zu unsicher; die App rankt dann nur nach Kosten
MIN_VERGLEICHE = 6

# Franken in Tausend umrechnen, damit beide Merkmale ähnlich grosse Zahlen haben
CHF_EINHEIT = 1000

# Sinnvoller Bereich für den Wert einer Minute Pendelzeit (CHF pro Jahr). Paare mit einem
# Grenzwert ausserhalb sagen fast nichts aus (jede Person würde gleich entscheiden).
GRENZWERT_MIN = 20
GRENZWERT_MAX = 2000


def select_for_rating(df: pd.DataFrame, n: int = 12) -> list[int]:
    """
    Wählt n möglichst unterschiedliche Gemeinden aus (k-means).

    Parameter:
        df: Gemeinden mit bfs_nr und MERKMALE, schon nach max. Pendelzeit gefiltert
        n:  Anzahl Gemeinden bzw. Cluster

    Rückgabe: Liste mit den bfs_nr der ausgewählten Gemeinden
    """
    # Standardisieren, sonst zählen Franken (Tausende) viel mehr als Minuten (Dutzende)
    werte = StandardScaler().fit_transform(df[MERKMALE])
    kmeans = KMeans(n_clusters=n, n_init=10, random_state=0).fit(werte)

    # Pro Cluster die Gemeinde, die dem Zentrum am nächsten liegt
    auswahl = []
    for zentrum in kmeans.cluster_centers_:
        abstand = np.linalg.norm(werte - zentrum, axis=1)
        auswahl.append(int(df["bfs_nr"].iloc[abstand.argmin()]))
    return list(dict.fromkeys(auswahl))   # doppelte entfernen, Reihenfolge behalten


def make_pairs(df_auswahl: pd.DataFrame, n_paare: int = 12) -> list[tuple[int, int]]:
    """
    Bildet Paare, bei denen eine Gemeinde günstiger und die andere näher ist.

    Jedes Paar fragt indirekt: "Ist dir eine Minute weniger Pendeln mehr als X CHF wert?"
    Die Paare werden so gewählt, dass diese Grenzwerte X von tief bis hoch verteilt sind.

    Rückgabe: Liste von (bfs_nr_a, bfs_nr_b)
    """
    kandidaten = []
    for (_, a), (_, b) in itertools.combinations(df_auswahl.iterrows(), 2):
        mehrkosten = a["gesamtkosten"] - b["gesamtkosten"]
        mehr_minuten = a["pendel_min"] - b["pendel_min"]
        if mehrkosten * mehr_minuten < 0:   # nur echte Trade-offs
            grenzwert = abs(mehrkosten / mehr_minuten)
            if GRENZWERT_MIN <= grenzwert <= GRENZWERT_MAX:
                kandidaten.append((grenzwert, int(a["bfs_nr"]), int(b["bfs_nr"])))
    if not kandidaten:
        return []
    kandidaten.sort()

    # Pro Zielwert (gleichmässig auf einer log-Skala) das Paar mit dem nächsten Grenzwert
    ziele = np.geomspace(GRENZWERT_MIN, GRENZWERT_MAX, n_paare)
    grenzwerte = np.array([k[0] for k in kandidaten])
    stellen = [int(np.abs(np.log(grenzwerte) - np.log(z)).argmin()) for z in ziele]
    return [(kandidaten[i][1], kandidaten[i][2]) for i in dict.fromkeys(stellen)]


def fit_preferences(vergleiche: pd.DataFrame) -> dict | None:
    """
    Trainiert eine logistische Regression auf den Paarvergleichen.

    Parameter:
        vergleiche: eine Zeile pro Vergleich mit gesamtkosten_a, pendel_min_a,
                    gesamtkosten_b, pendel_min_b und wahl_a (1 = A gewählt, 0 = B)

    Rückgabe: {"modell", "chf_pro_minute"} oder None, wenn zu wenige Vergleiche
              oder die Entscheide sich widersprechen
    """
    if len(vergleiche) < MIN_VERGLEICHE:
        return None

    # Merkmal = Unterschied A minus B; Ergebnis = wurde A gewählt?
    unterschied = np.column_stack([
        (vergleiche["gesamtkosten_a"] - vergleiche["gesamtkosten_b"]) / CHF_EINHEIT,
        vergleiche["pendel_min_a"] - vergleiche["pendel_min_b"],
    ])
    gewaehlt = vergleiche["wahl_a"].to_numpy()
    # Jeden Vergleich auch umgekehrt (B gegen A) aufnehmen: So kommen beide Klassen vor,
    # und das Modell braucht keinen Achsenabschnitt (die Reihenfolge A/B ist zufällig).
    x = np.vstack([unterschied, -unterschied])
    y = np.concatenate([gewaehlt, 1 - gewaehlt])
    modell = LogisticRegression(fit_intercept=False).fit(x, y)

    pro_chf = modell.coef_[0][0] / CHF_EINHEIT
    pro_minute = modell.coef_[0][1]
    if pro_chf < 0 and pro_minute < 0:
        chf_pro_minute = pro_minute / pro_chf
    elif pro_minute < 0:
        chf_pro_minute = GRENZWERT_MAX   # immer die nähere gewählt, egal wie teuer
    elif pro_chf < 0:
        chf_pro_minute = 0.0   # immer die günstigere gewählt, Pendelzeit egal
    else:
        return None   # Entscheide widersprechen sich (teurer und weiter bevorzugt)
    return {"modell": modell, "chf_pro_minute": chf_pro_minute}


def persoenliche_kosten(modell: dict, df: pd.DataFrame) -> pd.Series:
    """
    Kosten inklusive Zeit: Gesamtkosten + Wert der Pendelzeit × Minuten.

    Je tiefer, desto besser passt die Gemeinde zur Nutzerin (gleicher Index wie df).
    """
    return (df["gesamtkosten"] + modell["chf_pro_minute"] * df["pendel_min"]).round()
