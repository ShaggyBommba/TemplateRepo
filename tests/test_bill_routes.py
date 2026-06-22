from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from application.dto import BillReview
from domain.entity import (
    Allocation,
    Bill,
    BillingPeriod,
    Expenditure,
    ParticipantShare,
)
from domain.error import UnhandledBillLines
from presentation.api.app import api
from presentation.api.routes.bills import (
    AllocationRequest,
    ParticipantShareRequest,
    PrepareBillRequest,
    ReviewBillLineRequest,
    bill as get_bill,
    bill_review,
    bill_summary,
    close_bill,
    late_transactions,
    prepare_bill,
    review_bill_line,
)


def test_api_includes_bill_routes() -> None:
    paths = api().openapi()["paths"]

    assert "/bills/prepare" in paths
    assert "/bills/{bill_id}" in paths
    assert "/bills/{bill_id}/review" in paths
    assert "/bills/{bill_id}/summary" in paths
    assert "/bills/{bill_id}/lines/{line_id}/review" in paths
    assert "/bills/{bill_id}/late-transactions" in paths
    assert "/bills/{bill_id}/close" in paths


def test_prepare_bill_endpoint_calls_usecase() -> None:
    app = FakeApp()

    response = prepare_bill(PrepareBillRequest(year=2026, month=6), app)

    assert response == app.bill
    assert app.prepared_period == BillingPeriod.starting(2026, 6)


def test_get_bill_endpoint_returns_bill() -> None:
    app = FakeApp()

    assert get_bill("2026-06", app) == app.bill


def test_get_bill_endpoint_returns_404_when_missing() -> None:
    app = FakeApp()
    app.bill = None

    with pytest.raises(HTTPException) as exc:
        get_bill("missing", app)

    assert exc.value.status_code == 404
    assert exc.value.detail["code"] == "bill.not_found"


def test_bill_review_endpoint_returns_review_model() -> None:
    app = FakeApp()

    response = bill_review("2026-06", app)

    assert response == app.review
    assert app.reviewed_bill_id == "2026-06"


def test_bill_summary_endpoint_returns_summary() -> None:
    app = FakeApp()

    response = bill_summary("2026-06", app)

    assert response == app.summary
    assert app.summarized_bill_id == "2026-06"


def test_review_bill_line_endpoint_converts_allocation() -> None:
    app = FakeApp()

    response = review_bill_line(
        "2026-06",
        "R1",
        ReviewBillLineRequest(
            category_id="groceries",
            allocation=AllocationRequest(
                shares=(
                    ParticipantShareRequest(
                        participant_id="jonas",
                        basis_points=5_000,
                    ),
                    ParticipantShareRequest(
                        participant_id="partner",
                        basis_points=5_000,
                    ),
                )
            ),
        ),
        app,
    )

    assert response == app.bill
    assert app.reviewed_line == ("2026-06", "R1", "groceries", even_split())


def test_review_bill_line_endpoint_maps_invalid_allocation() -> None:
    app = FakeApp()

    with pytest.raises(HTTPException) as exc:
        review_bill_line(
            "2026-06",
            "R1",
            ReviewBillLineRequest(
                category_id="groceries",
                allocation=AllocationRequest(
                    shares=(
                        ParticipantShareRequest(
                            participant_id="jonas",
                            basis_points=9_000,
                        ),
                    )
                ),
            ),
            app,
        )

    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "allocation.invalid"


def test_late_transactions_endpoint_returns_late_transactions() -> None:
    app = FakeApp()

    response = late_transactions("2026-06", app)

    assert response == app.late
    assert app.late_bill_id == "2026-06"


def test_close_bill_endpoint_maps_unhandled_lines_to_conflict() -> None:
    app = FakeApp()
    app.close_error = UnhandledBillLines("bill has unhandled lines: R1")

    with pytest.raises(HTTPException) as exc:
        close_bill("2026-06", app)

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "bill.unhandled_lines"


class FakeApp:
    def __init__(self) -> None:
        self.bill: Bill | None = reviewed_bill()
        self.summary = self.bill.summary()
        self.late = (expenditure("R2", date(2026, 6, 25), "12.00"),)
        self.review = BillReview(
            bill=self.bill,
            summary=self.summary,
            late_transactions=self.late,
        )
        self.close_error: Exception | None = None
        self.prepared_period: BillingPeriod | None = None
        self.reviewed_bill_id: str | None = None
        self.summarized_bill_id: str | None = None
        self.reviewed_line: tuple[str, str, str, Allocation] | None = None
        self.late_bill_id: str | None = None

    def prepare_bill(self, period: BillingPeriod) -> Bill | None:
        self.prepared_period = period
        return self.bill

    def get_bill(self, bill_id: str) -> Bill | None:
        return self.bill

    def get_bill_for_review(self, bill_id: str) -> BillReview:
        self.reviewed_bill_id = bill_id
        return self.review

    def get_bill_summary(self, bill_id: str):
        self.summarized_bill_id = bill_id
        return self.summary

    def review_bill_line(
        self,
        bill_id: str,
        line_id: str,
        category_id: str,
        allocation: Allocation,
    ) -> Bill | None:
        self.reviewed_line = (bill_id, line_id, category_id, allocation)
        return self.bill

    def detect_late_transactions(self, bill_id: str) -> tuple[Expenditure, ...]:
        self.late_bill_id = bill_id
        return self.late

    def close_bill(self, bill_id: str) -> Bill | None:
        if self.close_error is not None:
            raise self.close_error
        return self.bill


def reviewed_bill() -> Bill:
    bill = Bill.open(BillingPeriod.starting(2026, 6))
    bill = bill.add(expenditure("R1", date(2026, 6, 21), "10.00"))
    return bill.review("R1", "groceries", even_split())


def even_split() -> Allocation:
    return Allocation(
        shares=(
            ParticipantShare(participant_id="jonas", basis_points=5_000),
            ParticipantShare(participant_id="partner", basis_points=5_000),
        )
    )


def expenditure(
    reference: str,
    transaction_date: date,
    amount: str,
) -> Expenditure:
    return Expenditure(
        transaction_date=transaction_date,
        description="Purchase",
        card_member="Card Member",
        account_number="12345",
        amount=Decimal(amount),
        reference=reference,
    )
