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
| `scripts/build_db.py` | baut die Datenbank aus `data/raw/` |

## Datenquellen

_Wird von AP 1 und AP 2 ergänzt (Quelle, Link, Stand)._

## Machine Learning

_Wird von AP 3 ergänzt._

## Einsatz von GenAI

_Welche Tools, wofür, was wir selbst geprüft haben._

## Team

_Namen und Arbeitspakete._
