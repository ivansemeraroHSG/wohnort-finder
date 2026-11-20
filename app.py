"""
app.py – Streamlit-Oberfläche des Wohnort-Finders (Arbeitspaket 5).

Verantwortlich: Ivan
Task 5.3–5.5 (Daten, ML, geführter Ablauf, Grafiken): mit Claude erstellt, angepasst von Ivan
Task 2.8 (Live-ÖV für die günstigsten Kandidaten): mit Claude erstellt, angepasst von Gregor Weber

Starten (im Projektordner, mit aktivierter Umgebung):
    streamlit run app.py

Ablauf in vier Schritten:
1. Deine Situation   (Einkommen, Haushalt, Zimmer, Wohnort heute, Arbeitsort)
2. Dein Arbeitsweg   (Bürotage, Verkehrsmittel, Auto, Parkplatz, GA, max. Pendelzeit)
3. Was ist dir Zeit wert?  (Paarvergleiche, daraus lernt das ML-Modell)
4. Dein Ergebnis     (Vergleich mit heute, Grafiken, Karte, Rangliste)

Das Aussehen (Farben, Schriften) steht in .streamlit/config.toml.
"""

import random

import pandas as pd
import streamlit as st

from api import PROFIL_AUTO, PROFIL_VELO, commute_minutes, geocode, pendel_optionen, route_matrix
from charts import kosten_balken, lade_grenzen, map_chart, scatter_chart, tradeoff_chart, zeitwert_chart
from data import HAUSHALTE, OEV_ABOS, get_municipalities, get_rent, get_tax
from model import MIN_VERGLEICHE, fit_preferences, make_pairs, persoenliche_kosten, select_for_rating
from scoring import wohnkosten

st.set_page_config(page_title="Wohnort-Finder", page_icon=":material/home_work:", layout="centered")

SCHRITTE = ["Situation", "Arbeitsweg", "Zeitwert", "Ergebnis"]
HAUSHALT_TEXT = {
    "ledig": "Ledig, keine Kinder",
    "verheiratet": "Verheiratet, keine Kinder",
    "verheiratet_2_kinder": "Verheiratet, 2 Kinder",
}
VM_NAME = {"oev": "ÖV", "auto": "Auto", "velo": "Velo"}
VM_ICON = {"oev": ":material/train:", "auto": ":material/directions_car:", "velo": ":material/pedal_bike:"}
ANZAHL_TOP = 10
MAX_RUNDEN = 3                # danach aufhören, damit die App nicht zu lange lädt
# Standardwerte: damit die App sofort ein sinnvolles Ergebnis zeigt (Zürich = BFS 261)
STANDARD = {
    "einkommen": 100_000, "haushalt": "ledig", "zimmer": 3, "heute_nr": 261,
    "arbeitsort": "Zürich HB", "buerotage": 5, "verkehrsmittel": ["oev", "auto", "velo"],
    "hat_auto": False, "parkplatz_chf": 0, "oev_abo": "guenstigstes", "max_pendel": 45,
    "lieblings_vm": None, "toleranz_min": 0,
}
ZEITWERT_MAX_10MIN = 20_000   # Obergrenze des Reglers: CHF pro Jahr für 10 Min. pro Strecke

# Zahlen in Tabellen und Kennzahlen mit gleich breiten Ziffern, damit sie sauber untereinander stehen
st.html("""<style>
[data-testid="stMetricValue"], [data-testid="stTable"] td, .zahl { font-variant-numeric: tabular-nums; }
.schritte { display: flex; justify-content: center; align-items: center; gap: 0.75rem; margin: 0.5rem 0 1.5rem; }
.schritt { display: flex; align-items: center; gap: 0.4rem; color: #8a857a; font-size: 0.95rem; }
.schritt .nr { width: 1.6rem; height: 1.6rem; border-radius: 50%; border: 1.5px solid #c9c2b3;
               display: inline-flex; align-items: center; justify-content: center; font-size: 0.85rem; }
.schritt.aktiv { color: #22211e; font-weight: 600; }
.schritt.aktiv .nr { border-color: #2f6b4f; background: #2f6b4f; color: #f7f4ee; }
.schritt.fertig { color: #2f6b4f; }
.schritt.fertig .nr { border-color: #2f6b4f; }
.linie { width: 2.5rem; height: 1.5px; background: #d9d2c3; }
</style>""")


