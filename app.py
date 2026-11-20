"""
app.py – Streamlit-Oberfläche des Wohnort-Finders (Arbeitspaket 5).

Verantwortlich: <Name eintragen>
Umstellung auf echte Daten und Wohnkosten (Task 5.3): mit Claude erstellt, angepasst von Ivan

Starten (im Projektordner, mit aktivierter Umgebung):
    streamlit run app.py

Aktueller Stand (MVP v0.2): Wohnkosten (Steuern + Miete) aller Gemeinden für die
eigene Situation, verglichen mit dem heutigen Wohnort, gefiltert nach Pendelzeit.
"""

import streamlit as st

from api import commute_minutes, geocode
from data import HAUSHALTE, get_municipalities, get_rent, get_tax
from scoring import wohnkosten

st.set_page_config(page_title="Wohnort-Finder", page_icon="🏡", layout="wide")

# Beschriftungen für die Auswahl in der Seitenleiste (Wert in der Datenbank -> Anzeige)
HAUSHALT_TEXT = {
    "ledig": "Ledig, keine Kinder",
    "verheiratet": "Verheiratet, keine Kinder",
    "verheiratet_2_kinder": "Verheiratet, 2 Kinder",
}
STANDARD_WOHNORT = "Zürich"
ANZAHL_TOP = 10


def chf(betrag):
    """Betrag als Text mit Schweizer Tausendertrennzeichen, z. B. 11'400."""
    return f"{betrag:,.0f}".replace(",", "'")


# --- Startseite mit Problemstellung (Kriterium 1) ---
st.title("Wohnort-Finder: Wo bleibt dir am meisten Geld?")
st.write(
    "Tiefe Steuern heisst nicht automatisch günstig wohnen: In Steuerparadiesen sind "
    "die Mieten oft so hoch, dass sich ein Umzug erst ab einem hohen Einkommen lohnt. "
    "Die App rechnet für deine Situation aus, was dich jede Gemeinde pro Jahr kostet "
    "(Steuern + Miete), und zeigt, wo du gegenüber heute sparst und wie lange du dafür pendelst."
)

gemeinden = get_municipalities()

# --- Eingaben in der Seitenleiste ---
st.sidebar.header("Deine Situation")
einkommen = st.sidebar.number_input(
    "Bruttoeinkommen pro Jahr (CHF)", min_value=50_000, max_value=300_000,
    value=100_000, step=5_000,
)
haushalt = st.sidebar.selectbox(
    "Haushalt", HAUSHALTE, format_func=lambda h: HAUSHALT_TEXT[h],
)
zimmer = st.sidebar.slider("Zimmer", 1, 6, 3, help="6 bedeutet 6 und mehr Zimmer")
namen = dict(zip(gemeinden["bfs_nr"], gemeinden["name"]))
heute_nr = st.sidebar.selectbox(
    "Heutiger Wohnort", list(namen),
    index=list(namen.values()).index(STANDARD_WOHNORT),
    format_func=lambda nr: namen[nr],
)
arbeitsort = st.sidebar.text_input("Arbeitsort (Adresse oder Ort)", "Zürich HB")
max_pendel = st.sidebar.slider("Maximale Pendelzeit (Min., ÖV)", 10, 90, 45, step=5)

# --- Wohnkosten aller Gemeinden (Daten aus Arbeitspaket 1, verknüpft über bfs_nr) ---
df = gemeinden.merge(get_tax(einkommen, haushalt), on="bfs_nr")
df = df.merge(get_rent(zimmer), on="bfs_nr")
df["wohnkosten"] = wohnkosten(df)

# --- Arbeitsort und Pendelzeiten (Arbeitspaket 2) ---
ort = geocode(arbeitsort)
if ort is None:
    st.sidebar.warning("Arbeitsort nicht gefunden. Die Pendelzeit wird nicht berücksichtigt.")
