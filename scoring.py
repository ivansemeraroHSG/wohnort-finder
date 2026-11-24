"""
scoring.py – Gesamtkosten pro Gemeinde (Arbeitspaket 5).

Verantwortlich: Ivan
KI-Hinweis: Mit Claude (Anthropic) erstellt; am 24.11.2026 mit Claude vereinfacht
(Branch WF-5.6-Umbau).

Die Gesamtkosten sind die Grundlage der Rangliste. Sie gelten auch, solange das
ML-Modell noch nicht trainiert ist (zu wenige Bewertungen).
"""

MONATE = 12


def gesamtkosten(df):
    """Kosten in CHF pro Jahr: Steuern + 12 Monatsmieten + Pendelkosten."""
    return df["steuer_chf"] + MONATE * df["miete_chf"] + df["pendel_chf"]
