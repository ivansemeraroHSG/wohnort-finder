# Wohnort-Finder

Gruppenprojekt im Kurs *Fundamentals and Methods of Computer Science*, HSG, HS 2026.

## Problem

Steuern, Miete und Pendelzeit stehen auf verschiedenen Websites. Gemeinden zu vergleichen dauert Stunden, und viele wissen nicht, welchen Trade-off sie eigentlich wollen. Die App kombiniert die drei Faktoren und lernt aus Bewertungen, was der Nutzerin wichtig ist.

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
| `scoring.py` | Ranking mit festen Gewichten (Fallback) |
| `data.py` | Zugriff auf die SQLite-Datenbank |
| `api.py` | swisstopo und transport.opendata.ch |
| `model.py` | k-means, logistische Regression, Mietmodell |
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

**Wie wir die Daten aufbereiten**

- **Steuern:** Die ESTV bietet keine offizielle API. Wir haben die Schnittstelle des Steuerrechners einmalig mit `scripts/steuern_laden.py` abgefragt (ohne Kirchensteuer, nur Einkommenssteuer). Für Einkommen zwischen den Stufen interpoliert `data.get_tax()` linear.
- **Mieten:** Das BFS veröffentlicht Mieten nicht pro Gemeinde. Wir schätzen sie: Kantonsmiete × (Miete des Gemeindetyps / Miete Schweiz). Alle Mieten sind darum als geschätzt markiert. Es sind Durchschnitte bestehender Mietverhältnisse (netto), nicht aktuelle Angebotsmieten.
- **Gemeindegrenzen:** Die Grenzen haben Stand 2025. 14 Gemeinden haben bis 2026 fusioniert oder (Moutier) den Kanton gewechselt; `scripts/grenzen_aufbereiten.py` ordnet ihre Flächen den Gemeinden 2026 zu.
- **Pendelzeit:** Für die 50 nächsten Gemeinden live abgefragt (Montag 07:30), für alle anderen aus der Luftlinie geschätzt.

## Machine Learning

_Wird von AP 3 ergänzt._

## Einsatz von GenAI

_Welche Tools, wofür, was wir selbst geprüft haben._

## Team

_Namen und Arbeitspakete._
