from __future__ import annotations

from datetime import date
from decimal import Decimal
from functools import partial

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from domain.entity import (
    Allocation,
    Bill,
    BillingPeriod,
    Expenditure,
    ParticipantShare,
)
from infrastructure.config import OutboxSettings
from infrastructure.persistence.database import Base
from infrastructure.persistence.uow import SqlUnitOfWork


def test_bill_repository_round_trips_bill_with_lines() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = partial(SqlUnitOfWork, sessionmaker(bind=engine), OutboxSettings())
    bill = Bill.open(BillingPeriod.starting(2026, 6)).add(
        expenditure("R1", date(2026, 6, 21))
    )
    bill = bill.review("R1", "groceries", even_split())

    with factory() as uow:
        uow.bills.add(bill)
        uow.commit()

    with factory() as uow:
        assert uow.bills.get("2026-06") == bill
        assert uow.bills.for_period(BillingPeriod.starting(2026, 6)) == bill
        assert uow.bills.list() == [bill]


def even_split() -> Allocation:
    return Allocation(
        shares=(
            ParticipantShare(participant_id="jonas", basis_points=5_000),
            ParticipantShare(participant_id="partner", basis_points=5_000),
        )
    )


def expenditure(reference: str, transaction_date: date) -> Expenditure:
    return Expenditure(
        transaction_date=transaction_date,
        description="Purchase",
        card_member="Card Member",
        account_number="12345",
        amount=Decimal("10.00"),
        reference=reference,
    )
