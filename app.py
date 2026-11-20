"""
app.py – Streamlit-Oberfläche des Wohnort-Finders (Arbeitspaket 5).

Verantwortlich: Ivan
Task 5.3 (echte Daten, Wohnkosten) und 5.4 (Pendelkosten, ML): mit Claude erstellt, angepasst von Ivan

Starten (im Projektordner, mit aktivierter Umgebung):
    streamlit run app.py

Ablauf: Die Nutzerin gibt ihre Situation ein. Die App rechnet für jede Gemeinde die
Gesamtkosten (Steuern + Miete + Pendeln) und vergleicht sie mit dem heutigen Wohnort.
Im Tab «Was ist dir deine Zeit wert?» lernt das ML-Modell aus Paarvergleichen, wie viel
ihr eine Minute Pendelzeit wert ist, und die Rangliste wird persönlich.
"""

import random

import pandas as pd
import streamlit as st

from api import PROFIL_AUTO, PROFIL_VELO, commute_minutes, geocode, pendel_optionen, route_matrix
from data import HAUSHALTE, get_municipalities, get_rent, get_tax
from model import MIN_VERGLEICHE, fit_preferences, make_pairs, persoenliche_kosten, select_for_rating
from scoring import wohnkosten

st.set_page_config(page_title="Wohnort-Finder", page_icon="🏡", layout="wide")

HAUSHALT_TEXT = {
    "ledig": "Ledig, keine Kinder",
    "verheiratet": "Verheiratet, keine Kinder",
    "verheiratet_2_kinder": "Verheiratet, 2 Kinder",
}
VM_TEXT = {"oev": "🚆 ÖV", "auto": "🚗 Auto", "velo": "🚲 Velo"}
STANDARD_WOHNORT = "Zürich"
ANZAHL_TOP = 10
ANZAHL_LIVE_KANDIDATEN = 30   # pro Runde so viele geschätzte Gemeinden live nachfragen
MAX_RUNDEN = 3                # danach aufhören, damit die App nicht zu lange lädt


def chf(betrag):
    """Betrag als Text mit Schweizer Tausendertrennzeichen, z. B. 11'400."""
    return f"{betrag:,.0f}".replace(",", "'")


@st.cache_data
def gemeinden_laden():
    """Gemeinden nur einmal pro Sitzung aus der Datenbank lesen."""
    return get_municipalities()


def pendeln_laden(ziel_lat, ziel_lon, ort_name, gemeinden):
    """ÖV-, Auto- und Velodaten zum Arbeitsort, nur neu holen, wenn er sich ändert."""
    # Streamlit führt bei jedem Klick die ganze Datei neu aus; die API-Ergebnisse
    # merken wir uns darum in st.session_state, pro Arbeitsort.
    if st.session_state.get("pendel_arbeitsort") != ort_name:
        balken = st.progress(0.0, text="Pendelzeiten werden berechnet …")
        oev = commute_minutes(ziel_lat, ziel_lon, gemeinden, fortschritt=balken)
        auto = route_matrix(ziel_lat, ziel_lon, gemeinden, PROFIL_AUTO)
        velo = route_matrix(ziel_lat, ziel_lon, gemeinden, PROFIL_VELO)
        st.session_state["pendel_oev"] = oev
        st.session_state["pendel_routen"] = auto.merge(velo, on="bfs_nr")
        st.session_state["pendel_arbeitsort"] = ort_name
        balken.empty()
    return st.session_state["pendel_oev"], st.session_state["pendel_routen"]


# --- Startseite mit Problemstellung (Kriterium 1) ---
st.title("Wohnort-Finder: Wo bleibt dir am meisten Geld?")
st.write(
    "Tiefe Steuern heisst nicht automatisch günstig wohnen: In Steuerparadiesen sind "
    "die Mieten oft so hoch, dass sich ein Umzug erst ab einem hohen Einkommen lohnt. "
    "Die App rechnet für deine Situation aus, was dich jede Gemeinde pro Jahr kostet "
    "(Steuern + Miete + Pendeln), zeigt das günstigste Verkehrsmittel und lernt, "
    "wie viel dir deine Zeit wert ist."
)

gemeinden = gemeinden_laden()
namen = dict(zip(gemeinden["bfs_nr"], gemeinden["name"]))

# --- Eingaben in der Seitenleiste (siehe Handbuch, Teil 0) ---
st.sidebar.header("Meine Situation")
einkommen = st.sidebar.number_input(
    "Bruttoeinkommen pro Jahr (CHF)", min_value=50_000, max_value=300_000,
    value=100_000, step=5_000, help="Für die Einkommenssteuer (Bund, Kanton, Gemeinde)",
)
haushalt = st.sidebar.selectbox("Haushalt", HAUSHALTE, format_func=lambda h: HAUSHALT_TEXT[h])
zimmer = st.sidebar.slider("Zimmer", 1, 6, 3, help="6 bedeutet 6 und mehr Zimmer")
heute_nr = st.sidebar.selectbox(
    "Heutiger Wohnort", list(namen), index=list(namen.values()).index(STANDARD_WOHNORT),
    format_func=lambda nr: namen[nr], help="Damit die App zeigt, wie viel du gegenüber heute sparst",
)
arbeitsort = st.sidebar.text_input("Arbeitsort (Adresse oder Ort)", "Zürich HB")