def chf(betrag):
    """Betrag als Text mit Schweizer Tausendertrennzeichen, z. B. 11'400."""
    return f"{betrag:,.0f}".replace(",", "'")


def mit_vorzeichen(betrag):
    """Betrag mit Vorzeichen, z. B. +1'200 oder -850 (Streamlit erkennt so auch die Pfeilrichtung)."""
    return ("+" if betrag > 0 else "-" if betrag < 0 else "±") + chf(abs(betrag))


@st.cache_data
def gemeinden_laden():
    """Gemeinden nur einmal aus der Datenbank lesen."""
    return get_municipalities()


@st.cache_data
def grenzen_laden():
    """Gemeindegrenzen für die Karte nur einmal laden."""
    return lade_grenzen()


def gehe_zu(schritt):
    """Wechselt zu einem Schritt und lädt die Seite neu."""
    st.session_state["schritt"] = schritt
    st.rerun()


def fortschritt_anzeigen(aktuell):
    """Zeigt zentriert die vier Schritte: erledigte grün mit Häkchen, der aktuelle gefüllt."""
    teile = []
    for nr, titel in enumerate(SCHRITTE, start=1):
        if nr < aktuell:
            teile.append(f'<span class="schritt fertig"><span class="nr">&#10003;</span>{titel}</span>')
        elif nr == aktuell:
            teile.append(f'<span class="schritt aktiv"><span class="nr">{nr}</span>{titel}</span>')
        else:
            teile.append(f'<span class="schritt"><span class="nr">{nr}</span>{titel}</span>')
    st.html('<div class="schritte">' + '<span class="linie"></span>'.join(teile) + "</div>")


def pendeln_laden(ziel_lat, ziel_lon, ort_name, gemeinden):
    """ÖV-, Auto- und Velodaten zum Arbeitsort; nur neu holen, wenn er sich ändert."""
    # Streamlit führt bei jedem Klick die ganze Datei neu aus; die API-Ergebnisse
    # merken wir uns darum in st.session_state, pro Arbeitsort.
    if st.session_state.get("pendel_arbeitsort") != ort_name:
        balken = st.progress(0.0, text="Pendelzeiten zu deinem Arbeitsort werden berechnet …")
        oev = commute_minutes(ziel_lat, ziel_lon, gemeinden, fortschritt=balken)
        auto = route_matrix(ziel_lat, ziel_lon, gemeinden, PROFIL_AUTO)
        velo = route_matrix(ziel_lat, ziel_lon, gemeinden, PROFIL_VELO)
        balken.empty()
        st.session_state["pendel_oev"] = oev
        st.session_state["pendel_routen"] = auto.merge(velo, on="bfs_nr")
        st.session_state["pendel_arbeitsort"] = ort_name
        st.session_state["live_versucht"] = set()   # neuer Arbeitsort: noch nichts nachgefragt
    return st.session_state["pendel_oev"], st.session_state["pendel_routen"]


def kosten_aller_gemeinden(wohnen, oev, routen, optionen):
    """Wohnkosten plus Pendelkosten (bestes Verkehrsmittel) für alle Gemeinden."""
    df = wohnen.merge(pendel_optionen(wohnen, oev, routen, optionen), on="bfs_nr")
    df["gesamtkosten"] = wohnkosten(df) + df["pendel_chf"]
    return df


def rangliste(df, e, zeitwert):
    """Gemeinden innerhalb der max. Pendelzeit, die besten zuerst."""
    kandidaten = df[(df["bfs_nr"] != e["heute_nr"]) & (df["pendel_min"] <= e["max_pendel"])].copy()
    if zeitwert is None:
        kandidaten["rang"] = kandidaten["gesamtkosten"]
    else:
        kandidaten["rang"] = persoenliche_kosten({"chf_pro_minute": zeitwert}, kandidaten)
    return kandidaten.sort_values("rang")


