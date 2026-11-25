"""
charts.py – Grafiken des Wohnort-Finders (Arbeitspaket 4).

Verantwortlich: Ivan
KI-Hinweis: Mit Claude (Anthropic) erstellt; am 24.11.2026 mit Claude vereinfacht
(Branch WF-5.6-Umbau). Am 25.11.2026 (Branch WF-5.7): Farben und Schrift ans Design
der App angepasst, Gewichte-Grafik mit Richtung.

Alle Grafiken mit matplotlib. Jede Funktion gibt eine Figur zurück,
app.py zeigt sie mit st.pyplot() an. Die Karte macht app.py direkt mit st.map().
"""

import matplotlib.pyplot as plt

# --- Farben: dieselben wie in .streamlit/config.toml und style.css ---
PAPIER = "#f7f4ee"       # Hintergrund
TINTE = "#22211e"        # Schrift
GRAU = "#8a857a"         # Achsen und Nebensachen
LINIE = "#d9d2c3"        # Gitterlinien
FARBE_ALLE = "#cfc8b8"   # alle Gemeinden (zurückhaltend)
FARBE_TOP = "#2f6b4f"    # deine Top-Gemeinden (Waldgrün)
FARBE_HEUTE = TINTE      # heutiger Wohnort
# Kostenteile: drei gut unterscheidbare Farben (auch bei Farbsehschwäche geprüft)
FARBEN_KOSTEN = {"Steuern": "#1e8058", "Miete": "#bd8a2f", "Pendeln": "#a04673"}


def stil():
    """Einheitliches Aussehen für alle Grafiken (gilt für alle Figuren danach)."""
    plt.rcParams["figure.facecolor"] = PAPIER
    plt.rcParams["axes.facecolor"] = PAPIER
    plt.rcParams["axes.edgecolor"] = LINIE
    plt.rcParams["axes.labelcolor"] = GRAU
    plt.rcParams["axes.spines.top"] = False
    plt.rcParams["axes.spines.right"] = False
    plt.rcParams["axes.grid"] = True
    plt.rcParams["grid.color"] = LINIE
    plt.rcParams["grid.linewidth"] = 0.6
    plt.rcParams["xtick.color"] = GRAU
    plt.rcParams["ytick.color"] = TINTE
    plt.rcParams["text.color"] = TINTE
    plt.rcParams["font.size"] = 10
    plt.rcParams["legend.frameon"] = False


stil()


def chf(betrag):
    """Betrag als Text mit Schweizer Tausendertrennzeichen, z. B. 11'400."""
    return f"{betrag:,.0f}".replace(",", "'")


def tausender(wert, position):
    """Achsenbeschriftung mit Tausendertrennzeichen (für matplotlib FuncFormatter)."""
    return chf(wert)


def scatter_chart(df, heute_nr, top_nrs):
    """
    Streudiagramm Miete gegen Steuern (Vorschlag des Dozenten).

    Jeder Punkt ist eine Gemeinde. Es zeigt: Wo die Steuern tief sind,
    ist die Miete oft hoch, und umgekehrt.
    """
    fig, ax = plt.subplots(figsize=(8, 4.5))

    # Alle Gemeinden klein und zurückhaltend
    ax.scatter(df["miete_chf"], df["steuer_chf"], color=FARBE_ALLE, s=10, label="Alle Gemeinden")

    # Der heutige Wohnort als Stern
    heute = df[df["bfs_nr"] == heute_nr]
    ax.scatter(heute["miete_chf"], heute["steuer_chf"], color=FARBE_HEUTE, marker="*", s=220,
               edgecolors=PAPIER, linewidths=1, label="Heute", zorder=3)

    # Die besten Gemeinden als grüne Kreise mit ihrem Platz (1 bis 5). Namen würden sich
    # überlappen, weil Gemeinden im gleichen Kanton oft die gleiche geschätzte Miete haben.
    # Ein kleiner Versatz nach rechts verhindert, dass gleiche Punkte genau aufeinander liegen.
    versatz = 0
    for platz in range(len(top_nrs)):
        zeile = df[df["bfs_nr"] == top_nrs[platz]].iloc[0]
        x = zeile["miete_chf"] + versatz
        if platz == 0:
            ax.scatter(x, zeile["steuer_chf"], color=FARBE_TOP, s=230, edgecolors=PAPIER, linewidths=1.5,
                       label="Deine Top 5 (Zahl = Platz)", zorder=4)
        else:
            ax.scatter(x, zeile["steuer_chf"], color=FARBE_TOP, s=230, edgecolors=PAPIER, linewidths=1.5, zorder=4)
        ax.text(x, zeile["steuer_chf"], str(platz + 1), color=PAPIER, fontsize=8, fontweight="bold",
                ha="center", va="center", zorder=5)
        versatz = versatz + 35

    ax.set_xlabel("Miete (CHF pro Monat, geschätzt)")
    ax.set_ylabel("Steuern (CHF pro Jahr)")
    ax.xaxis.set_major_formatter(plt.FuncFormatter(tausender))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(tausender))
    ax.legend(loc="upper right")
    fig.tight_layout()
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

    fig, ax = plt.subplots(figsize=(8, 3.6))
    # Balken übereinander stapeln: "left" sagt, wo der nächste Teil anfängt.
    # Ein Rand in Papierfarbe trennt die Teile sichtbar voneinander.
    ax.barh(namen, steuern, height=0.6, color=FARBEN_KOSTEN["Steuern"], edgecolor=PAPIER,
            linewidth=2, label="Steuern")
    ax.barh(namen, mieten, height=0.6, left=steuern, color=FARBEN_KOSTEN["Miete"], edgecolor=PAPIER,
            linewidth=2, label="Miete")
    links = []
    totale = []
    for i in range(len(namen)):
        links.append(steuern[i] + mieten[i])
        totale.append(steuern[i] + mieten[i] + pendeln[i])
    ax.barh(namen, pendeln, height=0.6, left=links, color=FARBEN_KOSTEN["Pendeln"], edgecolor=PAPIER,
            linewidth=2, label="Pendeln")

    # Total rechts neben jedem Balken
    for i in range(len(namen)):
        ax.text(totale[i] + 300, i, chf(totale[i]), va="center", fontsize=9)

    ax.invert_yaxis()   # heute oben, dann Platz 1, 2, 3 ...
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("CHF pro Jahr")
    ax.xaxis.set_major_formatter(plt.FuncFormatter(tausender))
    ax.set_xlim(0, max(totale) * 1.12)   # Platz für die Totale rechts
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3)
    fig.tight_layout()
    return fig


def gewichte_chart(gewichte):
    """
    Horizontale Balken: Was ist der Nutzerin wichtig, und in welche Richtung?

    Parameter:
        gewichte: Liste aus model.gewichte(), z. B.
                  [{"merkmal": "Steuern", "prozent": 20, "text": "Tiefe Steuern"}, ...]
    """
    # Wichtigstes zuoberst
    gewichte = sorted(gewichte, key=lambda g: g["prozent"], reverse=True)
    texte = []
    prozent = []
    for g in gewichte:
        texte.append(g["text"])
        prozent.append(g["prozent"])

    fig, ax = plt.subplots(figsize=(7, 2.2))
    ax.barh(texte, prozent, color=FARBE_TOP, height=0.55)
    for i in range(len(texte)):
        ax.text(prozent[i] + 1.5, i, f"{prozent[i]} %", va="center", fontsize=10)
    ax.set_xlim(0, 110)
    ax.invert_yaxis()
    ax.grid(visible=False)
    ax.spines["bottom"].set_visible(False)
    ax.set_xticks([])
    fig.tight_layout()
    return fig
