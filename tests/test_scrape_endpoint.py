from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domain.entity import Expenditure
from domain.event import ScrapeCreated
from presentation.api.app import api
from presentation.api.routes.billing import ScrapeRequest, expenditures, scrape


def test_api_includes_scrape_endpoint() -> None:
    assert "/scrape" in api().openapi()["paths"]
    assert "/expenditures" in api().openapi()["paths"]


def test_scrape_endpoint_adds_outbox_job() -> None:
    app = SimpleNamespace(uow_factory=lambda: FakeUnitOfWork())

    response = scrape(
        ScrapeRequest(start_date=date(2026, 6, 1), end_date=date(2026, 6, 21)),
        app,
    )

    assert response == {"job_id": "job-1"}
    assert FakeUnitOfWork.last.outbox.appended == (
        ScrapeCreated.topic,
        ScrapeCreated.kind,
        {"start_date": "2026-06-01", "end_date": "2026-06-21"},
        ScrapeCreated.version,
    )
    assert FakeUnitOfWork.last.committed is True


def test_scrape_endpoint_rejects_inverted_interval() -> None:
    with pytest.raises(HTTPException):
        scrape(
            ScrapeRequest(start_date=date(2026, 6, 21), end_date=date(2026, 6, 1)),
            SimpleNamespace(),
        )


def test_expenditures_endpoint_lists_by_date() -> None:
    app = SimpleNamespace(uow_factory=lambda: FakeUnitOfWork())

    response = expenditures(date(2026, 6, 1), date(2026, 6, 30), app)

    assert response == FakeExpenditures.items
    assert FakeUnitOfWork.last.expenditures.called_with == (
        date(2026, 6, 1),
        date(2026, 6, 30),
    )


def test_expenditures_endpoint_rejects_inverted_interval() -> None:
    with pytest.raises(HTTPException):
        expenditures(date(2026, 6, 30), date(2026, 6, 1), SimpleNamespace())


class FakeOutbox:
    def append(self, *args):
        self.appended = args
        return SimpleNamespace(id="job-1")


class FakeExpenditures:
    items = [
        Expenditure(
            id="exp-1",
            transaction_date=date(2026, 6, 21),
            description="Test purchase",
            card_member="Card Member",
            account_number="12345",
            amount=Decimal("12.34"),
            reference="ref-1",
        )
    ]

    def list(self, start_date: date, end_date: date) -> list[Expenditure]:
        self.called_with = (start_date, end_date)
        return self.items


class FakeUnitOfWork:
    last: FakeUnitOfWork

    def __enter__(self):
        self.outbox = FakeOutbox()
        self.expenditures = FakeExpenditures()
        self.committed = False
        FakeUnitOfWork.last = self
        return self

    def __exit__(self, *args):
        return None

    def commit(self) -> None:
        self.committed = True