def gesamtkosten_berechnen(e, gemeinden, zeitwert=None, nachfragen=False):
    """Gesamtkosten (Steuern + Miete + Pendeln) aller Gemeinden und der Vergleich mit heute.

    zeitwert: CHF pro Minute; None = nur Franken (so bleiben die Zahlen während der Vergleiche fix).
    nachfragen: geschätzte ÖV-Zeiten der besten Kandidaten live nachfragen (nur im Ergebnis).
    """
    ziel_lat, ziel_lon, ort_name = e["ort"]
    oev, routen = pendeln_laden(ziel_lat, ziel_lon, ort_name, gemeinden)
    optionen = {
        "verkehrsmittel": e["verkehrsmittel"], "buerotage": e["buerotage"], "hat_auto": e["hat_auto"],
        "parkplatz_chf": e["parkplatz_chf"], "oev_abo": e["oev_abo"], "max_pendel_min": e["max_pendel"],
        "lieblings_vm": e["lieblings_vm"], "toleranz_min": e["toleranz_min"], "zeitwert": zeitwert,
    }
    wohnen = gemeinden.merge(get_tax(e["einkommen"], e["haushalt"]), on="bfs_nr")
    wohnen = wohnen.merge(get_rent(e["zimmer"]), on="bfs_nr")
    df = kosten_aller_gemeinden(wohnen, oev, routen, optionen)

    # Task 2.8 (Gregor Weber): Geschätzte ÖV-Zeiten können zu optimistisch sein, und dann
    # rutscht eine schlecht erschlossene Gemeinde nach oben. Darum die besten Kandidaten,
    # deren ÖV-Zeit noch geschätzt ist, live nachfragen und neu rechnen.
    if nachfragen and "oev" in e["verkehrsmittel"]:
        for _ in range(MAX_RUNDEN):
            vorne = rangliste(df, e, zeitwert)
            # Jede Gemeinde nur einmal nachfragen: Schlägt die Abfrage fehl, nicht bei jedem Klick erneut
            versucht = st.session_state.get("live_versucht", set())
            # Nur die Gemeinden, die in der Rangliste sichtbar sind (max. 10 Abfragen pro Runde)
            top = vorne.head(ANZAHL_TOP)
            geschaetzt = top[top["oev_geschaetzt"] == True]["bfs_nr"]   # noqa: E712
            offen = [int(nr) for nr in geschaetzt if int(nr) not in versucht]
            if not offen:
                break
            st.session_state["live_versucht"] = versucht | set(offen)
            balken = st.progress(0.0, text="Echte ÖV-Verbindungen für die günstigsten Gemeinden …")
            neu = commute_minutes(ziel_lat, ziel_lon, gemeinden, fortschritt=balken, zusaetzlich=offen,
                                  max_abfragen=0)
            balken.empty()
            # Keine einzige neue echte Zeit (z. B. API gestört): nicht weiter versuchen
            if neu["pendel_geschaetzt"].sum() == oev["pendel_geschaetzt"].sum():
                break
            oev = neu
            st.session_state["pendel_oev"] = neu
            df = kosten_aller_gemeinden(wohnen, oev, routen, optionen)

    heute = df[df["bfs_nr"] == e["heute_nr"]].iloc[0]
    df["ersparnis"] = heute["gesamtkosten"] - df["gesamtkosten"]
    df["mehr_pendeln"] = df["pendel_min"] - heute["pendel_min"]
    return df, heute


def ml_zuruecksetzen():
    """Vergleiche und gelernten Zeitwert löschen (z. B. nach geänderten Eingaben)."""
    for schluessel in ["paare", "antworten", "zeitwert", "zeitwert_10min"]:
        st.session_state.pop(schluessel, None)


def aktueller_zeitwert():
    """CHF pro Jahr für 1 Minute pro Strecke: vom Regler in Schritt 4, sonst vom Modell, sonst None."""
    if "zeitwert_10min" in st.session_state:
        wert = st.session_state["zeitwert_10min"] / 10
        return wert if wert > 0 else None
    return st.session_state.get("zeitwert")


gemeinden = gemeinden_laden()
namen = dict(zip(gemeinden["bfs_nr"], gemeinden["name"]))
if "eingaben" not in st.session_state:
    st.session_state["eingaben"] = dict(STANDARD)
    st.session_state["schritt"] = 1
