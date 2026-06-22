from __future__ import annotations

from datetime import date
from decimal import Decimal
from functools import partial

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from application.usecases.billing import GetBillingUseCase
from domain.entity import Expenditure
from infrastructure.config import OutboxSettings
from infrastructure.persistence.database import Base
from infrastructure.persistence.uow import SqlUnitOfWork


def memory_uow_factory() -> partial[SqlUnitOfWork]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return partial(SqlUnitOfWork, sessionmaker(bind=engine), OutboxSettings())


def test_get_billing_usecase_scrapes_and_persists() -> None:
    expected = [
        Expenditure(
            transaction_date=date(2026, 6, 21),
            description="Test purchase",
            card_member="Card Member",
            account_number="12345",
            amount=Decimal("42.50"),
            reference="ref-1",
        )
    ]
    scraper = FakeAmexScraper(expected)
    factory = memory_uow_factory()

    result = GetBillingUseCase(scraper, factory)(date(2026, 6, 1), date(2026, 6, 21))

    assert result == expected
    assert scraper.called_with == (date(2026, 6, 1), date(2026, 6, 21))
    with factory() as uow:
        assert uow.expenditures.list() == expected


def test_get_billing_usecase_rejects_inverted_interval() -> None:
    scraper = FakeAmexScraper([])

    with pytest.raises(ValueError, match="from_date"):
        GetBillingUseCase(scraper, memory_uow_factory())(
            date(2026, 6, 21), date(2026, 6, 1)
        )


class FakeAmexScraper:
    def __init__(self, expenditures: list[Expenditure]) -> None:
        self.expenditures = expenditures
        self.called_with: tuple[date, date] | None = None

    def scrape(self, from_date: date, to_date: date) -> list[Expenditure]:
        self.called_with = (from_date, to_date)
        return self.expenditures
