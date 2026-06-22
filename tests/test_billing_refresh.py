from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from functools import partial

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from application.usecases import billing
from application.usecases.billing import RefreshBillingUseCase
from domain.entity import Expenditure
from infrastructure.config import OutboxSettings
from infrastructure.persistence.database import Base
from infrastructure.persistence.uow import SqlUnitOfWork

HISTORY_START = date(2024, 1, 1)
TODAY = date(2026, 6, 21)


def memory_uow_factory() -> partial[SqlUnitOfWork]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return partial(SqlUnitOfWork, sessionmaker(bind=engine), OutboxSettings())


def expenditure(reference: str, transaction_date: date, amount: str) -> Expenditure:
    return Expenditure(
        transaction_date=transaction_date,
        description="Purchase",
        card_member="Card Member",
        account_number="12345",
        amount=Decimal(amount),
        reference=reference,
    )


def test_full_refresh_scrapes_from_history_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    freeze_today(monkeypatch)
    scraper = FakeScraper([])

    RefreshBillingUseCase(scraper, memory_uow_factory(), HISTORY_START)(full=True)

    assert scraper.called_with == (HISTORY_START, TODAY)


def test_incremental_refresh_scrapes_from_latest_stored_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    freeze_today(monkeypatch)
    factory = memory_uow_factory()
    with factory() as uow:
        uow.expenditures.add(expenditure("R0", date(2026, 6, 10), "10.00"))
        uow.commit()
    scraper = FakeScraper([])

    RefreshBillingUseCase(scraper, factory, HISTORY_START)(full=False)

    assert scraper.called_with == (date(2026, 6, 10), TODAY)


def test_incremental_refresh_falls_back_to_history_start_when_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    freeze_today(monkeypatch)
    scraper = FakeScraper([])

    RefreshBillingUseCase(scraper, memory_uow_factory(), HISTORY_START)(full=False)

    assert scraper.called_with == (HISTORY_START, TODAY)


def test_refresh_does_not_duplicate_repeated_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    freeze_today(monkeypatch)
    factory = memory_uow_factory()
    scraper = FakeScraper([expenditure("R1", date(2026, 6, 20), "10.00")])
    refresh = RefreshBillingUseCase(scraper, factory, HISTORY_START)

    refresh(full=True)
    scraper.expenditures = [expenditure("R1", date(2026, 6, 20), "20.00")]
    refresh(full=True)

    with factory() as uow:
        stored = uow.expenditures.list()
    assert len(stored) == 1
    assert stored[0].amount == Decimal("20.00")


def freeze_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(billing, "now", lambda: datetime(2026, 6, 21, tzinfo=UTC))


class FakeScraper:
    def __init__(self, expenditures: list[Expenditure]) -> None:
        self.expenditures = expenditures
        self.called_with: tuple[date, date] | None = None

    def scrape(self, from_date: date, to_date: date) -> list[Expenditure]:
        self.called_with = (from_date, to_date)
        return self.expenditures