e = st.session_state["eingaben"]
schritt = st.session_state["schritt"]

# --- Kopf: Problemstellung (Kriterium 1) und Fortschritt ---
st.title("Wohnort-Finder")
st.markdown(
    "Wo bleibt dir am Ende des Jahres am meisten Geld? Tiefe Steuern heisst nicht automatisch "
    "günstig wohnen: In Steuerparadiesen sind die Mieten oft so hoch, dass sich ein Umzug erst ab "
    "einem hohen Einkommen lohnt. Wir rechnen für deine Situation aus, was dich jede der 2'110 "
    "Schweizer Gemeinden pro Jahr kostet, mit Steuern, Miete und Arbeitsweg."
)
fortschritt_anzeigen(schritt)

# --- Schritt 1: Situation ---
if schritt == 1:
    st.header("Deine Situation")
    with st.form("situation", border=False):
        links, rechts = st.columns(2)
        einkommen = links.number_input("Bruttoeinkommen pro Jahr (CHF)", 50_000, 300_000, e["einkommen"],
                                       step=5_000, help="Für die Einkommenssteuer von Bund, Kanton und Gemeinde")
        haushalt = rechts.selectbox("Haushalt", HAUSHALTE, index=HAUSHALTE.index(e["haushalt"]),
                                    format_func=lambda h: HAUSHALT_TEXT[h])
        zimmer = links.slider("Zimmer", 1, 6, e["zimmer"], help="6 bedeutet 6 und mehr Zimmer")
        nummern = list(namen)
        wohnort = rechts.selectbox("Wo wohnst du heute?", nummern, index=nummern.index(e["heute_nr"]),
                                   format_func=lambda nr: namen[nr],
                                   help="Name eintippen, um zu suchen. Damit zeigen wir, was du gegenüber heute sparst.")
        arbeitsort = st.text_input("Wo arbeitest du?", e["arbeitsort"], help="Adresse oder Ort in der Schweiz")
        weiter = st.form_submit_button("Weiter zum Arbeitsweg", type="primary")
    if weiter:
        ort = geocode(arbeitsort)
        if ort is None:
            st.error("Diesen Arbeitsort finden wir nicht. Gib eine Adresse oder einen Ort in der Schweiz ein.")
        else:
            neu = {"einkommen": einkommen, "haushalt": haushalt, "zimmer": zimmer,
                   "heute_nr": wohnort, "arbeitsort": arbeitsort, "ort": ort}
            if any(e.get(k) != v for k, v in neu.items()):
                ml_zuruecksetzen()
            e.update(neu)
            gehe_zu(2)

