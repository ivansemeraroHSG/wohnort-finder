"""
app.py – Streamlit-Oberfläche des Wohnort-Finders (Arbeitspaket 5).

Verantwortlich: Ivan
KI-Hinweis: Mit Claude (Anthropic) erstellt; am 24.11.2026 mit Claude vereinfacht
(Branch WF-5.6-Umbau).

Starten (im Projektordner, mit aktivierter Umgebung):
    streamlit run app.py

Ablauf:
- Links in der Seitenleiste: eigene Situation eingeben und auf «Berechnen» klicken.
- Schritt 1: zehn Gemeinden bewerten (gefällt / gefällt nicht), daraus lernt das ML-Modell.
- Schritt 2: Ergebnis mit Rangliste, Grafiken und Karte.

Wichtig zu Streamlit: Bei jedem Klick läuft diese ganze Datei von oben nach unten neu.
Was wir uns merken müssen (Eingaben, Ergebnisse, Modell), steht darum in st.session_state.
"""

import pandas as pd
import streamlit as st

from api import geocode, ors_schluessel, pendeln_berechnen
from charts import chf, gewichte_chart, kosten_chart, scatter_chart
from data import HAUSHALTE, get_municipalities, get_rent, get_tax
from model import ANZAHL_BEWERTEN, MERKMALE, MIN_BEWERTUNGEN, gewichte, score_all, select_for_rating, train_model
from scoring import gesamtkosten

st.set_page_config(page_title="Wohnort-Finder", page_icon="🏠")

HAUSHALT_TEXT = {
    "ledig": "Ledig, keine Kinder",
    "verheiratet": "Verheiratet, keine Kinder",
    "verheiratet_2_kinder": "Verheiratet, 2 Kinder",
}
VM_TEXT = {"oev": "ÖV", "auto": "Auto", "velo": "Velo"}
BEWERTUNG_OPTIONEN = ["keine Angabe", "gefällt", "gefällt nicht"]
ANZAHL_TOP = 10
ZUERICH_NR = 261   # BFS-Nummer von Zürich, Standardwert für «Wo wohnst du heute?»


def alles_berechnen(eingaben, gemeinden):
    """
    Steuern, Miete, Pendeln und Gesamtkosten für alle Gemeinden.

    Rückgabe: DataFrame mit einer Zeile pro Gemeinde
    """
    ziel_lat, ziel_lon, ort_name = eingaben["ort"]

    # Pendelzeiten und -kosten (fragt die APIs ab, darum mit Fortschrittsbalken)
    balken = st.progress(0.0, text="Pendelzeiten zu deinem Arbeitsort werden berechnet …")
    pendel = pendeln_berechnen(ziel_lat, ziel_lon, gemeinden, eingaben["verkehrsmittel"],
                               eingaben["buerotage"], eingaben["hat_auto"], balken)
    balken.empty()

    # Alles über die BFS-Nummer zu einer Tabelle zusammenfügen
    df = gemeinden.merge(get_tax(eingaben["einkommen"], eingaben["haushalt"]), on="bfs_nr")
    df = df.merge(get_rent(eingaben["zimmer"]), on="bfs_nr")
    df = df.merge(pendel, on="bfs_nr")
    df["gesamtkosten"] = gesamtkosten(df)

    # Vergleich mit dem heutigen Wohnort: positive Ersparnis = günstiger als heute
    heute = df[df["bfs_nr"] == eingaben["heute_nr"]].iloc[0]
    df["ersparnis"] = heute["gesamtkosten"] - df["gesamtkosten"]
    return df


# ---------------------------------------------------------------------------
# Daten laden und Titel
# ---------------------------------------------------------------------------
gemeinden = get_municipalities()
# Dictionary BFS-Nummer -> Gemeindename, z. B. 261 -> "Zürich"
namen = {}
for nr, name in zip(gemeinden["bfs_nr"], gemeinden["name"]):
    namen[nr] = name