else:
    ziel_lat, ziel_lon, ort_name = ort
    # Den gefundenen Namen zeigen, damit man Verwechslungen sieht (Rapperswil SG/BE)
    st.sidebar.caption(f"Gefundener Arbeitsort: {ort_name}")

    # Streamlit führt bei jedem Klick die ganze Datei neu aus. Darum merken wir uns
    # in st.session_state, für welchen Arbeitsort die Pendelzeiten schon berechnet sind,
    # und rechnen nur neu, wenn sich der Arbeitsort ändert.
    if st.session_state.get("pendel_arbeitsort") != ort_name:
        balken = st.progress(0.0, text="Pendelzeiten werden berechnet …")
        st.session_state["pendel"] = commute_minutes(ziel_lat, ziel_lon, gemeinden, fortschritt=balken)
        st.session_state["pendel_arbeitsort"] = ort_name
        balken.empty()   # Balken ausblenden, wenn fertig
    df = df.merge(st.session_state["pendel"], on="bfs_nr")

# --- Vergleich mit dem heutigen Wohnort ---
heute = df[df["bfs_nr"] == heute_nr].iloc[0]
df["ersparnis"] = heute["wohnkosten"] - df["wohnkosten"]

kandidaten = df[df["bfs_nr"] != heute_nr]
if "pendel_min" in df.columns:
    df["mehr_pendeln"] = df["pendel_min"] - heute["pendel_min"]
    kandidaten = df[(df["bfs_nr"] != heute_nr) & (df["pendel_min"] <= max_pendel)]
top = kandidaten.sort_values("wohnkosten").head(ANZAHL_TOP)

st.subheader(f"Heute in {heute['name']}: {chf(heute['wohnkosten'])} CHF pro Jahr")
st.caption(f"Steuern {chf(heute['steuer_chf'])} CHF + 12 × Miete {chf(heute['miete_chf'])} CHF")

if top.empty:
    st.info("Keine Gemeinde innerhalb dieser Pendelzeit. Erhöhe die maximale Pendelzeit.")
else:
    beste = top.iloc[0]
    if beste["ersparnis"] <= 0:
        st.success(f"{heute['name']} ist bereits einer der günstigsten Orte für deine Situation.")
    else:
        satz = f"In **{beste['name']}** sparst du **{chf(beste['ersparnis'])} CHF pro Jahr**"
        if "mehr_pendeln" in beste:
            minuten = int(beste["mehr_pendeln"])
            if minuten > 0:
                satz += f" und pendelst {minuten} Min. länger"
            else:
                satz += f" und pendelst {abs(minuten)} Min. weniger"
        st.success(satz + ".")

    st.subheader(f"Die {ANZAHL_TOP} günstigsten Gemeinden für dich")
    spalten = {
        "name": "Gemeinde",
        "kanton": "Kanton",
        "wohnkosten": "Wohnkosten CHF/Jahr",
        "ersparnis": "Ersparnis CHF/Jahr",
        "steuer_chf": "Steuern CHF/Jahr",
        "miete_chf": "Miete CHF/Monat",
        "pendel_min": "Pendelzeit Min.",
        "mehr_pendeln": "Pendeln vs. heute Min.",
    }
    anzeige = top[[s for s in spalten if s in top.columns]]
    # Ganze Franken und Minuten reichen, Nachkommastellen lenken nur ab
    anzeige = anzeige.astype({s: "Int64" for s in anzeige.columns if s not in ("name", "kanton")})
    st.dataframe(anzeige.rename(columns=spalten), hide_index=True)

st.caption(
    "Steuern: ESTV, Steuerjahr 2026, Einkommenssteuer ohne Kirchensteuer. "
    "Mieten: Schätzung aus BFS-Durchschnitten pro Kanton und Gemeindetyp (bestehende Mietverhältnisse). "
    "Pendelzeiten mit dem ÖV: für die nächsten Gemeinden echte Verbindungen, sonst geschätzt."
)
