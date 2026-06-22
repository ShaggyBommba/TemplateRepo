from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from functools import partial

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from application.usecases import bills as bill_usecases
from application.usecases.bills import (
    CloseBillUseCase,
    DetectLateTransactionsUseCase,
    GetBillForReviewUseCase,
    GetBillSummaryUseCase,
    PrepareBillUseCase,
    ReviewBillLineUseCase,
)
from domain.entity import Allocation, BillingPeriod, Expenditure, ParticipantShare
from domain.error import BillClosed
from domain.value import BillStatus
from infrastructure.config import OutboxSettings
from infrastructure.persistence.database import Base
from infrastructure.persistence.uow import SqlUnitOfWork


def memory_uow_factory() -> partial[SqlUnitOfWork]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return partial(SqlUnitOfWork, sessionmaker(bind=engine), OutboxSettings())


def test_prepare_bill_creates_lines_for_period_expenditures() -> None:
    factory = memory_uow_factory()
    period = BillingPeriod.starting(2026, 6)
    with factory() as uow:
        uow.expenditures.add(expenditure("R1", date(2026, 6, 21)))
        uow.expenditures.add(expenditure("R2", date(2026, 7, 1)))
        uow.expenditures.add(expenditure("R3", date(2026, 7, 2)))
        uow.commit()

    bill = PrepareBillUseCase(factory)(period)
    bill = PrepareBillUseCase(factory)(period)

    assert bill.id == "2026-06"
    assert [line.expenditure_id for line in bill.lines] == ["R1", "R2"]


def test_review_bill_line_persists_category_and_allocation() -> None:
    factory = memory_uow_factory()
    period = BillingPeriod.starting(2026, 6)
    with factory() as uow:
        uow.expenditures.add(expenditure("R1", date(2026, 6, 21)))
        uow.commit()

    PrepareBillUseCase(factory)(period)
    bill = ReviewBillLineUseCase(factory)("2026-06", "R1", "groceries", even_split())

    assert bill.lines[0].category_id == "groceries"
    assert bill.lines[0].allocation == even_split()
    with factory() as uow:
        stored = uow.bills.get("2026-06")
    assert stored == bill


def test_get_bill_summary_calculates_settlement_totals() -> None:
    factory = memory_uow_factory()
    period = BillingPeriod.starting(2026, 6)
    with factory() as uow:
        uow.expenditures.add(expenditure("R1", date(2026, 6, 21), "10.00"))
        uow.expenditures.add(expenditure("R2", date(2026, 6, 22), "30.00"))
        uow.commit()
    PrepareBillUseCase(factory)(period)
    ReviewBillLineUseCase(factory)("2026-06", "R1", "groceries", even_split())
    ReviewBillLineUseCase(factory)("2026-06", "R2", "rent", weighted_split())

    summary = GetBillSummaryUseCase(factory)("2026-06")

    assert summary.total == Decimal("40.00")
    assert {
        total.participant_id: total.amount for total in summary.participant_totals
    } == {
        "jonas": Decimal("12.50"),
        "partner": Decimal("27.50"),
    }
    assert {total.category_id: total.amount for total in summary.category_totals} == {
        "groceries": Decimal("10.00"),
        "rent": Decimal("30.00"),
    }
    assert summary.unhandled_count == 0


def test_close_bill_persists_closed_status(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze_today(monkeypatch)
    factory = memory_uow_factory()
    period = BillingPeriod.starting(2026, 6)
    with factory() as uow:
        uow.expenditures.add(expenditure("R1", date(2026, 6, 21)))
        uow.commit()
    PrepareBillUseCase(factory)(period)
    ReviewBillLineUseCase(factory)("2026-06", "R1", "groceries", even_split())

    bill = CloseBillUseCase(factory)("2026-06")

    assert bill.status == BillStatus.CLOSED
    with factory() as uow:
        assert uow.bills.get("2026-06") == bill


def test_prepare_bill_rejects_late_transaction_for_closed_period(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    freeze_today(monkeypatch)
    factory = memory_uow_factory()
    period = BillingPeriod.starting(2026, 6)
    with factory() as uow:
        uow.expenditures.add(expenditure("R1", date(2026, 6, 21)))
        uow.commit()
    PrepareBillUseCase(factory)(period)
    ReviewBillLineUseCase(factory)("2026-06", "R1", "groceries", even_split())
    CloseBillUseCase(factory)("2026-06")

    with factory() as uow:
        uow.expenditures.add(expenditure("R2", date(2026, 6, 25)))
        uow.commit()

    with pytest.raises(BillClosed):
        PrepareBillUseCase(factory)(period)


def test_detect_late_transactions_returns_missing_closed_period_expenditures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    freeze_today(monkeypatch)
    factory = memory_uow_factory()
    period = BillingPeriod.starting(2026, 6)
    with factory() as uow:
        uow.expenditures.add(expenditure("R1", date(2026, 6, 21), "10.00"))
        uow.commit()
    PrepareBillUseCase(factory)(period)
    ReviewBillLineUseCase(factory)("2026-06", "R1", "groceries", even_split())
    CloseBillUseCase(factory)("2026-06")
    late = expenditure("R2", date(2026, 6, 25), "12.00")
    with factory() as uow:
        uow.expenditures.add(late)
        uow.commit()

    assert DetectLateTransactionsUseCase(factory)("2026-06") == (late,)


def test_get_bill_for_review_includes_summary_and_late_transactions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    freeze_today(monkeypatch)
    factory = memory_uow_factory()
    period = BillingPeriod.starting(2026, 6)
    with factory() as uow:
        uow.expenditures.add(expenditure("R1", date(2026, 6, 21), "10.00"))
        uow.commit()
    PrepareBillUseCase(factory)(period)
    ReviewBillLineUseCase(factory)("2026-06", "R1", "groceries", even_split())
    CloseBillUseCase(factory)("2026-06")
    late = expenditure("R2", date(2026, 6, 25), "12.00")
    with factory() as uow:
        uow.expenditures.add(late)
        uow.commit()

    review = GetBillForReviewUseCase(factory)("2026-06")

    assert review.bill.id == "2026-06"
    assert review.summary.total == Decimal("10.00")
    assert review.unhandled_count == 0
    assert review.late_transactions == (late,)
    assert review.late_transaction_count == 1


def freeze_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        bill_usecases,
        "now",
        lambda: datetime(2026, 7, 2, 12, tzinfo=UTC),
    )


def even_split() -> Allocation:
    return Allocation(
        shares=(
            ParticipantShare(participant_id="jonas", basis_points=5_000),
            ParticipantShare(participant_id="partner", basis_points=5_000),
        )
    )


def weighted_split() -> Allocation:
    return Allocation(
        shares=(
            ParticipantShare(participant_id="jonas", basis_points=2_500),
            ParticipantShare(participant_id="partner", basis_points=7_500),
        )
    )


def expenditure(
    reference: str,
    transaction_date: date,
    amount: str = "10.00",
) -> Expenditure:
    return Expenditure(
        transaction_date=transaction_date,
        description="Purchase",
        card_member="Card Member",
        account_number="12345",
        amount=Decimal(amount),
        reference=reference,
    )
