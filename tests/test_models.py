"""Unit tests for versioned domain model contracts."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from uuid import uuid4

import pytest

from constants import Priority, Recurrence, ShopifyStatus, TaskStatus, TaskType
from models import (
    AppSettings,
    DailyRecord,
    DailyRecordsDocument,
    MessageCheck,
    MessageChecksDocument,
    ModelValidationError,
    SettingsDocument,
    ShopifyDetails,
    TaskDocument,
    TaskOccurrence,
    TaskTemplate,
)

MANILA = timezone(timedelta(hours=8))
NOW = datetime(2026, 8, 1, 20, 0, tzinfo=MANILA)
SHIFT_DATE = date(2026, 8, 1)


def make_task(**changes: object) -> TaskTemplate:
    values: dict[str, object] = {
        "title": "Check client messages",
        "category": "Client Monitoring",
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(changes)
    return TaskTemplate(**values)  # type: ignore[arg-type]


def test_task_template_round_trip_preserves_values_and_unknown_fields() -> None:
    task = make_task(
        scheduled_time=time(4, 0),
        reminder_enabled=True,
        extra={"future_option": {"enabled": True}},
    )

    restored = TaskTemplate.from_dict(task.to_dict())

    assert restored == task
    assert restored.to_dict()["future_option"] == {"enabled": True}
    assert restored.to_dict()["scheduled_time"] == "04:00"
    assert restored.to_dict()["created_at"].endswith("+08:00")


def test_one_time_task_requires_target_shift_date() -> None:
    with pytest.raises(ModelValidationError, match="require.*target_shift_date"):
        make_task(recurrence=Recurrence.ONE_TIME)


def test_daily_task_rejects_target_shift_date() -> None:
    with pytest.raises(ModelValidationError, match="daily tasks cannot"):
        make_task(target_shift_date=SHIFT_DATE)


def test_reminder_requires_scheduled_time() -> None:
    with pytest.raises(ModelValidationError, match="reminders require"):
        make_task(reminder_enabled=True)


@pytest.mark.parametrize(
    ("field_name", "field_value", "message"),
    [
        ("title", " ", "cannot be blank"),
        ("id", "not-a-uuid", "valid UUID"),
        ("reminder_lead_minutes", -1, "at least 0"),
        ("sort_order", -1, "at least 0"),
    ],
)
def test_task_rejects_invalid_core_fields(
    field_name: str, field_value: object, message: str
) -> None:
    with pytest.raises(ModelValidationError, match=message):
        make_task(**{field_name: field_value})


def test_task_from_dict_rejects_invalid_time_format() -> None:
    payload = make_task().to_dict()
    payload["scheduled_time"] = "4:00 AM"

    with pytest.raises(ModelValidationError, match="HH:MM"):
        TaskTemplate.from_dict(payload)


def test_shopify_task_requires_one_time_recurrence_and_details() -> None:
    with pytest.raises(ModelValidationError, match="shopify_details"):
        make_task(task_type=TaskType.SHOPIFY)

    details = ShopifyDetails(
        store_name="Example Store",
        description="Update home page banner",
        requested_at=NOW,
    )
    with pytest.raises(ModelValidationError, match="one-time"):
        make_task(task_type=TaskType.SHOPIFY, shopify_details=details)


def test_shopify_task_round_trip() -> None:
    details = ShopifyDetails(
        store_name="Example Store",
        description="Update home page banner",
        requested_at=NOW,
        priority=Priority.HIGH,
        extra={"future_reference": "request-42"},
    )
    task = make_task(
        title="Update banner",
        category="Shopify",
        recurrence=Recurrence.ONE_TIME,
        target_shift_date=SHIFT_DATE,
        task_type=TaskType.SHOPIFY,
        shopify_details=details,
    )

    restored = TaskTemplate.from_dict(task.to_dict())

    assert restored == task
    assert restored.shopify_details is not None
    assert restored.shopify_details.priority is Priority.HIGH
    assert restored.shopify_details.to_dict()["future_reference"] == "request-42"


def test_completed_shopify_status_requires_completion_time() -> None:
    with pytest.raises(ModelValidationError, match="completed_at is required"):
        ShopifyDetails(
            store_name="Example Store",
            description="Update banner",
            requested_at=NOW,
            status=ShopifyStatus.COMPLETED,
        )


def test_non_completed_shopify_status_rejects_completion_time() -> None:
    with pytest.raises(ModelValidationError, match="must be empty"):
        ShopifyDetails(
            store_name="Example Store",
            description="Update banner",
            requested_at=NOW,
            completed_at=NOW,
        )


def test_occurrence_is_an_independent_template_snapshot() -> None:
    template = make_task(title="Original")
    occurrence = TaskOccurrence.from_template(template, SHIFT_DATE)

    template.title = "Edited"

    assert occurrence.title == "Original"
    assert occurrence.template_id == template.id
    assert occurrence.shift_date == SHIFT_DATE


def test_completed_occurrence_requires_completion_time() -> None:
    template = make_task()
    occurrence = TaskOccurrence.from_template(template, SHIFT_DATE)
    payload = occurrence.to_dict()
    payload["status"] = TaskStatus.COMPLETED.value

    with pytest.raises(ModelValidationError, match="require.*completed_at"):
        TaskOccurrence.from_dict(payload)


def test_pending_occurrence_rejects_completion_time() -> None:
    template = make_task()
    occurrence = TaskOccurrence.from_template(template, SHIFT_DATE)
    payload = occurrence.to_dict()
    payload["completed_at"] = NOW.isoformat()

    with pytest.raises(ModelValidationError, match="must be empty"):
        TaskOccurrence.from_dict(payload)


def test_task_document_rejects_duplicate_ids() -> None:
    first = make_task()
    second = make_task(id=first.id, title="Duplicate ID")

    with pytest.raises(ModelValidationError, match="duplicate task IDs"):
        TaskDocument(tasks=[first, second])


def test_daily_record_round_trip_and_closed_property() -> None:
    occurrence = TaskOccurrence.from_template(make_task(), SHIFT_DATE)
    closed_at = NOW + timedelta(hours=16)
    record = DailyRecord(
        shift_date=SHIFT_DATE,
        opened_at=NOW,
        closed_at=closed_at,
        occurrences=[occurrence],
        extra={"future_summary": 1},
    )

    restored = DailyRecord.from_dict(record.to_dict())

    assert restored == record
    assert restored.is_closed
    assert restored.to_dict()["future_summary"] == 1


def test_daily_record_rejects_occurrence_from_another_shift() -> None:
    occurrence = TaskOccurrence.from_template(make_task(), date(2026, 8, 2))

    with pytest.raises(ModelValidationError, match="same shift_date"):
        DailyRecord(shift_date=SHIFT_DATE, opened_at=NOW, occurrences=[occurrence])


def test_daily_records_document_allows_only_one_open_record() -> None:
    records = [
        DailyRecord(shift_date=SHIFT_DATE, opened_at=NOW),
        DailyRecord(shift_date=date(2026, 8, 2), opened_at=NOW + timedelta(days=1)),
    ]

    with pytest.raises(ModelValidationError, match="only one.*open"):
        DailyRecordsDocument(records=records)


def test_message_check_round_trip() -> None:
    check = MessageCheck(
        id=str(uuid4()),
        shift_date=SHIFT_DATE,
        checked_at=NOW,
        next_check_at=NOW + timedelta(minutes=30),
        note="No new requests",
        extra={"future_source": "manual"},
    )

    restored = MessageCheck.from_dict(check.to_dict())

    assert restored == check
    assert restored.to_dict()["future_source"] == "manual"


def test_message_check_requires_later_next_time() -> None:
    with pytest.raises(ModelValidationError, match="must be after"):
        MessageCheck(
            shift_date=SHIFT_DATE,
            checked_at=NOW,
            next_check_at=NOW,
        )


def test_message_check_document_rejects_duplicate_ids() -> None:
    identifier = str(uuid4())
    checks = [
        MessageCheck(
            id=identifier,
            shift_date=SHIFT_DATE,
            checked_at=NOW,
            next_check_at=NOW + timedelta(minutes=30),
        ),
        MessageCheck(
            id=identifier,
            shift_date=SHIFT_DATE,
            checked_at=NOW + timedelta(hours=1),
            next_check_at=NOW + timedelta(minutes=90),
        ),
    ]

    with pytest.raises(ModelValidationError, match="duplicate message check IDs"):
        MessageChecksDocument(checks=checks)


def test_settings_missing_fields_receive_safe_defaults() -> None:
    document = SettingsDocument.from_dict(
        {"schema_version": 1, "settings": {}, "future_root": "preserved"}
    )

    assert document.settings.reset_time == time(12, 0)
    assert document.settings.client_check_interval_minutes == 30
    assert document.settings.categories
    assert document.to_dict()["future_root"] == "preserved"


@pytest.mark.parametrize(
    "changes",
    [
        {"client_check_interval_minutes": 0},
        {"default_reminder_lead_minutes": -1},
        {"categories": []},
        {"categories": ["General", " general "]},
    ],
)
def test_settings_reject_invalid_values(changes: dict[str, object]) -> None:
    with pytest.raises(ModelValidationError):
        AppSettings(**changes)  # type: ignore[arg-type]


def test_document_schema_must_be_current_after_migration() -> None:
    with pytest.raises(ModelValidationError, match="schema"):
        TaskDocument(schema_version=2)