st.title("🏠 Wohnort-Finder")
st.write(
    "Lohnt sich ein Umzug? Tiefe Steuern heissen nicht automatisch günstig wohnen: "
    "In Steuerparadiesen sind die Mieten oft hoch. Wir rechnen für deine Situation aus, "
    "was dich jede der 2'110 Schweizer Gemeinden pro Jahr kostet: Steuern, Miete und Arbeitsweg. "
    "Aus deinen Bewertungen lernt ein Machine-Learning-Modell, welche Gemeinden zu dir passen."
)

# ---------------------------------------------------------------------------
# Seitenleiste: Eingaben
# ---------------------------------------------------------------------------
st.sidebar.header("Deine Situation")
einkommen = st.sidebar.number_input("Bruttoeinkommen pro Jahr (CHF)", min_value=50000,
                                    max_value=300000, value=100000, step=5000)
haushalt = st.sidebar.selectbox("Haushalt", HAUSHALTE, format_func=lambda h: HAUSHALT_TEXT[h])
zimmer = st.sidebar.slider("Zimmer", 1, 6, 3, help="6 bedeutet 6 und mehr Zimmer")
nummern = list(namen.keys())
heute_nr = st.sidebar.selectbox("Wo wohnst du heute?", nummern, index=nummern.index(ZUERICH_NR),
                                format_func=lambda nr: namen[nr])
arbeitsort = st.sidebar.text_input("Wo arbeitest du?", "Zürich HB", help="Adresse oder Ort in der Schweiz")

st.sidebar.header("Dein Arbeitsweg")
verkehrsmittel = st.sidebar.radio("Verkehrsmittel", ["oev", "auto", "velo"], format_func=lambda vm: VM_TEXT[vm])
buerotage = st.sidebar.slider("Bürotage pro Woche", 1, 5, 5, help="Wichtig für die Autokosten")
hat_auto = st.sidebar.checkbox("Ich habe schon ein Auto", help="Dann zählen nur Benzin, Unterhalt und Reifen")
max_pendel = st.sidebar.slider("Maximale Pendelzeit pro Strecke (Min.)", 10, 90, 45, step=5)

if st.sidebar.button("Berechnen", type="primary"):
    ort = geocode(arbeitsort)
    if ort is None:
        st.sidebar.error("Diesen Arbeitsort finden wir nicht. Gib eine Adresse oder einen Ort in der Schweiz ein.")
    else:
        eingaben = {
            "einkommen": einkommen, "haushalt": haushalt, "zimmer": zimmer, "heute_nr": heute_nr,
            "ort": ort, "verkehrsmittel": verkehrsmittel, "buerotage": buerotage,
            "hat_auto": hat_auto, "max_pendel": max_pendel,
        }
        st.session_state["eingaben"] = eingaben
        st.session_state["df"] = alles_berechnen(eingaben, gemeinden)
        # Neue Eingaben: Auswahl, Bewertungen und Modell von vorher löschen
        st.session_state["auswahl"] = None
        st.session_state["modell"] = None
        for nr in nummern:
            if f"bewertung_{nr}" in st.session_state:
                del st.session_state[f"bewertung_{nr}"]

# Noch nichts berechnet: Hinweis zeigen und hier aufhören
if "df" not in st.session_state:
    st.info("Gib links deine Situation ein und klicke auf «Berechnen».")
    st.stop()

df = st.session_state["df"]
eingaben = st.session_state["eingaben"]
st.caption(f"Arbeitsort: {eingaben['ort'][2]} · Verkehrsmittel: {VM_TEXT[eingaben['verkehrsmittel']]}")
if eingaben["verkehrsmittel"] != "oev" and ors_schluessel() is None:
    st.warning("Kein Schlüssel für openrouteservice gefunden: Auto- und Velozeiten sind nur aus der Luftlinie geschätzt.")

# Nur Gemeinden innerhalb der maximalen Pendelzeit, ohne den heutigen Wohnort
kandidaten = df[(df["pendel_min"] <= eingaben["max_pendel"]) & (df["bfs_nr"] != eingaben["heute_nr"])].copy()
if len(kandidaten) < ANZAHL_BEWERTEN:
    st.warning("Zu wenige Gemeinden liegen innerhalb deiner maximalen Pendelzeit. Erhöhe sie links.")
    st.stop()

