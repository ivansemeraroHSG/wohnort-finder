# Wohnort-Finder

Gruppenprojekt im Kurs *Fundamentals and Methods of Computer Science*, HSG, HS 2026.

## Problem

Wer einen Job in Zürich hat, fragt sich: Lohnt es sich, nach Zug oder Schwyz zu ziehen? Tiefe Steuern heissen nicht automatisch günstig wohnen, denn in Steuerparadiesen sind die Mieten oft hoch. Ob sich ein Umzug lohnt, hängt vom eigenen Einkommen und Haushalt ab und lässt sich nicht im Kopf ausrechnen: Für eine ledige Person mit 60'000 CHF ist Zug rund 3'000 CHF pro Jahr teurer als Rapperswil-Jona, bei 300'000 CHF ist Zug über 8'000 CHF günstiger.

Der Wohnort-Finder rechnet für die eigene Situation die **Wohnkosten pro Jahr** (Steuern + 12 × Miete) aller 2110 Gemeinden aus, vergleicht sie mit dem heutigen Wohnort und zeigt, wie viel man spart und wie viel länger man dafür pendelt. Aus Bewertungen lernt die App, wie viel einem eine Minute Pendelzeit wert ist.

## Online-Version

_Link zu Streamlit Community Cloud folgt._

## Lokal starten

```
python -m venv ~/venvs/wohnort
source ~/venvs/wohnort/bin/activate      # Windows: %USERPROFILE%\venvs\wohnort\Scripts\activate
pip install -r requirements.txt
python scripts/grenzen_aufbereiten.py    # Gemeindegrenzen auf Stand 2026
python scripts/build_db.py               # baut data/wohnort.db
streamlit run app.py
```

## Aufbau

| Datei | Inhalt |
| --- | --- |
| `app.py` | Streamlit-Oberfläche |
| `scoring.py` | Wohnkosten pro Gemeinde (Grundlage des Rankings) |
| `data.py` | Zugriff auf die SQLite-Datenbank |
| `api.py` | swisstopo und transport.opendata.ch |
| `model.py` | k-means, logistische Regression (Wert der Pendelzeit) |
| `charts.py` | Karte, Scatterplot, Tabellen |
| `scripts/steuern_laden.py` | lädt die Steuerdaten einmalig von der ESTV |
| `scripts/grenzen_aufbereiten.py` | passt die Gemeindegrenzen an die Gemeinden 2026 an |
| `scripts/build_db.py` | baut die Datenbank aus `data/raw/` |
| `scripts/pendel_kalibrieren.py` | bestimmt die Formel für geschätzte Pendelzeiten |

## Datenquellen

Alle Daten sind öffentlich und kostenlos. Die Originaldateien liegen unverändert in `data/raw/`, bereinigt wird nur in `scripts/build_db.py`. Details zu jeder Datei: `data/raw/QUELLEN.md`.

