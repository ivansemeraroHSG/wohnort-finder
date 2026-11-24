# Wohnort-Finder

Gruppenprojekt im Kurs *Fundamentals and Methods of Computer Science*, HSG, HS 2026.

## Problem

Wer einen Job in Zürich hat, fragt sich: Lohnt es sich, nach Zug oder Schwyz zu ziehen? Tiefe Steuern heissen nicht automatisch günstig wohnen, denn in Steuerparadiesen sind die Mieten oft hoch. Ob sich ein Umzug lohnt, hängt vom eigenen Einkommen, Haushalt und Arbeitsweg ab und lässt sich nicht im Kopf ausrechnen.

Der Wohnort-Finder rechnet für die eigene Situation die **Gesamtkosten pro Jahr** (Steuern + 12 × Miete + Pendeln) aller 2'110 Gemeinden aus und vergleicht sie mit dem heutigen Wohnort. Aus den Bewertungen der Nutzerin lernt ein Machine-Learning-Modell, welche Gemeinden zu ihr passen.

## Online-Version

_Link zu Streamlit Community Cloud folgt._

## Lokal starten

```
python -m venv ~/venvs/wohnort
source ~/venvs/wohnort/bin/activate      # Windows: %USERPROFILE%\venvs\wohnort\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Die Datenbank `data/wohnort.db` liegt schon im Projekt. Nur wer sie aus den Rohdaten neu bauen will:

```
python scripts/grenzen_aufbereiten.py    # Gemeindegrenzen auf Stand 2026
python scripts/build_db.py               # baut data/wohnort.db
```

Für Auto und Velo braucht die App einen Schlüssel von openrouteservice in `.streamlit/secrets.toml` (`ORS_KEY = "..."`). Ohne Schlüssel schätzt sie die Zeiten aus der Luftlinie.

## Aufbau

| Datei | Inhalt |
| --- | --- |
| `app.py` | Streamlit-Oberfläche: Eingaben, Bewerten, Ergebnis |
| `data.py` | Zugriff auf die SQLite-Datenbank, feste Kostenwerte |
| `api.py` | swisstopo, transport.opendata.ch und openrouteservice; Pendelzeit und Pendelkosten |
| `model.py` | k-means (Auswahl zum Bewerten) und logistische Regression (was passt zu mir?) |
| `charts.py` | Grafiken mit matplotlib |
| `scoring.py` | Gesamtkosten pro Gemeinde |
| `scripts/grenzen_aufbereiten.py` | passt die Gemeindegrenzen an die Gemeinden 2026 an |
| `scripts/build_db.py` | baut die Datenbank aus `data/raw/` |
| `scripts/steuern_laden.py` | hat die Steuerdaten einmalig von der ESTV geladen |

## Datenquellen

Alle Daten sind öffentlich und kostenlos. Die Originaldateien liegen unverändert in `data/raw/`. Details zu jeder Datei und zu den Kostenansätzen: `data/raw/QUELLEN.md`.

| Daten | Quelle | Verwendung |
| --- | --- | --- |
| Gemeindeliste mit Kanton und Gemeindetyp | BFS, Amtliches Gemeindeverzeichnis, Stand 01.01.2026 | Liste der 2'110 Gemeinden |
| Einkommenssteuer (Bund, Kanton, Gemeinde) | ESTV Steuerrechner, Steuerjahr 2026 | Steuern pro Gemeinde, 3 Haushaltstypen, 6 Einkommen |
| Durchschnittliche Miete nach Kanton und nach Gemeindetyp | BFS, Strukturerhebung, Daten 2024 | Schätzung der Miete pro Gemeinde |
| Generalisierte Gemeindegrenzen | BFS, Stand 01.01.2025, angepasst auf 2026 | Koordinaten der Gemeinden |
| Adresssuche | swisstopo SearchServer (live) | Koordinaten des Arbeitsorts |
| ÖV-Verbindungen | transport.opendata.ch (live) | ÖV-Zeit für die 50 nächsten Gemeinden |
| Fahrzeit Auto und Velo | openrouteservice, Matrix-API (live) | Auto- und Velozeit, Strassen-km |
| Preise Strecken-Abo und GA | Alliance SwissPass, Tarif T650 (01.06.2026) | ÖV-Kosten pro Jahr |
| Kilometerkosten Auto | TCS 2026 | Autokosten pro Jahr |

**Wie wir rechnen**

- **Steuern:** In der Datenbank stehen 6 Einkommensstufen. Für ein Einkommen dazwischen rechnet `data.get_tax()` mit einem Dreisatz.
- **Mieten:** Das BFS veröffentlicht keine Mieten pro Gemeinde. Wir schätzen: Kantonsmiete × (Miete des Gemeindetyps / Miete Schweiz).
- **Pendelzeit:** ÖV für die 50 nächsten Gemeinden live aus dem Fahrplan (Montag 07:30), für alle anderen aus der Luftlinie geschätzt. Auto und Velo von openrouteservice.
- **Pendelkosten:** ÖV = Jahres-Strecken-Abo aus einer Preistabelle, höchstens das GA. Auto = km × 2 × Bürotage × 46 Wochen × 74 Rp. (bzw. 28 Rp., wenn das Auto schon da ist). Velo = 0 CHF.

## Machine Learning

Wir nutzen scikit-learn mit zwei Lernarten aus dem Kurs:

1. **Clustering (k-means):** Die Gemeinden innerhalb der maximalen Pendelzeit werden nach Steuern, Miete und Pendelzeit in 10 Gruppen eingeteilt. Aus jeder Gruppe zeigt die App eine Gemeinde zum Bewerten. So bewertet die Nutzerin möglichst unterschiedliche Gemeinden.
2. **Klassifikation (logistische Regression):** Die Nutzerin bewertet die Gemeinden mit «gefällt» (1) oder «gefällt nicht» (0). Das Modell lernt daraus und sagt für alle Gemeinden voraus, wie wahrscheinlich sie ihr gefallen («Passt zu dir in %»). Die Beträge der Koeffizienten zeigen, wie wichtig ihr Steuern, Miete und Pendelzeit sind.

Vor dem Training werden die Merkmale standardisiert (`StandardScaler`), damit Frankenbeträge und Minuten vergleichbar sind. Unter 6 Bewertungen oder ohne mindestens ein «gefällt» und ein «gefällt nicht» trainiert die App kein Modell und sortiert nur nach Kosten.

## Einsatz von GenAI

_Welche Tools, wofür, was wir selbst geprüft haben. Der KI-generierte Code ist in jeder Datei oben gekennzeichnet._

## Team

_Namen und Arbeitspakete._