# ---------------------------------------------------------------------------
# Schritt 1: Gemeinden bewerten (Daten für das ML-Modell)
# ---------------------------------------------------------------------------
st.header("Schritt 1: Bewerte zehn Gemeinden")
st.write(
    "Ein k-means-Modell hat zehn möglichst unterschiedliche Gemeinden ausgewählt "
    "(günstig oder teuer, nah oder weit). Sag uns, ob sie dir gefallen. "
    f"Ab {MIN_BEWERTUNGEN} Bewertungen mit mindestens einem «gefällt» und einem «gefällt nicht» "
    "lernt eine logistische Regression, was dir wichtig ist."
)

# Auswahl nur einmal treffen, sonst ändert sie sich bei jedem Klick
if st.session_state.get("auswahl") is None:
    st.session_state["auswahl"] = select_for_rating(kandidaten)
auswahl = kandidaten[kandidaten["bfs_nr"].isin(st.session_state["auswahl"])]

# Bewertungstabelle: die Werte der zehn Gemeinden nebeneinander
bewertungstabelle = auswahl[["name", "kanton", "steuer_chf", "miete_chf", "pendel_min", "gesamtkosten"]]
bewertungstabelle = bewertungstabelle.rename(columns={
    "name": "Gemeinde", "kanton": "Kanton", "steuer_chf": "Steuern (CHF/Jahr)",
    "miete_chf": "Miete (CHF/Monat)", "pendel_min": "Pendelzeit (Min.)", "gesamtkosten": "Total (CHF/Jahr)",
})
st.dataframe(bewertungstabelle, hide_index=True)

# Pro Gemeinde eine Auswahl. Der key speichert die Antwort in st.session_state.
for nr, name in zip(auswahl["bfs_nr"], auswahl["name"]):
    st.radio(name, BEWERTUNG_OPTIONEN, horizontal=True, key=f"bewertung_{nr}")

if st.button("Modell trainieren", type="primary"):
    # Alle beantworteten Gemeinden sammeln: gefällt = 1, gefällt nicht = 0
    gefaellt = []
    bewertete_nrs = []
    for nr in auswahl["bfs_nr"]:
        antwort = st.session_state[f"bewertung_{nr}"]
        if antwort == "gefällt":
            bewertete_nrs.append(nr)
            gefaellt.append(1)
        elif antwort == "gefällt nicht":
            bewertete_nrs.append(nr)
            gefaellt.append(0)
    bewertet = auswahl.set_index("bfs_nr").loc[bewertete_nrs, MERKMALE]
    bewertet["gefaellt"] = gefaellt

    st.session_state["modell"] = train_model(bewertet)
    if st.session_state["modell"] is None:
        st.error(f"Das Modell braucht mindestens {MIN_BEWERTUNGEN} Bewertungen, davon mindestens ein «gefällt» "
                 "und ein «gefällt nicht».")

# ---------------------------------------------------------------------------
# Schritt 2: Ergebnis
# ---------------------------------------------------------------------------
st.header("Schritt 2: Dein Ergebnis")
heute = df[df["bfs_nr"] == eingaben["heute_nr"]].iloc[0]
modell = st.session_state.get("modell")

# Rangliste: mit Modell nach «passt zu dir», sonst nur nach Kosten
if modell is None:
    st.info("Noch kein Modell trainiert: Die Rangliste sortiert nur nach den Gesamtkosten.")
    rangliste = kandidaten.sort_values("gesamtkosten")
else:
    modell_lr, skalierer = modell
    kandidaten["passt"] = score_all(modell_lr, skalierer, kandidaten)
    # Zuerst nach «passt zu dir», bei Gleichstand die günstigere Gemeinde zuerst
    rangliste = kandidaten.sort_values(["passt", "gesamtkosten"], ascending=[False, True])

top = rangliste.head(ANZAHL_TOP)
top5_nrs = list(top["bfs_nr"].head(5))
beste = top.iloc[0]

