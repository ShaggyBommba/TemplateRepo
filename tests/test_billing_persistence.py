from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from functools import partial

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from application.handlers.billing import GetBillingHandler
from application.usecases.billing import GetBillingUseCase
from domain.entity import Expenditure, OutboxJob
from domain.event import ScrapeCreated
from domain.value import EventKind, EventTopic
from infrastructure.config import OutboxSettings
from infrastructure.persistence.database import Base
from infrastructure.persistence.uow import SqlUnitOfWork


def test_expenditure_repository_crud() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = partial(SqlUnitOfWork, sessionmaker(bind=engine), OutboxSettings())
    expenditure = Expenditure(
        id="exp-1",
        transaction_date=date(2026, 6, 21),
        description="Test purchase",
        card_member="Card Member",
        account_number="12345",
        amount=Decimal("12.34"),
        reference="ref-1",
    )

    with factory() as uow:
        uow.expenditures.add(expenditure)
        uow.commit()

    with factory() as uow:
        assert uow.expenditures.get("exp-1") == expenditure
        assert uow.expenditures.list() == [expenditure]
        assert uow.expenditures.remove("exp-1") == expenditure
        uow.commit()

    with factory() as uow:
        assert uow.expenditures.get("exp-1") is None


def test_expenditure_repository_filters_by_date() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = partial(SqlUnitOfWork, sessionmaker(bind=engine), OutboxSettings())
    june = Expenditure(
        id="exp-1",
        transaction_date=date(2026, 6, 21),
        description="June purchase",
        card_member="Card Member",
        account_number="12345",
        amount=Decimal("12.34"),
        reference="ref-1",
    )
    july = Expenditure(
        id="exp-2",
        transaction_date=date(2026, 7, 1),
        description="July purchase",
        card_member="Card Member",
        account_number="12345",
        amount=Decimal("56.78"),
        reference="ref-2",
    )

    with factory() as uow:
        uow.expenditures.add(june)
        uow.expenditures.add(july)
        uow.commit()

    with factory() as uow:
        assert uow.expenditures.list(date(2026, 6, 1), date(2026, 6, 30)) == [june]


def test_get_billing_handler_persists_scraped_expenditures() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = partial(SqlUnitOfWork, sessionmaker(bind=engine), OutboxSettings())
    expenditure = Expenditure(
        id="exp-1",
        transaction_date=date(2026, 6, 21),
        description="Test purchase",
        card_member="Card Member",
        account_number="12345",
        amount=Decimal("12.34"),
        reference="ref-1",
    )
    scraper = FakeScraper([expenditure])

    asyncio.run(
        GetBillingHandler(GetBillingUseCase(scraper, factory), factory)(
            ScrapeCreated(
                payload={
                    "start_date": "2026-06-01",
                    "end_date": "2026-06-21",
                }
            )
        )
    )

    assert scraper.called_with == (date(2026, 6, 1), date(2026, 6, 21))
    with factory() as uow:
        assert uow.expenditures.list() == [expenditure]


def test_scrape_created_event_is_registered() -> None:
    event = OutboxJob(
        trace_id="trace-1",
        topic=EventTopic.SCRAPE,
        kind=EventKind.CREATED,
        payload={"start_date": "2026-06-01", "end_date": "2026-06-21"},
        max_attempts=1,
    ).to_event()

    assert isinstance(event, ScrapeCreated)


class FakeScraper:
    def __init__(self, expenditures: list[Expenditure]) -> None:
        self.expenditures = expenditures
        self.called_with: tuple[date, date] | None = None

    def scrape(self, from_date: date, to_date: date) -> list[Expenditure]:
        self.called_with = (from_date, to_date)
        return self.expenditures
