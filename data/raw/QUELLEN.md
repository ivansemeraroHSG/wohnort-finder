# Datenquellen

Stand der Downloads: 20.11.2026

| Datei | Inhalt | Quelle | Link | Stand |
| --- | --- | --- | --- | --- |
| gemeinden_2026.csv | Gemeindeliste mit Kanton, Bezirk, Gemeindetyp (GDETYP2020_9) und weiteren Raumgliederungen | BFS, Amtliches Gemeindeverzeichnis (REST-API) | https://www.agvchapp.bfs.admin.ch/api/communes/levels?date=01-01-2026 | 01.01.2026 |
| steuern_2026.csv | Einkommenssteuer (Bund, Kanton, Gemeinde) aller Gemeinden für 3 Haushaltstypen und 6 Einkommen | ESTV Steuerrechner, inoffizielle Schnittstelle, geladen mit scripts/steuern_laden.py | https://swisstaxcalculator.estv.admin.ch/#/taxburden/income-wealth-tax | Steuerjahr 2026 |
| mieten_pro_kanton.xlsx | Durchschnittliche Monatsmiete nach Zimmerzahl und Kanton (T 09.03.03.01) | BFS, Strukturerhebung | https://statistik.admin.ch/de/asset/36398431 | Daten bis 2024, publiziert 05.03.2026 |
| mieten_pro_gemeindetyp.xlsx | Durchschnittliche Monatsmiete nach Zimmerzahl und Gemeindetyp (T 09.03.03.16) | BFS, Strukturerhebung | https://statistik.admin.ch/de/asset/36398494 | Daten bis 2024, publiziert 05.03.2026 |
| gemeindegrenzen/Communes_K4_20250101_4326.geojson | Gemeindegrenzen, generalisiert (K4), WGS84 | BFS, Generalisierte Gemeindegrenzen | https://statistik.admin.ch/en/asset/34367751 | 01.01.2025 |
| gemeindegrenzen/Lacs_K4_20250101_4326.geojson | Seen für die Karte | BFS, Generalisierte Gemeindegrenzen | https://statistik.admin.ch/en/asset/34367751 | 01.01.2025 |
| LIESMICH.txt | Hinweis zum Ordner (keine Daten) | – | – | – |

## Einstellungen Steuerdaten

- Haushaltstypen: ledig ohne Kinder; verheiratet, ein Einkommen, ohne Kinder; verheiratet, ein Einkommen, 2 Kinder
- Einkommen (brutto): 50'000 / 75'000 / 100'000 / 150'000 / 200'000 / 300'000 CHF
- Keine Konfession (ohne Kirchensteuer), nur Einkommenssteuer
- Die ESTV bietet keine offizielle API. Wir nutzen die Schnittstelle der Webseite einmalig beim Aufbau der Datenbank, nicht live in der App.

## Bekannte Einschränkungen

- Mieten gibt es vom BFS nicht pro Gemeinde, nur nach Kanton und Gemeindetyp. Die Miete pro Gemeinde wird im Mietmodell (AP 3) geschätzt.
- Die Miet-Tabelle nach Gemeindetyp nutzt die Gemeindetypologie 2012 und fasst die 9 Typen zu 5 Gruppen zusammen. Unsere Gemeindeliste nutzt die Typologie 2020 (GDETYP2020_9). Zuordnung über die erste Ziffer des Codes (1x = städtisch, 2x = periurban, 3x = ländlich).
- Die Gemeindegrenzen haben Stand 01.01.2025, die Gemeindeliste 01.01.2026. Wenige Gemeinden (Fusionen, Kantonswechsel Moutier) passen nicht exakt; wird in Task 1.3 bereinigt.
- Die Mieten sind Durchschnittswerte aller bestehenden Mietverhältnisse (netto, ohne Nebenkosten), nicht aktuelle Angebotsmieten.