# --- Schritt 2: Arbeitsweg ---
elif schritt == 2:
    st.header("Dein Arbeitsweg")
    st.caption(f"Arbeitsort: {e['ort'][2]}")
    with st.form("arbeitsweg", border=False):
        verkehrsmittel = st.multiselect("Welche Verkehrsmittel kommen für dich in Frage?", list(VM_NAME),
                                        default=e["verkehrsmittel"], format_func=lambda vm: VM_NAME[vm])
        links, rechts = st.columns(2)
        buerotage = links.slider("Bürotage pro Woche", 1, 5, e["buerotage"],
                                 help="An Homeoffice-Tagen fallen keine Fahrkosten an")
        max_pendel = rechts.slider("Maximale Pendelzeit pro Strecke (Min.)", 10, 90, e["max_pendel"], step=5,
                                   help="Von Tür zu Tür, beim ÖV inklusive Fusswege zur und von der Haltestelle")

        st.markdown("**ÖV**")
        abos = list(OEV_ABOS)
        oev_abo = st.selectbox("Abo", abos, index=abos.index(e["oev_abo"]), format_func=lambda k: OEV_ABOS[k],
                               help="Preise nach dem offiziellen Tarif für Strecken-Abos (Alliance SwissPass, "
                                    "2. Klasse). Ein Jahres-Abo kostet 9 Monatspreise, das GA 4'095 CHF.")
        st.markdown("**Auto**")
        links, rechts = st.columns(2)
        hat_auto = links.toggle("Ich habe schon ein Auto", e["hat_auto"],
                                help="Ja: nur Benzin, Unterhalt, Reifen (28 Rp./km). "
                                     "Nein: inklusive Kauf und Versicherung (74 Rp./km, TCS 2026)")
        parkplatz_chf = rechts.number_input("Parkplatz am Arbeitsort (CHF pro Monat)", 0, 1_000,
                                            e["parkplatz_chf"], step=10)
        st.markdown("**Vorliebe**")
        links, rechts = st.columns(2)
        lieblinge = [None] + list(VM_NAME)
        lieblings_vm = links.selectbox("Am liebsten fahre ich mit", lieblinge, index=lieblinge.index(e["lieblings_vm"]),
                                       format_func=lambda vm: "keine Vorliebe" if vm is None else VM_NAME[vm])
        toleranz_min = rechts.slider("… solange es höchstens so viel länger dauert (Min.)", 0, 30,
                                     e["toleranz_min"], step=5,
                                     help="Sonst wählt die App das Verkehrsmittel mit den tiefsten Kosten")

        zurueck_spalte, weiter_spalte = st.columns(2)
        zurueck = zurueck_spalte.form_submit_button("Zurück", icon=":material/arrow_back:")
        weiter = weiter_spalte.form_submit_button("Weiter zu den Vergleichen", type="primary")
    if zurueck:
        gehe_zu(1)
    if weiter:
        if not verkehrsmittel:
            st.error("Wähle mindestens ein Verkehrsmittel aus.")
        else:
            neu = {"verkehrsmittel": verkehrsmittel, "buerotage": buerotage, "max_pendel": max_pendel,
                   "hat_auto": hat_auto, "parkplatz_chf": parkplatz_chf, "oev_abo": oev_abo,
                   "lieblings_vm": lieblings_vm, "toleranz_min": toleranz_min}
            if any(e.get(k) != v for k, v in neu.items()):
                ml_zuruecksetzen()
            e.update(neu)
            gehe_zu(3)

# --- Schritt 3: Paarvergleiche, daraus lernt das ML-Modell (Arbeitspaket 3) ---
elif schritt == 3:
    # Bewusst ohne Zeitwert: sonst ändern sich nach jeder Antwort Rangliste, Karten und Live-Abfragen
    df, heute = gesamtkosten_berechnen(e, gemeinden)
    kandidaten = df[(df["bfs_nr"] != e["heute_nr"]) & (df["pendel_min"] <= e["max_pendel"])]
    st.header("Was ist dir deine Zeit wert?")
    st.markdown(
        "Zwei Gemeinden, eine ist günstiger, die andere näher. Wähle die, in der du lieber wohnen "
        "würdest. Aus deinen Antworten schätzt ein Machine-Learning-Modell (logistische Regression), "
        "wie viel dir eine Minute Arbeitsweg wert ist. Bei jeder Gemeinde siehst du alle Verkehrsmittel; "
        "gerechnet wird mit dem markierten."
    )
    # Paare nur einmal bilden: k-means wählt unterschiedliche Gemeinden, daraus echte Trade-offs
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
        st.progress(len(antworten) / len(paare), text=f"Vergleich {len(antworten) + 1} von {len(paare)}")
        ga, gb = nach_nr.loc[a], nach_nr.loc[b]
        for spalte, g, andere, buchstabe in zip(st.columns(2), [ga, gb], [gb, ga], ["A", "B"]):
            with spalte.container(border=True):
                st.subheader(g["name"])
                st.caption(f"Kanton {g['kanton']}")
                st.metric("Kosten pro Jahr", f"{chf(g['gesamtkosten'])} CHF",
                          delta=f"{mit_vorzeichen(g['gesamtkosten'] - andere['gesamtkosten'])} CHF",
                          delta_color="inverse")
                st.metric(f"Arbeitsweg mit {VM_NAME[g['bestes_vm']]}", f"{g['pendel_min']:.0f} Min.",
                          delta=f"{mit_vorzeichen(g['pendel_min'] - andere['pendel_min'])} Min.",
                          delta_color="inverse")
                # Alle Verkehrsmittel im Überblick, das gewählte markiert
                zeilen = ["| | Zeit | Kosten/Jahr |", "|---|---:|---:|"]
                for vm in ["oev", "auto", "velo"]:
                    if pd.isna(g[f"{vm}_min"]):
                        continue
                    name = f"**{VM_NAME[vm]}** :material/check:" if vm == g["bestes_vm"] else VM_NAME[vm]
                    zeilen.append(f"| {name} | {g[f'{vm}_min']:.0f} Min. | {chf(g[f'{vm}_chf'])} |")
                st.markdown("\n".join(zeilen))
                st.caption(f"Steuern {chf(g['steuer_chf'])} · Miete {chf(g['miete_chf'])} pro Monat")
                if st.button(f"{g['name']} wählen", key=f"wahl_{buchstabe}", type="primary", width="stretch"):
                    antworten.append({
                        "gesamtkosten_a": ga["gesamtkosten"], "pendel_min_a": ga["pendel_min"],
                        "gesamtkosten_b": gb["gesamtkosten"], "pendel_min_b": gb["pendel_min"],
                        "wahl_a": int(buchstabe == "A"),
                    })
                    modell = fit_preferences(pd.DataFrame(antworten))
                    st.session_state["zeitwert"] = modell["chf_pro_minute"] if modell else None
                    st.session_state.pop("zeitwert_10min", None)   # Regler wieder auf den gelernten Wert
                    if len(antworten) == len(paare):
                        gehe_zu(4)
                    st.rerun()
    zurueck_spalte, weiter_spalte = st.columns(2)
    if zurueck_spalte.button("Zurück", icon=":material/arrow_back:"):
        gehe_zu(2)
    if len(antworten) >= MIN_VERGLEICHE:
        if weiter_spalte.button("Ergebnis anzeigen", type="primary"):
            gehe_zu(4)
    elif weiter_spalte.button("Ohne Vergleiche weiter", help="Dann rankt die App nur nach Kosten"):
        gehe_zu(4)

