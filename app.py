"""
app.py – Streamlit-Oberfläche des Wohnort-Finders (Arbeitspaket 5).

Verantwortlich: <Name eintragen>

Starten (im Projektordner, mit aktivierter Umgebung):
    streamlit run app.py

Aktueller Stand: "Hello World" mit Fake-Daten und festen Gewichten.
"""

import streamlit as st

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
