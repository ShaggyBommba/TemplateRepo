from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from application.app import App, get_app
from application.dto import GeneratedNote
from domain.entity import AnswerAssessment
from infrastructure.config import DatabaseSettings, Settings
from presentation.htmx.app import api


def build_app(tmp_path: Path) -> App:
    return App(
        Settings(
            database=DatabaseSettings(
                provider="sqlite",
                database=str(tmp_path / "bazzpara"),
            )
        )
    )


def test_delete_removes_dependent_study_state(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    document = app.create("SQLite cascades should remove all dependent state.")
    app.store_generated_notes(
        document.id,
        [
            GeneratedNote(
                question="What should deletion remove?",
                answer="All dependent study state.",
            )
        ],
    )

    prompt = app.start_review_session()
    assert prompt is not None
    app.record_review_assessment(
        prompt.card_id,
        AnswerAssessment(
            quality=5,
            correct=True,
            feedback="Correct.",
            confidence=1.0,
        ),
    )

    overview = app.review_overview()
    assert overview.documents == 1
    assert overview.notes == 1
    assert overview.cards == 1
    assert overview.attempts == 1
    assert app.document(document.id) is not None

    with app.uow_factory() as uow:
        assert uow.outbox.get_document_job(document.id) is not None

    deleted = app.delete_document(document.id)

    assert deleted is not None
    assert deleted.notes == 1
    assert deleted.cards == 1
    assert deleted.attempts == 1
    assert app.document(document.id) is None

    overview = app.review_overview()
    assert overview.documents == 0
    assert overview.notes == 0
    assert overview.cards == 0
    assert overview.attempts == 0

    with app.uow_factory() as uow:
        assert uow.outbox.get_document_job(document.id) is None


def test_htmx_list_detail_and_delete(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    document = app.create("HTMX should expose this source document.")
    app.store_generated_notes(
        document.id,
        [
            GeneratedNote(
                question="What should HTMX expose?",
                answer="The source document and its generated notes.",
            )
        ],
    )

    htmx_app = api()
    htmx_app.dependency_overrides[get_app] = lambda: app
    client = TestClient(htmx_app)

    index = client.get("/")
    assert index.status_code == 200
    assert document.id[:8] in index.text
    assert "HTMX should expose this source document." in index.text

    detail = client.get(f"/documents/{document.id}")
    assert detail.status_code == 200
    assert "The source document and its generated notes." in detail.text

    deleted = client.delete(f"/documents/{document.id}")
    assert deleted.status_code == 200
    assert "No documents stored yet." in deleted.text
    assert 'hx-swap-oob="true"' in deleted.text

    overview = app.review_overview()
    assert overview.documents == 0
    assert overview.notes == 0
    assert overview.cards == 0