# --- Schritt 4: Ergebnis (Grafiken: Arbeitspaket 4) ---
else:
    gelernt = st.session_state.get("zeitwert")
    antworten = st.session_state.get("antworten", [])
    # Startwert des Reglers: der gelernte Zeitwert (gerundet), sonst 0 = nur Franken
    if "zeitwert_10min" not in st.session_state:
        start = 0 if gelernt is None else min(round(10 * gelernt / 250) * 250, ZEITWERT_MAX_10MIN)
        st.session_state["zeitwert_10min"] = start
    zeitwert = aktueller_zeitwert()
    df, heute = gesamtkosten_berechnen(e, gemeinden, zeitwert, nachfragen=True)
    liste = rangliste(df, e, zeitwert)
    liste["zeitkosten"] = liste["pendel_min"] * (zeitwert or 0)
    top = liste.head(ANZAHL_TOP)
    top5 = top["bfs_nr"].head(5).tolist()

    st.header("Dein Ergebnis")
    if top.empty:
        st.warning("Keine Gemeinde liegt innerhalb deiner maximalen Pendelzeit. Erhöhe sie im Schritt Arbeitsweg.")
        st.stop()

    beste = top.iloc[0]
    minuten = int(beste["mehr_pendeln"])
    name_beste = beste["name"] if beste["name"].endswith(")") else f"{beste['name']} ({beste['kanton']})"
    if beste["ersparnis"] > 0:
        kernsatz = f"spart dir **{chf(beste['ersparnis'])} CHF pro Jahr**"
    else:
        kernsatz = f"kostet dich {chf(-beste['ersparnis'])} CHF mehr pro Jahr, ist aber näher"
    st.markdown(f"### {name_beste} {kernsatz}")
    st.markdown(
        f"gegenüber {heute['name']}, mit {abs(minuten)} Minuten {'mehr' if minuten > 0 else 'weniger'} "
        f"Arbeitsweg pro Strecke ({VM_NAME[beste['bestes_vm']]})."
    )
    # Vergleichstabelle heute gegen Vorschlag: die wichtigsten Zahlen auf einen Blick
    def zeile(titel, heute_wert, neu_wert, einheit="CHF"):
        return {"": titel, heute["name"]: f"{chf(heute_wert)} {einheit}",
                beste["name"]: f"{chf(neu_wert)} {einheit}",
                "Unterschied": f"{mit_vorzeichen(neu_wert - heute_wert)} {einheit}"}
    st.table(pd.DataFrame([
        zeile("Steuern pro Jahr", heute["steuer_chf"], beste["steuer_chf"]),
        zeile("Miete pro Jahr", 12 * heute["miete_chf"], 12 * beste["miete_chf"]),
        zeile(f"Pendeln pro Jahr ({VM_NAME[heute['bestes_vm']]} / {VM_NAME[beste['bestes_vm']]})",
              heute["pendel_chf"], beste["pendel_chf"]),
        zeile("Total pro Jahr", heute["gesamtkosten"], beste["gesamtkosten"]),
        zeile("Arbeitsweg pro Strecke", heute["pendel_min"], beste["pendel_min"], "Min."),
    ]).set_index(""))

    # --- So rechnet die App (Erklärung für die Nutzerin) ---
    with st.container(border=True):
        st.markdown("**So entsteht die Rangliste**")
        st.markdown(
            "1. **Gesamtkosten** pro Jahr = Steuern + 12 × Monatsmiete + Pendelkosten "
            "(mit dem günstigsten Verkehrsmittel bzw. deinem Lieblings-Verkehrsmittel).\n"
            "2. **Zeitkosten** = Minuten Arbeitsweg pro Strecke × dein Zeitwert. Sie machen sichtbar, "
            "dass ein langer Arbeitsweg dich auch etwas kostet, nämlich Freizeit.\n"
            "3. Die Rangliste sortiert nach **Gesamtkosten + Zeitkosten**. Ist dein Zeitwert 0, "
            "zählen nur die Franken, und die günstigste Gemeinde steht oben, egal wie weit weg."
        )

    # --- Dein Zeitwert: gelernt vom ML-Modell, anpassbar ---
    st.subheader("Dein Zeitwert")
    links, rechts = st.columns([3, 2])
    with links:
        if gelernt is not None:
            st.markdown(
                f"Das Modell hat aus deinen {len(antworten)} Vergleichen gelernt: 10 Minuten weniger "
                f"Arbeitsweg pro Strecke sind dir rund **{chf(10 * gelernt)} CHF pro Jahr** wert. "
                "Du kannst den Wert anpassen; die Rangliste rechnet sofort neu."
            )
        elif antworten:
            st.markdown("Deine Antworten widersprechen sich, das Modell konnte keinen Zeitwert schätzen. "
                        "Stelle ihn selbst ein oder beantworte die Vergleiche nochmals.")
        else:
            st.markdown("Du hast die Vergleiche übersprungen, darum zählen nur die Franken. "
                        "Stelle hier ein, was dir Zeit wert ist, oder lass ihn das Modell bestimmen.")
        st.slider("10 Minuten weniger Arbeitsweg pro Strecke sind mir pro Jahr wert (CHF)",
                  0, ZEITWERT_MAX_10MIN, step=250, key="zeitwert_10min")
        if st.button("Zeitwert mit Vergleichen bestimmen", icon=":material/refresh:"):
            ml_zuruecksetzen()
            gehe_zu(3)
    with rechts:
        if antworten:
            st.plotly_chart(zeitwert_chart(pd.DataFrame(antworten), zeitwert), width="stretch")
            st.caption("Jeder Punkt ist ein Vergleich. Die Linie ist dein Zeitwert: Liegt eine nähere Gemeinde "
                       "darunter, lohnt sich der Aufpreis für dich.")

    tab_rangliste, tab_tradeoff, tab_karte, tab_warum = st.tabs(
        ["Rangliste", "Günstig oder nah?", "Karte", "Warum nicht einfach Zug?"])
    with tab_rangliste:
        st.markdown("Die 10 Gemeinden, die nach Gesamtkosten und Zeitkosten am besten zu dir passen, "
                    "innerhalb deiner maximalen Pendelzeit.")
        tabelle = pd.DataFrame({
            "Gemeinde": [n if n.endswith(")") else f"{n} ({k})" for n, k in zip(top["name"], top["kanton"])],
            "Gesamtkosten": top["gesamtkosten"].map(lambda v: f"{chf(v)} CHF"),
            "Zeitkosten": top["zeitkosten"].map(lambda v: f"{chf(v)} CHF"),
            "Summe": (top["gesamtkosten"] + top["zeitkosten"]).map(lambda v: f"{chf(v)} CHF"),
            "Ersparnis ggü. heute": top["ersparnis"].map(lambda v: f"{mit_vorzeichen(v)} CHF"),
            "Arbeitsweg": [f"{m:.0f} Min. {VM_NAME[vm]}" for m, vm in zip(top["pendel_min"], top["bestes_vm"])],
        })
        tabelle.index = range(1, len(tabelle) + 1)
        st.table(tabelle)
        if "oev" in e["verkehrsmittel"]:
            echt = int((top["oev_geschaetzt"] == False).sum())   # noqa: E712
            st.caption(f"ÖV-Zeiten in dieser Rangliste: {echt} aus dem Fahrplan (inkl. Fusswege), "
                       f"{len(top) - echt} geschätzt.")
        st.markdown("**Woraus setzen sich die Kosten zusammen?**")
        st.plotly_chart(kosten_balken(df, e["heute_nr"], top5), width="stretch")

        # Arbeitsweg im Detail (Task 4.6): die drei Verkehrsmittel als Vergleichstabelle
        gewaehlt = st.selectbox("Arbeitsweg im Detail für", top["bfs_nr"], format_func=lambda nr: namen[nr])
        g = df.set_index("bfs_nr").loc[gewaehlt]
        reihen = []
        for vm in ["oev", "auto", "velo"]:
            if pd.isna(g[f"{vm}_min"]):
                reihen.append({"Verkehrsmittel": VM_NAME[vm], "Zeit pro Strecke": "–",
                               "Kosten pro Jahr": "nicht gewählt oder zu weit", "": ""})
            else:
                reihen.append({"Verkehrsmittel": VM_NAME[vm],
                               "Zeit pro Strecke": f"{g[f'{vm}_min']:.0f} Min.",
                               "Kosten pro Jahr": f"{chf(g[f'{vm}_chf'])} CHF",
                               "": "gewählt" if vm == g["bestes_vm"] else ""})
        st.table(pd.DataFrame(reihen).set_index("Verkehrsmittel"))
    with tab_tradeoff:
        st.markdown("Jeder Punkt ist eine Gemeinde. Unten links liegen die, die günstig **und** nah sind. "
                    "Die Farbe zeigt das gewählte Verkehrsmittel.")
        nahe = df[df["pendel_min"] <= max(e["max_pendel"], heute["pendel_min"])]
        st.plotly_chart(tradeoff_chart(nahe, e["heute_nr"], top5), width="stretch")
    with tab_karte:
        st.markdown("Blau: günstiger als heute. Terrakotta: teurer. Mit der Maus siehst du die Zahlen.")
        ziel_lat, ziel_lon, _ = e["ort"]
        st.plotly_chart(map_chart(df, grenzen_laden(), ziel_lat, ziel_lon), width="stretch")
    with tab_warum:
        st.markdown("Wo die Steuern tief sind, ist die Miete oft hoch. Darum lohnt sich ein "
                    "Steuerparadies erst ab einem höheren Einkommen.")
        st.plotly_chart(scatter_chart(df, e["heute_nr"], top5), width="stretch")

    if st.button("Eingaben ändern", icon=":material/edit:"):
        gehe_zu(1)
    st.caption(
        "Quellen und Annahmen: Steuern ESTV, Steuerjahr 2026, ohne Kirchensteuer. Mieten geschätzt aus "
        "BFS-Durchschnitten pro Kanton und Gemeindetyp. ÖV: Strecken-Abo nach Tarif T650 bzw. GA; Fahrzeit "
        "aus dem Fahrplan plus 5 Min. zur Haltestelle und Fussweg zum Arbeitsort. Auto: TCS-Kilometerkosten "
        "plus Parkplatz, ohne Stau."
    )
