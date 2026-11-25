"""
model.py – Machine Learning (Arbeitspaket 3).

Verantwortlich: Ivan
KI-Hinweis: Mit Claude (Anthropic) erstellt; am 24.11.2026 mit Claude vereinfacht
(Branch WF-5.6-Umbau). Am 25.11.2026 (Branch WF-5.7): typischste Gemeinde pro Gruppe,
Richtung der Gewichte.

Zwei Modelle mit scikit-learn (wie in Übung 5: Daten vorbereiten, Lernart wählen, trainieren):

1. Clustering mit k-means (ohne Labels):
   Teilt die Gemeinden in 10 Gruppen ein, z. B. «günstig und weit» oder «teuer und nah».
   Aus jeder Gruppe zeigen wir der Nutzerin eine Gemeinde zum Bewerten. So bewertet
   sie möglichst unterschiedliche Gemeinden.

2. Klassifikation mit logistischer Regression (mit Labels):
   Die Nutzerin bewertet die Gemeinden mit «gefällt» (1) oder «gefällt nicht» (0).
   Das Modell lernt daraus, welche Merkmale ihr wichtig sind, und sagt für alle
   anderen Gemeinden voraus, wie wahrscheinlich sie ihr gefallen.
"""

from sklearn.cluster import KMeans
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

# Merkmale (Features), aus denen die Modelle lernen
MERKMALE = ["steuer_chf", "miete_chf", "pendel_chf", "pendel_min"]
MERKMAL_TEXT = {"steuer_chf": "Steuern", "miete_chf": "Miete", "pendel_chf": "Pendelkosten",
                "pendel_min": "Pendelzeit"}
# Text für die Richtung: (bei negativem Koeffizienten, bei positivem Koeffizienten)
RICHTUNG_TEXT = {
    "steuer_chf": ("Tiefe Steuern", "Höhere Steuern"),
    "miete_chf": ("Tiefe Miete", "Höhere Miete (z. B. zentrale Lage)"),
    "pendel_chf": ("Tiefe Pendelkosten", "Höhere Pendelkosten"),
    "pendel_min": ("Kurzer Arbeitsweg", "Längerer Arbeitsweg (z. B. ländlich wohnen)"),
}

# So viele Gemeinden zeigen wir zum Bewerten
ANZAHL_BEWERTEN = 10

# Mit weniger Bewertungen trainieren wir das Modell nicht (zu unsicher)
MIN_BEWERTUNGEN = 6


def select_for_rating(df):
    """
    Wählt mit k-means ANZAHL_BEWERTEN möglichst unterschiedliche Gemeinden aus.

    Parameter:
        df: Gemeinden mit bfs_nr und den MERKMALEN (schon nach max. Pendelzeit gefiltert)

    Rückgabe: Liste mit den bfs_nr der ausgewählten Gemeinden
    """
    # Standardisieren: Steuern (Tausende CHF) und Minuten (Dutzende) auf die gleiche Skala
    # bringen, sonst würden die grossen Frankenbeträge alles bestimmen.
    werte = StandardScaler().fit_transform(df[MERKMALE])

    # k-means teilt die Gemeinden in ANZAHL_BEWERTEN Gruppen (Cluster) ein.
    # random_state=0: bei jedem Start die gleichen Gruppen
    kmeans = KMeans(n_clusters=ANZAHL_BEWERTEN, n_init=10, random_state=0)
    kmeans.fit(werte)

    # Aus jeder Gruppe die typischste Gemeinde nehmen: die, die am nächsten beim
    # Zentrum der Gruppe liegt. kmeans.transform() gibt pro Gemeinde den Abstand
    # zu jedem Zentrum (eine Spalte pro Gruppe).
    df = df.copy()   # Kopie, damit wir die Tabelle von app.py nicht verändern
    df["gruppe"] = kmeans.labels_
    abstaende = kmeans.transform(werte)
    df["abstand"] = abstaende.min(axis=1)   # Abstand zum Zentrum der eigenen Gruppe
    auswahl = []
    for gruppe in range(ANZAHL_BEWERTEN):
        gemeinden_der_gruppe = df[df["gruppe"] == gruppe].sort_values("abstand")
        auswahl.append(int(gemeinden_der_gruppe["bfs_nr"].iloc[0]))
    return auswahl


def train_model(bewertet):
    """
    Trainiert die logistische Regression auf den Bewertungen der Nutzerin.

    Parameter:
        bewertet: DataFrame mit den MERKMALEN und der Spalte "gefaellt" (1 oder 0)

    Rückgabe: (modell, skalierer) oder None, wenn das Modell nicht trainiert werden kann
    """
    # Zu wenige Bewertungen: das Modell wäre reiner Zufall
    if len(bewertet) < MIN_BEWERTUNGEN:
        return None
    # Das Modell braucht beide Klassen: mindestens ein «gefällt» und ein «gefällt nicht»
    if bewertet["gefaellt"].nunique() < 2:
        return None

    # Merkmale standardisieren (gleich wie bei k-means) und Modell trainieren
    skalierer = StandardScaler()
    x = skalierer.fit_transform(bewertet[MERKMALE])
    y = bewertet["gefaellt"]
    modell = LogisticRegression()
    modell.fit(x, y)
    return (modell, skalierer)


def score_all(modell, skalierer, df):
    """
    Wahrscheinlichkeit (0 bis 100), dass der Nutzerin eine Gemeinde gefällt.

    predict_proba gibt pro Gemeinde zwei Werte: [P(gefällt nicht), P(gefällt)].
    Wir nehmen den zweiten Wert (Spalte 1) und rechnen ihn in Prozent um.
    """
    x = skalierer.transform(df[MERKMALE])
    wahrscheinlichkeit = modell.predict_proba(x)[:, 1]
    return (wahrscheinlichkeit * 100).round()


def gewichte(modell):
    """
    Wie wichtig ist jedes Merkmal für die Nutzerin, und in welche Richtung?

    Die logistische Regression hat pro Merkmal einen Koeffizienten. Je grösser der
    Betrag, desto stärker beeinflusst das Merkmal die Entscheidung. Das Vorzeichen
    zeigt die Richtung: negativ heisst «weniger ist besser» (z. B. tiefe Steuern).

    Rückgabe: Liste mit einem Dictionary pro Merkmal, z. B.
              {"merkmal": "Steuern", "prozent": 20, "text": "Tiefe Steuern"}
    """
    koeffizienten = modell.coef_[0]
    summe = 0
    for wert in koeffizienten:
        summe = summe + abs(wert)

    resultat = []
    for i in range(len(MERKMALE)):
        merkmal = MERKMALE[i]
        if summe == 0:
            prozent = 0
        else:
            prozent = round(abs(koeffizienten[i]) / summe * 100)
        if koeffizienten[i] < 0:
            text = RICHTUNG_TEXT[merkmal][0]   # weniger gefällt besser
        else:
            text = RICHTUNG_TEXT[merkmal][1]   # mehr gefällt besser
        resultat.append({"merkmal": MERKMAL_TEXT[merkmal], "prozent": prozent, "text": text})
    return resultat
