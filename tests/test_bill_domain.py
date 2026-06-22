from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from domain.entity import (
    Allocation,
    Bill,
    BillingPeriod,
    CategoryTotal,
    Expenditure,
    ParticipantTotal,
    ParticipantShare,
)
from domain.error import (
    BillClosed,
    BillLinePeriodMismatch,
    BillPeriodOpen,
    InvalidAllocation,
    InvalidCategory,
    UnhandledBillLines,
)
from domain.value import BillStatus


def test_billing_period_starts_on_second_day() -> None:
    assert BillingPeriod.for_date(date(2026, 6, 1)) == BillingPeriod(
        start_date=date(2026, 5, 2),
        end_date=date(2026, 6, 1),
    )
    assert BillingPeriod.for_date(date(2026, 6, 2)) == BillingPeriod(
        start_date=date(2026, 6, 2),
        end_date=date(2026, 7, 1),
    )
    assert BillingPeriod.for_date(date(2026, 7, 1)) == BillingPeriod(
        start_date=date(2026, 6, 2),
        end_date=date(2026, 7, 1),
    )


def test_allocation_requires_exactly_full_split() -> None:
    with pytest.raises(InvalidAllocation):
        Allocation(
            shares=(
                ParticipantShare(participant_id="jonas", basis_points=6_000),
                ParticipantShare(participant_id="partner", basis_points=3_000),
            )
        )


def test_bill_line_is_handled_after_category_and_allocation() -> None:
    bill = Bill.open(BillingPeriod.starting(2026, 6)).add(
        expenditure("R1", date(2026, 6, 21))
    )

    assert bill.lines[0].handled is False

    bill = bill.review("R1", "groceries", even_split())

    assert bill.lines[0].handled is True


def test_bill_line_requires_category_when_reviewed() -> None:
    bill = Bill.open(BillingPeriod.starting(2026, 6)).add(
        expenditure("R1", date(2026, 6, 21))
    )

    with pytest.raises(InvalidCategory):
        bill.review("R1", "", even_split())


def test_bill_rejects_expenditure_outside_period() -> None:
    bill = Bill.open(BillingPeriod.starting(2026, 6))

    with pytest.raises(BillLinePeriodMismatch):
        bill.add(expenditure("R1", date(2026, 7, 2)))


def test_bill_cannot_close_before_period_is_over() -> None:
    bill = handled_bill()

    with pytest.raises(BillPeriodOpen):
        bill.close(
            date(2026, 7, 1),
            datetime(2026, 7, 1, 12, tzinfo=UTC),
        )


def test_bill_cannot_close_with_unhandled_lines() -> None:
    bill = Bill.open(BillingPeriod.starting(2026, 6)).add(
        expenditure("R1", date(2026, 6, 21))
    )

    with pytest.raises(UnhandledBillLines):
        bill.close(
            date(2026, 7, 2),
            datetime(2026, 7, 2, 12, tzinfo=UTC),
        )


def test_closed_bill_rejects_new_transaction() -> None:
    bill = handled_bill().close(
        date(2026, 7, 2),
        datetime(2026, 7, 2, 12, tzinfo=UTC),
    )

    assert bill.status == BillStatus.CLOSED
    with pytest.raises(BillClosed):
        bill.add(expenditure("R2", date(2026, 6, 25)))


def test_bill_summary_calculates_settlement_totals() -> None:
    bill = Bill.open(BillingPeriod.starting(2026, 6))
    bill = bill.add(expenditure("R1", date(2026, 6, 10), "10.00"))
    bill = bill.add(expenditure("R2", date(2026, 6, 11), "30.00"))
    bill = bill.add(expenditure("R3", date(2026, 6, 12), "5.00"))
    bill = bill.review("R1", "groceries", even_split())
    bill = bill.review("R2", "rent", weighted_split())

    summary = bill.summary()

    assert summary.bill_id == "2026-06"
    assert summary.total == Decimal("45.00")
    assert summary.participant_totals == (
        ParticipantTotal(participant_id="jonas", amount=Decimal("12.50")),
        ParticipantTotal(participant_id="partner", amount=Decimal("27.50")),
    )
    assert summary.category_totals == (
        CategoryTotal(category_id="groceries", amount=Decimal("10.00")),
        CategoryTotal(category_id="rent", amount=Decimal("30.00")),
    )
    assert summary.unhandled_count == 1


def test_bill_summary_distributes_rounding_to_exact_cents() -> None:
    bill = Bill.open(BillingPeriod.starting(2026, 6))
    bill = bill.add(expenditure("R1", date(2026, 6, 10), "0.01"))
    bill = bill.review("R1", "groceries", even_split())

    summary = bill.summary()

    assert summary.total == Decimal("0.01")
    assert sum(total.amount for total in summary.participant_totals) == Decimal("0.01")


def handled_bill() -> Bill:
    bill = Bill.open(BillingPeriod.starting(2026, 6)).add(
        expenditure("R1", date(2026, 6, 21))
    )
    return bill.review("R1", "groceries", even_split())


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