st.sidebar.header("Pendeln")
buerotage = st.sidebar.slider("Bürotage pro Woche", 1, 5, 5, help="Homeoffice-Tage kosten nichts")
verkehrsmittel = st.sidebar.multiselect(
    "Verkehrsmittel", list(VM_TEXT), default=list(VM_TEXT), format_func=lambda vm: VM_TEXT[vm],
)
hat_auto = st.sidebar.toggle(
    "Ich habe schon ein Auto",
    help="Ja: nur Benzin, Unterhalt usw. (28 Rp./km). Nein: inkl. Kauf und Versicherung (74 Rp./km, TCS)",
)
parkplatz_chf = st.sidebar.number_input("Parkplatz am Arbeitsort (CHF pro Monat)", 0, 1_000, 0, step=10)
hat_ga = st.sidebar.toggle("Ich habe schon ein GA", help="Dann kostet der ÖV fürs Pendeln nichts zusätzlich")
max_pendel = st.sidebar.slider("Maximale Pendelzeit pro Weg (Min.)", 10, 90, 45, step=5)

if not verkehrsmittel:
    st.warning("Wähle mindestens ein Verkehrsmittel aus.")
    st.stop()
ort = geocode(arbeitsort)
if ort is None:
    st.warning("Arbeitsort nicht gefunden. Bitte eine Adresse oder einen Ort in der Schweiz eingeben.")
    st.stop()
ziel_lat, ziel_lon, ort_name = ort
st.sidebar.caption(f"Gefundener Arbeitsort: {ort_name}")

# --- Gesamtkosten aller Gemeinden ---
oev, routen = pendeln_laden(ziel_lat, ziel_lon, ort_name, gemeinden)
zeitwert = st.session_state.get("zeitwert")   # vom ML-Modell gelernt, sonst None
eingaben = {
    "verkehrsmittel": verkehrsmittel, "buerotage": buerotage, "hat_auto": hat_auto,
    "parkplatz_chf": parkplatz_chf, "hat_ga": hat_ga, "max_pendel_min": max_pendel,
    "zeitwert": zeitwert,
}
df = gemeinden.merge(get_tax(einkommen, haushalt), on="bfs_nr").merge(get_rent(zimmer), on="bfs_nr")
df = df.merge(pendel_optionen(gemeinden, oev, routen, eingaben), on="bfs_nr")
df["gesamtkosten"] = wohnkosten(df) + df["pendel_chf"]

heute = df[df["bfs_nr"] == heute_nr].iloc[0]
df["ersparnis"] = heute["gesamtkosten"] - df["gesamtkosten"]
df["mehr_pendeln"] = df["pendel_min"] - heute["pendel_min"]
kandidaten = df[(df["bfs_nr"] != heute_nr) & (df["pendel_min"] <= max_pendel)].copy()

# --- Heutiger Wohnort ---
st.subheader(f"Heute in {heute['name']}: {chf(heute['gesamtkosten'])} CHF pro Jahr")
spalte1, spalte2, spalte3 = st.columns(3)
spalte1.metric("Steuern", f"{chf(heute['steuer_chf'])} CHF")
spalte2.metric("Miete (12 Monate)", f"{chf(12 * heute['miete_chf'])} CHF")
spalte3.metric(
    f"Pendeln ({VM_TEXT[heute['bestes_vm']]}, {heute['pendel_min']:.0f} Min.)",
    f"{chf(heute['pendel_chf'])} CHF",
)

tab_ergebnis, tab_vorlieben = st.tabs(["Ergebnis", "Was ist dir deine Zeit wert?"])

