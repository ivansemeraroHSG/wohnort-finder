"""
app.py – Streamlit-Oberfläche des Wohnort-Finders (Arbeitspaket 5).

Verantwortlich: Ivan
KI-Hinweis: Mit Claude (Anthropic) erstellt; am 24.11.2026 mit Claude vereinfacht
(Branch WF-5.6-Umbau). Am 25.11.2026 mit Claude ergänzt (Branch WF-5.7): Ablauf in
vier Schritten, Karten zum Bewerten, alle Verkehrsmittel. Design (style.css): Ivan.

Starten (im Projektordner, mit aktivierter Umgebung):
    streamlit run app.py

Ablauf in vier Schritten:
1. Deine Situation:  Einkommen, Haushalt, Wohnung, heutiger Wohnort, Arbeitsort
2. Dein Arbeitsweg:  Verkehrsmittel, Bürotage, Abo, maximale Pendelzeit -> Berechnen
3. Bewerten:         zehn Gemeinden mit «gefällt» / «gefällt nicht», daraus lernt das ML-Modell
4. Ergebnis:         Rangliste, Grafiken und Karte

Wichtig zu Streamlit: Bei jedem Klick läuft diese ganze Datei von oben nach unten neu.
Was wir uns merken müssen (Schritt, Eingaben, Ergebnisse, Modell), steht darum in st.session_state.
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from api import geocode, ors_schluessel, pendeln_berechnen
from charts import chf, gewichte_chart, kosten_chart, scatter_chart
from data import HAUSHALTE, OEV_ABOS, get_municipalities, get_rent, get_tax
from model import ANZAHL_BEWERTEN, MERKMALE, MIN_BEWERTUNGEN, gewichte, score_all, select_for_rating, train_model
from scoring import gesamtkosten

st.set_page_config(page_title="Wohnort-Finder", page_icon=":material/home:")

SCHRITTE = ["Situation", "Arbeitsweg", "Bewerten", "Ergebnis"]
HAUSHALT_TEXT = {
    "ledig": "Ledig, keine Kinder",
    "verheiratet": "Verheiratet, keine Kinder",
    "verheiratet_2_kinder": "Verheiratet, 2 Kinder",
}
VM_TEXT = {"oev": "ÖV", "auto": "Auto", "velo": "Velo"}
ANZAHL_TOP = 10
ANZAHL_TIEFSTE_STEUERN = 20   # für den Satz unter dem Streudiagramm
# Standardwerte beim ersten Öffnen (Zürich = BFS-Nummer 261)
STANDARD = {
    "einkommen": 100000, "haushalt": "ledig", "zimmer": 3, "heute_nr": 261, "arbeitsort": "Zürich HB",
    "verkehrsmittel": ["oev", "auto", "velo"], "buerotage": 5, "hat_auto": False,
    "oev_abo": "guenstigstes", "max_pendel": 45,
}

# Unser eigenes CSS (Schrittanzeige, Karten, Tabellen) einmal laden
CSS = (Path(__file__).parent / "style.css").read_text(encoding="utf-8")
st.html(f"<style>{CSS}</style>")


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------
def gehe_zu(schritt):
    """Wechselt zu einem anderen Schritt und lädt die Seite neu."""
    st.session_state["schritt"] = schritt
    st.rerun()


def schritte_anzeigen(aktuell):
    """Schrittanzeige oben: erledigte Schritte mit Häkchen, der aktuelle gefüllt."""
    teile = []
    for nr in range(1, len(SCHRITTE) + 1):
        titel = SCHRITTE[nr - 1]
        if nr < aktuell:
            teile.append(f'<span class="schritt fertig"><span class="nr">&#10003;</span>{titel}</span>')
        elif nr == aktuell:
            teile.append(f'<span class="schritt aktiv"><span class="nr">{nr}</span>{titel}</span>')
        else:
            teile.append(f'<span class="schritt"><span class="nr">{nr}</span>{titel}</span>')
    st.html('<div class="schritte">' + '<span class="verbindung"></span>'.join(teile) + "</div>")


def unterschied(neu, heute, einheit):
    """Unterschied zu heute als farbiger Text: weniger ist besser (grün), mehr schlechter."""
    differenz = neu - heute
    if round(differenz) == 0:
        return '<span class="klein">gleich</span>'
    if differenz < 0:
        return f'<span class="besser">-{chf(-differenz)} {einheit}</span>'
    return f'<span class="schlechter">+{chf(differenz)} {einheit}</span>'


def arbeitsweg_text(zeile):
    """Zum Beispiel «24 Min. ÖV» oder «ca. 41 Min. ÖV», wenn die Zeit geschätzt ist."""
    text = f"{chf(zeile['pendel_min'])} Min. {VM_TEXT[zeile['verkehrsmittel']]}"
    if zeile["geschaetzt"]:
        text = "ca. " + text
    return text


def karte_html(g, heute, bewertung):
    """Eine Gemeinde als Karte: ihre Werte und der Unterschied zum heutigen Wohnort."""
    klasse = "karte"
    if bewertung == 1:
        klasse = "karte gefaellt"
    elif bewertung == 0:
        klasse = "karte gefaellt-nicht"
    zeilen = [
        ("Steuern pro Jahr", chf(g["steuer_chf"]), unterschied(g["steuer_chf"], heute["steuer_chf"], "")),
        ("Miete pro Monat", chf(g["miete_chf"]), unterschied(g["miete_chf"], heute["miete_chf"], "")),
        ("Arbeitsweg", arbeitsweg_text(g), unterschied(g["pendel_min"], heute["pendel_min"], "Min.")),
        ("Pendeln pro Jahr", chf(g["pendel_chf"]), unterschied(g["pendel_chf"], heute["pendel_chf"], "")),
    ]
    html = f'<div class="{klasse}"><div class="kopf"><span class="name">{g["name"]}</span>'
    html += f'<span class="kanton">Kanton {g["kanton"]}</span></div><table>'
    for titel, wert, diff in zeilen:
        html += f'<tr><td>{titel}</td><td class="wert">{wert}</td><td class="diff">{diff}</td></tr>'
    html += (f'<tr class="total"><td>Total pro Jahr</td><td class="wert">{chf(g["gesamtkosten"])}</td>'
             f'<td class="diff">{unterschied(g["gesamtkosten"], heute["gesamtkosten"], "")}</td></tr>')
    html += "</table></div>"
    return html


def tabelle_html(kopf, zeilen, summe_zeile=None, klasse="tabelle"):
    """Einfache HTML-Tabelle. kopf: Liste mit Spaltennamen, zeilen: Liste mit Listen (HTML erlaubt)."""
    html = f'<table class="{klasse}"><tr>'
    for spalte in kopf:
        html += f"<th>{spalte}</th>"
    html += "</tr>"
    for i in range(len(zeilen)):
        if i == summe_zeile:
            html += '<tr class="summe">'
        else:
            html += "<tr>"
        for zelle in zeilen[i]:
            html += f"<td>{zelle}</td>"
        html += "</tr>"
    return html + "</table>"


def alles_berechnen(eingaben, gemeinden, extra_nrs=None):
    """
    Steuern, Miete, Pendeln und Gesamtkosten für alle Gemeinden.

    extra_nrs: Gemeinden, für die wir die ÖV-Zeit sicher live abfragen (die, die man sieht)
    Rückgabe: DataFrame mit einer Zeile pro Gemeinde
    """
    ziel_lat, ziel_lon, ort_name = eingaben["ort"]

    # Pendelzeiten und -kosten (fragt die APIs ab, darum mit Fortschrittsbalken)
    balken = st.progress(0.0, text="Arbeitswege zu deinem Arbeitsort werden berechnet …")
    pendel = pendeln_berechnen(ziel_lat, ziel_lon, gemeinden, eingaben, extra_nrs, balken)
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


def kandidaten_waehlen(df, eingaben):
    """Gemeinden innerhalb der maximalen Pendelzeit, ohne den heutigen Wohnort."""
    passt = (df["pendel_min"] <= eingaben["max_pendel"]) & (df["bfs_nr"] != eingaben["heute_nr"])
    return df[passt].copy()


def rangliste_berechnen(df, eingaben, modell):
    """Rangliste: mit Modell nach «passt zu dir», sonst nur nach den Gesamtkosten."""
    kandidaten = kandidaten_waehlen(df, eingaben)
    if modell is None:
        return kandidaten.sort_values("gesamtkosten")
    modell_lr, skalierer = modell
    kandidaten["passt"] = score_all(modell_lr, skalierer, kandidaten)
    # Zuerst nach «passt zu dir», bei Gleichstand die günstigere Gemeinde zuerst
    return kandidaten.sort_values(["passt", "gesamtkosten"], ascending=[False, True])


# ---------------------------------------------------------------------------
# Start: Daten laden, Zustand vorbereiten, Titel
# ---------------------------------------------------------------------------
gemeinden = get_municipalities()
# Dictionary BFS-Nummer -> Gemeindename, z. B. 261 -> "Zürich"
namen = {}
for nr, name in zip(gemeinden["bfs_nr"], gemeinden["name"]):
    namen[nr] = name
nummern = list(namen.keys())

if "schritt" not in st.session_state:
    st.session_state["schritt"] = 1
    st.session_state["eingaben"] = STANDARD.copy()
schritt = st.session_state["schritt"]
e = st.session_state["eingaben"]

st.title("Wohnort-Finder")
if schritt == 1:
    st.write(
        "Lohnt sich ein Umzug? Tiefe Steuern heissen nicht automatisch günstig wohnen: In Steuerparadiesen "
        "sind die Mieten oft hoch. Wir rechnen für deine Situation aus, was dich jede der 2'110 Schweizer "
        "Gemeinden pro Jahr kostet: Steuern, Miete und Arbeitsweg."
    )
schritte_anzeigen(schritt)


# ---------------------------------------------------------------------------
# Schritt 1: Deine Situation
# ---------------------------------------------------------------------------
if schritt == 1:
    st.header("Deine Situation")
    with st.form("situation", border=False):
        links, rechts = st.columns(2)
        einkommen = links.number_input("Bruttoeinkommen pro Jahr (CHF)", min_value=50000, max_value=300000,
                                       value=e["einkommen"], step=5000)
        haushalt = rechts.selectbox("Haushalt", HAUSHALTE, index=HAUSHALTE.index(e["haushalt"]),
                                    format_func=lambda h: HAUSHALT_TEXT[h])
        zimmer = links.slider("Zimmer", 1, 6, e["zimmer"], help="6 bedeutet 6 und mehr Zimmer")
        heute_nr = rechts.selectbox("Wo wohnst du heute?", nummern, index=nummern.index(e["heute_nr"]),
                                    format_func=lambda nr: namen[nr])
        arbeitsort = st.text_input("Wo arbeitest du?", e["arbeitsort"], help="Adresse oder Ort in der Schweiz")
        weiter = st.form_submit_button("Weiter zum Arbeitsweg", type="primary")

    if weiter:
        ort = geocode(arbeitsort)
        if ort is None:
            st.error("Diesen Arbeitsort finden wir nicht. Gib eine Adresse oder einen Ort in der Schweiz ein.")
        else:
            e.update({"einkommen": einkommen, "haushalt": haushalt, "zimmer": zimmer, "heute_nr": heute_nr,
                      "arbeitsort": arbeitsort, "ort": ort})
            gehe_zu(2)


# ---------------------------------------------------------------------------
# Schritt 2: Dein Arbeitsweg -> alles berechnen
# ---------------------------------------------------------------------------
elif schritt == 2:
    st.header("Dein Arbeitsweg")
    st.caption(f"Arbeitsort: {e['ort'][2]}")
    with st.form("arbeitsweg", border=False):
        verkehrsmittel = st.multiselect("Welche Verkehrsmittel kommen für dich in Frage?", list(VM_TEXT),
                                        default=e["verkehrsmittel"], format_func=lambda vm: VM_TEXT[vm],
                                        help="Pro Gemeinde nehmen wir das günstigste, das in deine "
                                             "maximale Pendelzeit passt.")
        links, rechts = st.columns(2)
        buerotage = links.slider("Bürotage pro Woche", 1, 5, e["buerotage"], help="Wichtig für die Autokosten")
        max_pendel = rechts.slider("Maximale Pendelzeit pro Strecke (Min.)", 10, 90, e["max_pendel"], step=5)
        abos = list(OEV_ABOS)
        oev_abo = links.selectbox("ÖV-Abo", abos, index=abos.index(e["oev_abo"]),
                                  format_func=lambda a: OEV_ABOS[a])
        rechts.write("")   # kleiner Abstand, damit die Checkbox auf der Höhe der Auswahl steht
        hat_auto = rechts.checkbox("Ich habe schon ein Auto", e["hat_auto"],
                                   help="Dann zählen nur Benzin, Unterhalt und Reifen (28 statt 74 Rp. pro km)")
        zurueck_spalte, weiter_spalte = st.columns(2)
        zurueck = zurueck_spalte.form_submit_button("Zurück", icon=":material/arrow_back:")
        berechnen = weiter_spalte.form_submit_button("Berechnen", type="primary")

    if zurueck:
        gehe_zu(1)
    if berechnen:
        if len(verkehrsmittel) == 0:
            st.error("Wähle mindestens ein Verkehrsmittel aus.")
            st.stop()
        e.update({"verkehrsmittel": verkehrsmittel, "buerotage": buerotage, "max_pendel": max_pendel,
                  "oev_abo": oev_abo, "hat_auto": hat_auto})
        df = alles_berechnen(e, gemeinden)
        kandidaten = kandidaten_waehlen(df, e)
        if len(kandidaten) < ANZAHL_BEWERTEN:
            st.error("Zu wenige Gemeinden liegen innerhalb deiner maximalen Pendelzeit. Erhöhe sie.")
            st.stop()
        # k-means wählt zehn unterschiedliche Gemeinden; für diese holen wir echte ÖV-Zeiten
        auswahl = select_for_rating(kandidaten)
        df = alles_berechnen(e, gemeinden, extra_nrs=auswahl)
        # Neue Berechnung: alte Bewertungen und altes Modell löschen
        st.session_state["df"] = df
        st.session_state["auswahl"] = auswahl
        st.session_state["bewertungen"] = {}
        st.session_state["modell"] = None
        st.session_state["top_geprueft"] = False
        gehe_zu(3)


# ---------------------------------------------------------------------------
# Schritt 3: Gemeinden bewerten (Daten für das ML-Modell)
# ---------------------------------------------------------------------------
elif schritt == 3:
    df = st.session_state["df"]
    bewertungen = st.session_state["bewertungen"]   # Dictionary bfs_nr -> 1 (gefällt) oder 0
    heute = df[df["bfs_nr"] == e["heute_nr"]].iloc[0]

    st.header("Welche Gemeinden gefallen dir?")
    st.write(
        "Ein k-means-Modell hat zehn möglichst unterschiedliche Gemeinden ausgewählt: günstig oder teuer, "
        "nah oder weit. Bewerte sie. Daraus lernt eine logistische Regression, was dir wichtig ist. "
        f"Es braucht mindestens {MIN_BEWERTUNGEN} Bewertungen, davon mindestens ein «gefällt» und ein "
        "«gefällt nicht»."
    )
    st.html(f'<div class="referenz"><div class="titel">Zum Vergleich: heute</div>'
            f'<b>{heute["name"]}</b> · Total {chf(heute["gesamtkosten"])} CHF pro Jahr · '
            f'Arbeitsweg {arbeitsweg_text(heute)}</div>')

    # Karten in zwei Spalten. Die Antwort steht im Dictionary bewertungen.
    auswahl = df[df["bfs_nr"].isin(st.session_state["auswahl"])]
    spalten = st.columns(2)
    for i, nr in enumerate(auswahl["bfs_nr"]):
        g = auswahl[auswahl["bfs_nr"] == nr].iloc[0]
        with spalten[i % 2]:
            st.html(karte_html(g, heute, bewertungen.get(nr)))
            knopf_ja, knopf_nein = st.columns(2)
            if knopf_ja.button("Gefällt", key=f"ja_{nr}", icon=":material/thumb_up:", width="stretch",
                               type="primary" if bewertungen.get(nr) == 1 else "secondary"):
                bewertungen[nr] = 1
                st.rerun()
            if knopf_nein.button("Gefällt nicht", key=f"nein_{nr}", icon=":material/thumb_down:", width="stretch",
                                 type="primary" if bewertungen.get(nr) == 0 else "secondary"):
                bewertungen[nr] = 0
                st.rerun()

    st.write(f"**{len(bewertungen)} von {len(auswahl)} bewertet**")
    zurueck_spalte, weiter_spalte = st.columns(2)
    if zurueck_spalte.button("Zurück", icon=":material/arrow_back:"):
        gehe_zu(2)
    if weiter_spalte.button("Ergebnis anzeigen", type="primary"):
        # Trainingsdaten: die Merkmale der bewerteten Gemeinden und die Antwort (1 oder 0)
        bewertete_nrs = list(bewertungen.keys())
        bewertet = df.set_index("bfs_nr").loc[bewertete_nrs, MERKMALE]
        bewertet["gefaellt"] = list(bewertungen.values())
        st.session_state["modell"] = train_model(bewertet)
        st.session_state["top_geprueft"] = False   # neue Rangliste: Top 10 nochmals live prüfen
        gehe_zu(4)


# ---------------------------------------------------------------------------
# Schritt 4: Ergebnis
# ---------------------------------------------------------------------------
else:
    df = st.session_state["df"]
    modell = st.session_state["modell"]

    # Einmal: für die Top 10 echte ÖV-Zeiten holen und neu rechnen
    if not st.session_state["top_geprueft"]:
        top_nrs = list(rangliste_berechnen(df, e, modell)["bfs_nr"].head(ANZAHL_TOP))
        df = alles_berechnen(e, gemeinden, extra_nrs=st.session_state["auswahl"] + top_nrs)
        st.session_state["df"] = df
        st.session_state["top_geprueft"] = True

    heute = df[df["bfs_nr"] == e["heute_nr"]].iloc[0]
    rangliste = rangliste_berechnen(df, e, modell)
    top = rangliste.head(ANZAHL_TOP)
    top5_nrs = list(top["bfs_nr"].head(5))
    beste = top.iloc[0]

    st.header("Dein Ergebnis")
    if "auto" in e["verkehrsmittel"] or "velo" in e["verkehrsmittel"]:
        if ors_schluessel() is None:
            st.warning("Kein Schlüssel für openrouteservice gefunden: Auto- und Velozeiten sind nur "
                       "aus der Luftlinie geschätzt.")

    # --- Ergebnis-Box: die wichtigste Aussage zuerst ---
    if beste["ersparnis"] > 0:
        aussage = f"spart dir {chf(beste['ersparnis'])} CHF pro Jahr"
    else:
        aussage = f"kostet dich {chf(-beste['ersparnis'])} CHF mehr pro Jahr"
    zusatz = f"gegenüber {heute['name']}, mit {arbeitsweg_text(beste)} statt {arbeitsweg_text(heute)} Arbeitsweg."
    if modell is not None:
        zusatz += f" Passt laut Modell zu {chf(beste['passt'])} % zu deinen Bewertungen."
    st.html(f'<div class="ergebnis"><div class="titel">Platz 1 für dich</div>'
            f'<div class="gross">{beste["name"]} {aussage}</div><div class="zusatz">{zusatz}</div></div>')

    # --- Vergleich heute gegen Platz 1 (Vorschlag des Dozenten: Werte nebeneinander) ---
    st.subheader(f"{heute['name']} und {beste['name']} im Vergleich")
    vergleich = [
        ["Steuern pro Jahr", chf(heute["steuer_chf"]), chf(beste["steuer_chf"]),
         unterschied(beste["steuer_chf"], heute["steuer_chf"], "CHF")],
        ["Miete pro Jahr", chf(12 * heute["miete_chf"]), chf(12 * beste["miete_chf"]),
         unterschied(12 * beste["miete_chf"], 12 * heute["miete_chf"], "CHF")],
        ["Pendeln pro Jahr", chf(heute["pendel_chf"]), chf(beste["pendel_chf"]),
         unterschied(beste["pendel_chf"], heute["pendel_chf"], "CHF")],
        ["Total pro Jahr", chf(heute["gesamtkosten"]), chf(beste["gesamtkosten"]),
         unterschied(beste["gesamtkosten"], heute["gesamtkosten"], "CHF")],
        ["Arbeitsweg pro Strecke", arbeitsweg_text(heute), arbeitsweg_text(beste),
         unterschied(beste["pendel_min"], heute["pendel_min"], "Min.")],
    ]
    st.html(tabelle_html(["", f"{heute['name']} (heute)", beste["name"], "Unterschied"], vergleich,
                         summe_zeile=3))

    # --- Was das Modell gelernt hat ---
    st.subheader("Was dir wichtig ist")
    if modell is None:
        st.info(f"Kein Modell: Es braucht mindestens {MIN_BEWERTUNGEN} Bewertungen mit mindestens einem "
                "«gefällt» und einem «gefällt nicht». Die Rangliste sortiert darum nur nach den Kosten.")
    else:
        gelernt = gewichte(modell[0])
        wichtigstes = gelernt[0]
        for g in gelernt:
            if g["prozent"] > wichtigstes["prozent"]:
                wichtigstes = g
        st.write(f"Aus deinen {len(st.session_state['bewertungen'])} Bewertungen hat die logistische Regression "
                 f"gelernt: Am wichtigsten ist dir **{wichtigstes['text'].lower()}**. Die Prozente zeigen, "
                 "wie stark jedes Merkmal deine Bewertungen erklärt.")
        st.pyplot(gewichte_chart(gelernt))

    # --- Rangliste ---
    st.subheader(f"Deine Top {ANZAHL_TOP}")
    kopf = ["", "Gemeinde", "Total pro Jahr", "Ggü. heute", "Arbeitsweg"]
    if modell is not None:
        kopf.append("Passt zu dir")
    zeilen = []
    for platz, (index, g) in enumerate(top.iterrows(), start=1):
        zeile = [platz, f"{g['name']} <span class='klein'>{g['kanton']}</span>", chf(g["gesamtkosten"]),
                 unterschied(g["gesamtkosten"], heute["gesamtkosten"], ""), arbeitsweg_text(g)]
        if modell is not None:
            zeile.append(f"{chf(g['passt'])} %")
        zeilen.append(zeile)
    st.html(tabelle_html(kopf, zeilen, klasse="tabelle rangliste"))
    if modell is not None:
        st.caption("Sortiert nach «Passt zu dir» (Wahrscheinlichkeit aus dem Modell), bei Gleichstand nach Kosten. "
                   "«ca.» = Zeit aus der Luftlinie geschätzt, nicht aus Fahrplan oder Routenplaner.")

    st.subheader("Woraus setzen sich die Kosten zusammen?")
    st.pyplot(kosten_chart(df, e["heute_nr"], top5_nrs))

    # --- Streudiagramm (Vorschlag des Dozenten) mit einer Aussage aus den Daten ---
    st.subheader("Tiefe Steuern, hohe Miete?")
    tiefste = df.nsmallest(ANZAHL_TIEFSTE_STEUERN, "steuer_chf")
    mehr_miete = tiefste["miete_chf"].mean() - df["miete_chf"].mean()
    st.write(f"In den {ANZAHL_TIEFSTE_STEUERN} Gemeinden mit den tiefsten Steuern ist die Miete im Schnitt "
             f"{chf(mehr_miete)} CHF pro Monat höher als im Schweizer Durchschnitt. Ein Steuerparadies lohnt "
             "sich darum erst ab einem höheren Einkommen.")
    st.pyplot(scatter_chart(df, e["heute_nr"], top5_nrs))
    plaetze = []
    for platz in range(len(top5_nrs)):
        plaetze.append(f"{platz + 1} {namen[top5_nrs[platz]]}")
    st.caption(" · ".join(plaetze) + f" · Stern: {heute['name']} (heute)")

    # --- Karte mit st.map: Top 10 grün, heutiger Wohnort schwarz, Arbeitsort terrakotta ---
    st.subheader("Wo liegen deine Top 10?")
    breiten = list(top["lat"]) + [heute["lat"], e["ort"][0]]
    laengen = list(top["lon"]) + [heute["lon"], e["ort"][1]]
    farben = ["#2f6b4f"] * len(top) + ["#22211e", "#b5532a"]
    karte = pd.DataFrame({"lat": breiten, "lon": laengen, "farbe": farben})
    st.map(karte, latitude="lat", longitude="lon", color="farbe", size=700)
    st.caption("Grün: deine Top 10 · Schwarz: heutiger Wohnort · Terrakotta: Arbeitsort")

    zurueck_spalte, neu_spalte = st.columns(2)
    if zurueck_spalte.button("Nochmals bewerten", icon=":material/arrow_back:"):
        gehe_zu(3)
    if neu_spalte.button("Eingaben ändern", icon=":material/edit:"):
        gehe_zu(1)

    st.caption(
        "Quellen und Annahmen: Steuern ESTV, Steuerjahr 2026, ohne Kirchensteuer. Mieten geschätzt aus "
        "BFS-Durchschnitten pro Kanton und Gemeindetyp. ÖV: Fahrplan (transport.opendata.ch) plus 5 Min. "
        "zur Haltestelle; Abo nach Tarif T650 bzw. GA. Auto und Velo: openrouteservice; Autokosten TCS 2026. "
        "Details in data/raw/QUELLEN.md."
    )