# Kernaussage: Was bringt der beste Vorschlag gegenüber heute?
if beste["ersparnis"] > 0:
    st.subheader(f"{beste['name']} spart dir {chf(beste['ersparnis'])} CHF pro Jahr")
else:
    st.subheader(f"{beste['name']} kostet dich {chf(-beste['ersparnis'])} CHF mehr pro Jahr")
mehr_minuten = beste["pendel_min"] - heute["pendel_min"]
st.write(f"gegenüber {heute['name']}, mit {chf(beste['pendel_min'])} statt {chf(heute['pendel_min'])} "
         f"Minuten Arbeitsweg pro Strecke ({chf(mehr_minuten)} Min. Unterschied).")

# Vergleichstabelle heute gegen Vorschlag
vergleich = {
    "": ["Steuern pro Jahr", "Miete pro Jahr", "Pendeln pro Jahr", "Total pro Jahr", "Arbeitsweg (Min.)"],
    heute["name"] + " (heute)": [chf(heute["steuer_chf"]), chf(12 * heute["miete_chf"]),
                                 chf(heute["pendel_chf"]), chf(heute["gesamtkosten"]), chf(heute["pendel_min"])],
    beste["name"]: [chf(beste["steuer_chf"]), chf(12 * beste["miete_chf"]),
                    chf(beste["pendel_chf"]), chf(beste["gesamtkosten"]), chf(beste["pendel_min"])],
}
st.table(vergleich)

# Was das Modell gelernt hat
if modell is not None:
    st.subheader("Was dir wichtig ist (gelernt aus deinen Bewertungen)")
    st.pyplot(gewichte_chart(gewichte(modell[0])))

# Rangliste als Tabelle
st.subheader(f"Die {ANZAHL_TOP} besten Gemeinden für dich")
spalten = ["name", "kanton", "gesamtkosten", "ersparnis", "pendel_min", "geschaetzt"]
if modell is not None:
    spalten.append("passt")
tabelle = top[spalten].rename(columns={
    "name": "Gemeinde", "kanton": "Kanton", "gesamtkosten": "Total (CHF/Jahr)",
    "ersparnis": "Ersparnis ggü. heute (CHF)", "pendel_min": "Pendelzeit (Min.)",
    "geschaetzt": "Pendelzeit geschätzt", "passt": "Passt zu dir (%)",
})
st.dataframe(tabelle, hide_index=True)
st.caption("«Pendelzeit geschätzt» = aus der Luftlinie berechnet, nicht aus dem Fahrplan bzw. openrouteservice.")

st.subheader("Woraus setzen sich die Kosten zusammen?")
st.pyplot(kosten_chart(df, eingaben["heute_nr"], top5_nrs))

st.subheader("Tiefe Steuern, hohe Miete?")
st.pyplot(scatter_chart(df, eingaben["heute_nr"], top5_nrs))

# Karte mit st.map: Top 10 grün, heutiger Wohnort schwarz, Arbeitsort rot
st.subheader("Wo liegen deine Top 10?")
breiten = list(top["lat"]) + [heute["lat"], eingaben["ort"][0]]
laengen = list(top["lon"]) + [heute["lon"], eingaben["ort"][1]]
farben = ["#2ca02c"] * len(top) + ["#000000", "#d62728"]
karte = pd.DataFrame({"lat": breiten, "lon": laengen, "farbe": farben})
st.map(karte, latitude="lat", longitude="lon", color="farbe", size=1500)
st.caption("Grün: deine Top 10 · Schwarz: heutiger Wohnort · Rot: Arbeitsort")

st.caption(
    "Quellen und Annahmen: Steuern ESTV, Steuerjahr 2026, ohne Kirchensteuer. Mieten geschätzt aus "
    "BFS-Durchschnitten pro Kanton und Gemeindetyp. ÖV: Jahres-Strecken-Abo nach Tarif T650 bzw. GA. "
    "Auto: TCS-Kilometerkosten 2026. Details in data/raw/QUELLEN.md."
)