# --- Tab 2: Paarvergleiche für das ML-Modell (Arbeitspaket 3) ---
with tab_vorlieben:
    st.write(
        "Wähle bei jedem Paar die Gemeinde, in der du lieber wohnen würdest. Eine ist günstiger, "
        "die andere näher. Aus deinen Antworten lernt die App, wie viel dir Pendelzeit wert ist."
    )
    # Paare nur einmal bilden; die Antworten speichern die Werte, die die Nutzerin gesehen hat
    if "paare" not in st.session_state:
        auswahl = kandidaten[kandidaten["bfs_nr"].isin(select_for_rating(kandidaten))]
        paare = make_pairs(auswahl)
        random.shuffle(paare)
        st.session_state["paare"] = paare
        st.session_state["antworten"] = []
    paare = st.session_state["paare"]
    antworten = st.session_state["antworten"]
    nach_nr = df.set_index("bfs_nr")

    if len(antworten) < len(paare):
        a, b = paare[len(antworten)]
        st.caption(f"Vergleich {len(antworten) + 1} von {len(paare)}")
        links, rechts = st.columns(2)
        for spalte, nr, buchstabe in [(links, a, "A"), (rechts, b, "B")]:
            g = nach_nr.loc[nr]
            with spalte:
                st.markdown(f"#### {buchstabe}: {g['name']} ({g['kanton']})")
                st.metric("Gesamtkosten pro Jahr", f"{chf(g['gesamtkosten'])} CHF")
                st.metric(f"Pendelzeit pro Weg ({VM_TEXT[g['bestes_vm']]})", f"{g['pendel_min']:.0f} Min.")
                st.caption(f"Steuern {chf(g['steuer_chf'])} CHF, Miete {chf(g['miete_chf'])} CHF/Monat")
                if st.button(f"Lieber {g['name']}", key=f"wahl_{buchstabe}", use_container_width=True):
                    ga, gb = nach_nr.loc[a], nach_nr.loc[b]
                    antworten.append({
                        "gesamtkosten_a": ga["gesamtkosten"], "pendel_min_a": ga["pendel_min"],
                        "gesamtkosten_b": gb["gesamtkosten"], "pendel_min_b": gb["pendel_min"],
                        "wahl_a": int(buchstabe == "A"),
                    })
                    modell = fit_preferences(pd.DataFrame(antworten))
                    st.session_state["zeitwert"] = modell["chf_pro_minute"] if modell else None
                    st.rerun()
    else:
        st.success("Fertig! Dein Ergebnis siehst du im Tab «Ergebnis».")

    if len(antworten) < MIN_VERGLEICHE:
        st.info(f"Nach {MIN_VERGLEICHE} Antworten kann das Modell deinen Zeitwert schätzen.")
    elif zeitwert is None:
        st.warning("Deine Antworten widersprechen sich. Die Rangliste rechnet darum nur mit den Kosten.")
    else:
        st.metric("10 Minuten weniger Pendeln (pro Weg) sind dir pro Jahr wert", f"{chf(10 * zeitwert)} CHF")
    if antworten and st.button("Von vorne beginnen"):
        for schluessel in ["paare", "antworten", "zeitwert"]:
            st.session_state.pop(schluessel, None)
        st.rerun()

# --- Tab 1: Ergebnis ---
with tab_ergebnis:
    if zeitwert is None:
        kandidaten["rang"] = kandidaten["gesamtkosten"]
        st.caption("Rangliste nach Gesamtkosten. Beantworte die Vergleiche im zweiten Tab, "
                   "damit die App auch deine Pendelzeit gewichtet.")
    else:
        kandidaten["rang"] = persoenliche_kosten({"chf_pro_minute": zeitwert}, kandidaten)
        st.caption(f"Persönliche Rangliste: Gesamtkosten plus {chf(zeitwert)} CHF pro Minute Pendelzeit.")
    top = kandidaten.sort_values("rang").head(ANZAHL_TOP)

    if top.empty:
        st.info("Keine Gemeinde innerhalb dieser Pendelzeit. Erhöhe die maximale Pendelzeit.")
    else:
        beste = top.iloc[0]
        satz = f"Am besten passt **{beste['name']}**: "
        if beste["ersparnis"] > 0:
            satz += f"du sparst **{chf(beste['ersparnis'])} CHF pro Jahr**"
        else:
            satz += f"es kostet dich {chf(-beste['ersparnis'])} CHF mehr pro Jahr"
        minuten = int(beste["mehr_pendeln"])
        satz += f" und pendelst {abs(minuten)} Min. {'länger' if minuten > 0 else 'weniger'}"
        satz += f", am besten mit {VM_TEXT[beste['bestes_vm']]}."
        st.success(satz)

        anzeige = top.assign(vm=top["bestes_vm"].map(VM_TEXT))
        spalten = {
            "name": "Gemeinde", "kanton": "Kanton", "gesamtkosten": "Gesamtkosten CHF/Jahr",
            "ersparnis": "Ersparnis CHF/Jahr", "steuer_chf": "Steuern CHF/Jahr",
            "miete_chf": "Miete CHF/Monat", "pendel_chf": "Pendeln CHF/Jahr",
            "vm": "Verkehrsmittel", "pendel_min": "Pendelzeit Min.",
        }
        anzeige = anzeige[list(spalten)].rename(columns=spalten)
        zahlen = [s for s in anzeige.columns if s not in ("Gemeinde", "Kanton", "Verkehrsmittel")]
        anzeige[zahlen] = anzeige[zahlen].round().astype("Int64")
        st.dataframe(anzeige, hide_index=True)

    st.caption(
        "Steuern: ESTV, Steuerjahr 2026, ohne Kirchensteuer. Mieten: Schätzung aus BFS-Durchschnitten. "
        "ÖV: Jahres-Strecken-Abo (Tarif T650), höchstens GA. Auto: TCS-Kilometerkosten plus Parkplatz. "
        "Pendelzeiten zum Teil geschätzt; Autozeiten ohne Stau."
    )