| Daten | Quelle | Link | Stand | Verwendung |
| --- | --- | --- | --- | --- |
| Gemeindeliste mit Kanton und Gemeindetyp | BFS, Amtliches Gemeindeverzeichnis (REST-API) | https://www.agvchapp.bfs.admin.ch/api/communes/levels?date=01-01-2026 | 01.01.2026 | Liste der 2110 Gemeinden |
| Einkommenssteuer (Bund, Kanton, Gemeinde) | ESTV Steuerrechner, Schnittstelle der Webseite | https://swisstaxcalculator.estv.admin.ch | Steuerjahr 2026 | Steuern pro Gemeinde, 3 Haushaltstypen, 6 Einkommen |
| Durchschnittliche Miete nach Kanton (T 09.03.03.01) | BFS, Strukturerhebung | https://statistik.admin.ch/de/asset/36398431 | Daten 2024 | Basis der Mietschätzung |
| Durchschnittliche Miete nach Gemeindetyp (T 09.03.03.16) | BFS, Strukturerhebung | https://statistik.admin.ch/de/asset/36398494 | Daten 2024 | Basis der Mietschätzung |
| Generalisierte Gemeindegrenzen (K4) | BFS | https://statistik.admin.ch/en/asset/34367751 | 01.01.2025, angepasst auf 2026 | Karte, Koordinaten der Gemeinden |
| Adresssuche (Arbeitsort) | swisstopo SearchServer, live | https://api3.geo.admin.ch/rest/services/api/SearchServer | laufend | Koordinaten des Arbeitsorts |
| ÖV-Verbindungen | transport.opendata.ch, live | https://transport.opendata.ch/v1/connections | laufend | Pendelzeit zu den nächsten Gemeinden |
| Preise Strecken-Abo (Tarif T650) | Alliance SwissPass | https://www.allianceswisspass.ch/de/tarife-vorschriften/uebersicht | Ausgabe 01.06.2026 | ÖV-Kosten pro Jahr (`data.oev_abopreis`) |
| Preis GA 2. Klasse (4'095 CHF) | Alliance SwissPass / SBB, Medienmitteilung Preisüberwacher 04.08.2026 | https://www.sbb.ch/de/billette-angebote/abos/ga/ga-preise.html | ab Dezember 2026 | Obergrenze der ÖV-Kosten |
| Kilometerkosten Auto (74 Rp./km, davon variabel 4'135 CHF pro 15'000 km) | TCS | https://www.tcs.ch/de/der-tcs/presse/medienmitteilungen-2026/kilometerkosten-2026.php | 2026 | Autokosten pro Jahr |
| Fahrzeit und Strassendistanz Auto und Velo | openrouteservice (Matrix-API), live | https://openrouteservice.org | laufend | Auto- und Veloweg, Tarifkilometer (Task 2.6) |

**Wie wir die Daten aufbereiten**

- **Steuern:** Die ESTV bietet keine offizielle API. Wir haben die Schnittstelle des Steuerrechners einmalig mit `scripts/steuern_laden.py` abgefragt (ohne Kirchensteuer, nur Einkommenssteuer). Für Einkommen zwischen den Stufen interpoliert `data.get_tax()` linear.
- **Mieten:** Das BFS veröffentlicht Mieten nicht pro Gemeinde. Wir schätzen sie: Kantonsmiete × (Miete des Gemeindetyps / Miete Schweiz). Alle Mieten sind darum als geschätzt markiert. Es sind Durchschnitte bestehender Mietverhältnisse (netto), nicht aktuelle Angebotsmieten.
- **Gemeindegrenzen:** Die Grenzen haben Stand 2025. 14 Gemeinden haben bis 2026 fusioniert oder (Moutier) den Kanton gewechselt; `scripts/grenzen_aufbereiten.py` ordnet ihre Flächen den Gemeinden 2026 zu.
- **Pendelzeit:** Für die 50 nächsten Gemeinden live abgefragt (Montag 07:30), für alle anderen aus der Luftlinie geschätzt.
- **Pendelkosten:** ÖV = Jahres-Strecken-Abo nach Tarif T650 (Monatspreis × 9, Grundpreis 17.22 CHF pro km mit Rabatt je nach Distanz), höchstens der GA-Preis. Der Tarif rechnet mit Bahnkilometern; wir verwenden dafür die Strassendistanz. In Agglomerationen kann ein Verbund-Abo (z. B. ZVV) etwas günstiger sein. Auto = gefahrene km × 28 Rp. (Auto schon vorhanden, nur variable Kosten) bzw. 74 Rp. (TCS, inkl. Fixkosten), plus Parkplatz. 46 Arbeitswochen pro Jahr.

## Machine Learning

_Wird von AP 3 ergänzt._

## Einsatz von GenAI

_Welche Tools, wofür, was wir selbst geprüft haben._

## Team

_Namen und Arbeitspakete._
