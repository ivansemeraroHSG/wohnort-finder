"""
app.py – Streamlit-Oberfläche des Wohnort-Finders (Arbeitspaket 5).

Verantwortlich: <Name eintragen>

Starten (im Projektordner, mit aktivierter Umgebung):
    streamlit run app.py

Aktueller Stand: "Hello World" mit Fake-Daten und festen Gewichten.
"""

import streamlit as st

from api import commute_minutes, geocode
from data import fake_municipalities
from scoring import simple_score

st.set_page_config(page_title="Wohnort-Finder", page_icon="🏡", layout="wide")

# --- Startseite mit Problemstellung (Kriterium 1) ---
st.title("Wohnort-Finder: Welche Schweizer Gemeinde passt zu dir?")
st.write(
    "Steuern, Miete und Pendelzeit stehen auf verschiedenen Websites. "
    "Diese App bringt sie zusammen und lernt, welche Kombination dir am wichtigsten ist."
)

# --- Eingaben in der Seitenleiste (vorläufig: nur Gewichte) ---
st.sidebar.header("Was ist dir wichtig?")
w_steuer = st.sidebar.slider("Tiefe Steuern", 0, 100, 45)
w_pendel = st.sidebar.slider("Kurze Pendelzeit", 0, 100, 35)
w_miete = st.sidebar.slider("Tiefe Miete", 0, 100, 20)

# --- Daten laden (vorläufig Fake-Daten aus data.py) ---
df = fake_municipalities()

# --- Arbeitsort und Pendelzeiten (Arbeitspaket 2) ---
arbeitsort = st.sidebar.text_input("Arbeitsort (Adresse oder Ort)", "Zürich HB")
ort = geocode(arbeitsort)
if ort is None:
    st.sidebar.warning("Arbeitsort nicht gefunden. Die Pendelzeiten sind Testwerte.")
else:
    ziel_lat, ziel_lon, ort_name = ort
    # Den gefundenen Namen zeigen, damit man Verwechslungen sieht (Rapperswil SG/BE)
    st.sidebar.caption(f"Gefundener Arbeitsort: {ort_name}")

    # Streamlit führt bei jedem Klick die ganze Datei neu aus. Darum merken wir uns
    # in st.session_state, für welchen Arbeitsort die Pendelzeiten schon berechnet sind,
    # und rechnen nur neu, wenn sich der Arbeitsort ändert.
    if st.session_state.get("pendel_arbeitsort") != ort_name:
        balken = st.progress(0.0, text="Pendelzeiten werden berechnet …")
        st.session_state["pendel"] = commute_minutes(ziel_lat, ziel_lon, df, fortschritt=balken)
        st.session_state["pendel_arbeitsort"] = ort_name
        balken.empty()   # Balken ausblenden, wenn fertig
    pendel = st.session_state["pendel"]

    # Testwerte durch die berechneten Pendelzeiten ersetzen (verknüpft über bfs_nr)
    df = df.drop(columns=["pendel_min", "pendel_geschaetzt"]).merge(pendel, on="bfs_nr")

# --- Ranking berechnen und anzeigen ---
df["score"] = simple_score(
    df, {"steuer_chf": w_steuer, "pendel_min": w_pendel, "miete_chf": w_miete}
)
top = df.sort_values("score", ascending=False).head(10)

st.subheader("Top 10 (Testdaten)")
st.dataframe(
    top[["name", "kanton", "steuer_chf", "miete_chf", "pendel_min", "score"]],
    hide_index=True,
)
