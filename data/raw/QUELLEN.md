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

- Mieten gibt es vom BFS nicht pro Gemeinde, nur nach Kanton und Gemeindetyp. Die Miete pro Gemeinde schätzt scripts/build_db.py: Kantonsmiete × (Miete des Gemeindetyps / Miete Schweiz). Für 1-Zimmer-Wohnungen in Appenzell Innerrhoden fehlt der Kantonswert (BFS: "X"), dort gilt der Wert des Gemeindetyps.
- Die Miet-Tabelle nach Gemeindetyp nutzt die Gemeindetypologie 2012 und fasst die 9 Typen zu 5 Gruppen zusammen. Unsere Gemeindeliste nutzt die Typologie 2020 (GDETYP2020_9). Zuordnung über die erste Ziffer des Codes (1x = städtisch, 2x = periurban, 3x = ländlich).
- Die Gemeindegrenzen haben Stand 01.01.2025, die Gemeindeliste 01.01.2026. 14 Gemeinden haben fusioniert oder (Moutier) den Kanton gewechselt; scripts/grenzen_aufbereiten.py ordnet ihre Flächen den Gemeinden 2026 zu (Ergebnis: data/gemeindegrenzen_2026.geojson).
- Die Mieten sind Durchschnittswerte aller bestehenden Mietverhältnisse (netto, ohne Nebenkosten), nicht aktuelle Angebotsmieten.

## Kostenansätze fürs Pendeln (in data.py, keine Datei)

| Wert | Quelle | Stand |
| --- | --- | --- |
| Jahres-Strecken-Abo 2. Klasse als Preistabelle (`OEV_PREISE` in data.py): bis 5 km 684 CHF, bis 10 km 999 CHF … bis 120 km 3'717 CHF. Berechnet aus dem Grundpreis 17.22 CHF pro km und Monat mit der Staffelung des Tarifs; Jahres-Abo = 9 Monatspreise | Alliance SwissPass, Tarif T650 «Tarif für Streckenabonnemente», Ziffer 4.1 | Ausgabe 01.06.2026 |
| GA Erwachsene 2. Klasse: 4'095 CHF (für Strecken über 120 km) | Alliance SwissPass / Preisüberwacher, Medienmitteilung 04.08.2026 | ab 13.12.2026 |
| Auto: 74 Rp. pro km total; variable Kosten 4'135 CHF bei 15'000 km pro Jahr (= 28 Rp. pro km, wenn das Auto schon vorhanden ist) | TCS, Kilometerkosten 2026 | 06.01.2026 |
| 46 Arbeitswochen pro Jahr | eigene Annahme (52 Wochen minus Ferien und Feiertage) | – |

- Die Tabelle rechnet in Stufen: Eine Strecke von 12 km kostet so viel wie 15 km. Das ist etwas ungenauer als der Tarif, aber einfacher.
- Die Abo-Preise gelten pro Bahnkilometer. Wir setzen dafür die geschätzte Strassendistanz ein (Luftlinie × 1.35).
- Verbund-Abos (z. B. ZVV, Ostwind) können in Agglomerationen günstiger sein als das Strecken-Abo. Die App verwendet einheitlich das Strecken-Abo, damit alle Gemeinden gleich behandelt werden.
