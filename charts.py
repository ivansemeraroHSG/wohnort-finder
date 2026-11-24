"""
charts.py – Grafiken des Wohnort-Finders (Arbeitspaket 4).

Verantwortlich: Ivan
KI-Hinweis: Mit Claude (Anthropic) erstellt; am 24.11.2026 mit Claude vereinfacht
(Branch WF-5.6-Umbau).

Alle Grafiken mit matplotlib. Jede Funktion gibt eine Figur zurück,
app.py zeigt sie mit st.pyplot() an. Die Karte macht app.py direkt mit st.map().
"""

import matplotlib.pyplot as plt

# Gleiche Farbe für gleiche Bedeutung in allen Grafiken
FARBE_ALLE = "lightgray"
FARBE_TOP = "tab:green"
FARBE_HEUTE = "black"
FARBEN_KOSTEN = {"Steuern": "tab:blue", "Miete": "tab:orange", "Pendeln": "tab:purple"}


def chf(betrag):
    """Betrag als Text mit Schweizer Tausendertrennzeichen, z. B. 11'400."""
    return f"{betrag:,.0f}".replace(",", "'")


def scatter_chart(df, heute_nr, top_nrs):
    """
    Streudiagramm Miete gegen Steuern (Vorschlag des Dozenten).

    Jeder Punkt ist eine Gemeinde. Es zeigt: Wo die Steuern tief sind,
    ist die Miete oft hoch, und umgekehrt.
    """
    fig, ax = plt.subplots(figsize=(8, 5))

    # Alle Gemeinden in Grau
    ax.scatter(df["miete_chf"], df["steuer_chf"], color=FARBE_ALLE, s=10, label="Alle Gemeinden")

    # Die besten Gemeinden in Grün, mit Namen
    top = df[df["bfs_nr"].isin(top_nrs)]
    ax.scatter(top["miete_chf"], top["steuer_chf"], color=FARBE_TOP, s=60, label="Deine Top 5")
    for name, miete, steuer in zip(top["name"], top["miete_chf"], top["steuer_chf"]):
        ax.annotate(name, (miete, steuer), fontsize=8)

    # Der heutige Wohnort als schwarzer Stern
    heute = df[df["bfs_nr"] == heute_nr]
    ax.scatter(heute["miete_chf"], heute["steuer_chf"], color=FARBE_HEUTE, marker="*", s=200, label="Heute")

    ax.set_xlabel("Miete (CHF pro Monat, geschätzt)")
    ax.set_ylabel("Steuern (CHF pro Jahr)")
    ax.legend()
    return fig


def kosten_chart(df, heute_nr, top_nrs):
    """Gestapelte Balken: Steuern, Miete und Pendeln für heute und die Top 5."""
    # Zuerst der heutige Wohnort, dann Platz 1 bis 5
    namen = []
    steuern = []
    mieten = []
    pendeln = []
    for nr in [heute_nr] + top_nrs:
        zeile = df[df["bfs_nr"] == nr].iloc[0]
        if nr == heute_nr:
            namen.append(zeile["name"] + " (heute)")
        else:
            namen.append(zeile["name"])
        steuern.append(zeile["steuer_chf"])
        mieten.append(12 * zeile["miete_chf"])
        pendeln.append(zeile["pendel_chf"])

    fig, ax = plt.subplots(figsize=(8, 4))
    # Balken übereinander stapeln: "left" sagt, wo der nächste Teil anfängt
    ax.barh(namen, steuern, color=FARBEN_KOSTEN["Steuern"], label="Steuern")
    links = steuern
    ax.barh(namen, mieten, left=links, color=FARBEN_KOSTEN["Miete"], label="Miete")
    links = []
    for i in range(len(namen)):
        links.append(steuern[i] + mieten[i])
    ax.barh(namen, pendeln, left=links, color=FARBEN_KOSTEN["Pendeln"], label="Pendeln")

    ax.invert_yaxis()   # heute oben, dann Platz 1, 2, 3 ...
    ax.set_xlabel("CHF pro Jahr")
    ax.legend()
    return fig


def gewichte_chart(gewichte):
    """
    Horizontale Balken: Wie wichtig sind Steuern, Miete und Pendelzeit für die Nutzerin?

    Parameter:
        gewichte: Dictionary aus model.gewichte(), z. B. {"Steuern": 20, "Miete": 30, "Pendelzeit": 50}
    """
    namen = list(gewichte.keys())
    prozent = list(gewichte.values())

    fig, ax = plt.subplots(figsize=(6, 2.5))
    ax.barh(namen, prozent, color=FARBE_TOP)
    for i in range(len(namen)):
        ax.text(prozent[i] + 1, i, f"{prozent[i]} %", va="center")
    ax.set_xlim(0, 110)
    ax.set_xlabel("Wichtigkeit in %")
    ax.invert_yaxis()
    return fig
