from __future__ import annotations

from datetime import date
from decimal import Decimal

from infrastructure.config import AmexScraperConfig
from infrastructure.scraper.amex import AmexScraper


def test_parse_maps_amex_csv(tmp_path) -> None:
    csv_path = tmp_path / "activity.csv"
    csv_path.write_text(
        "Datum,Beskrivning,Kortmedlem,Konto #,Belopp,Utökade specifikationer,"
        "Visas på ditt kontoutdrag som,Adress,Ort,Postnummer,Land,Referens\n"
        '06/21/2026,Test purchase,Card Member,12345,"−123,45",Details,Statement,'
        "Street 1,Stockholm,111 22,SE,ABC123\n",
        encoding="utf-8",
    )

    expenditure = AmexScraper(
        AmexScraperConfig(username="user", password="password")
    ).parse(csv_path)[0]

    assert expenditure.transaction_date == date(2026, 6, 21)
    assert expenditure.description == "Test purchase"
    assert expenditure.card_member == "Card Member"
    assert expenditure.account_number == "12345"
    assert expenditure.amount == Decimal("-123.45")
    assert expenditure.extended_details == "Details"
    assert expenditure.statement_description == "Statement"
    assert expenditure.address == "Street 1"
    assert expenditure.city == "Stockholm"
    assert expenditure.postal_code == "111 22"
    assert expenditure.country == "SE"
    assert expenditure.reference == "ABC123"
