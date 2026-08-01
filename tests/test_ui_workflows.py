"""In-process UI controller tests using the real KV widgets and local services."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from kivy.app import App
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from constants import Recurrence, ShopifyStatus, TaskStatus, TaskType, TimeFormat
from main import ShiftChecklistApp
from screens.base import ServiceScreen, show_confirmation, show_message
from widgets import TaskForm, TaskItem, parse_date_text, parse_time_text


@pytest.fixture
def ui_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(Popup, "open", lambda self, *args: self)
    monkeypatch.setattr(Popup, "dismiss", lambda self, *args: self)
    monkeypatch.setattr(
        ServiceScreen,
        "show_message",
        lambda self, title, message: (title, message),
    )
    app = ShiftChecklistApp(data_directory=tmp_path)
    app.root = app.build()
    storage = app.services.get("storage")
    storage.initialize_all()
    storage.mark_default_tasks_seeded()
    app.services.get("shift").ensure_current_shift()
    yield app
    if app._shift_rollover_event is not None:
        app._shift_rollover_event.cancel()
    if app._reminder_poll_event is not None:
        app._reminder_poll_event.cancel()
    App._running_app = None


def test_task_form_parsing_and_model_conversion(ui_app: ShiftChecklistApp) -> None:
    assert parse_time_text("") is None
    assert parse_time_text("4:05 AM").hour == 4
    assert parse_time_text("16:30").hour == 16
    assert parse_date_text("2026-08-01").year == 2026
    with pytest.raises(ValueError, match="time"):
        parse_time_text("later", required=True)
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        parse_date_text("tomorrow")

    form = TaskForm()
    settings = ui_app.services.get("settings").get()
    form.reset(categories=settings.categories)
    with pytest.raises(ValueError, match="title"):
        form.make_template(now=ui_app.services.get("shift").now())

    form.ids.title_input.text = "Prepare shift report"
    form.ids.category_spinner.text = "General"
    form.ids.schedule_input.text = "7:30 AM"
    form.ids.reminder_check.active = True
    form.ids.lead_input.text = "10"
    template = form.make_template(now=ui_app.services.get("shift").now())
    assert template.title == "Prepare shift report"
    assert template.scheduled_time.hour == 7
    assert template.recurrence is Recurrence.DAILY

    form.load_template(template, categories=settings.categories)
    assert form.ids.title_input.text == template.title
    form.ids.lead_input.text = "-1"
    with pytest.raises(ValueError, match="negative"):
        form.task_values(now=ui_app.services.get("shift").now(), existing=template)
    form.ids.lead_input.text = "ten"
    with pytest.raises(ValueError, match="whole number"):
        form.task_values(now=ui_app.services.get("shift").now(), existing=template)

    form.reset(categories=settings.categories, shopify=True)
    form.ids.title_input.text = "Update product copy"
    form.ids.store_input.text = "Example Store"
    form.ids.description_input.text = "Replace the hero copy"
    form.ids.shift_date_input.text = (
        ui_app.services.get("shift").current_shift_date().isoformat()
    )
    shopify = form.make_template(now=ui_app.services.get("shift").now())
    assert shopify.task_type is TaskType.SHOPIFY
    assert shopify.recurrence is Recurrence.ONE_TIME
    assert shopify.shopify_details.store_name == "Example Store"


def test_today_and_task_management_workflow(ui_app: ShiftChecklistApp) -> None:
    today = ui_app.root.get_screen("today")
    management = ui_app.root.get_screen("tasks")
    today.refresh()
    management.refresh()
    assert today.ids.progress_card.total == 0
    assert "No task" in management.ids.template_list.children[0].text

    settings = ui_app.services.get("settings").get()
    form = TaskForm()
    form.reset(categories=settings.categories)
    form.ids.title_input.text = "First task"
    form.ids.category_spinner.text = "General"
    management._save_form(form, None, Popup())

    second_form = TaskForm()
    second_form.reset(categories=settings.categories)
    second_form.ids.title_input.text = "Second task"
    second_form.ids.category_spinner.text = "General"
    management._save_form(second_form, None, Popup())
    templates = ui_app.services.get("tasks").list_templates()
    assert [item.title for item in templates] == ["First task", "Second task"]

    management.move_task(templates[1].id, -1)
    templates = ui_app.services.get("tasks").list_templates()
    assert [item.title for item in templates] == ["Second task", "First task"]
    management.toggle_enabled(templates[0].id, False)
    management.refresh()
    assert "DISABLED" in management.ids.template_list.children[-1].children[-1].children[-1].text

    enabled = next(item for item in ui_app.services.get("tasks").list_templates() if item.enabled)
    edit_form = TaskForm()
    edit_form.load_template(enabled, categories=settings.categories)
    edit_form.ids.title_input.text = "Edited first task"
    management._save_form(edit_form, enabled, Popup())
    assert any(
        item.title == "Edited first task"
        for item in ui_app.services.get("tasks").list_templates()
    )

    today.refresh()
    occurrence = ui_app.services.get("tasks").list_occurrences()[0].occurrence
    today.toggle_completion(occurrence.id)
    assert ui_app.services.get("tasks").list_occurrences()[0].state.value == "completed"
    today.toggle_completion(occurrence.id)
    assert ui_app.services.get("tasks").list_occurrences()[0].state.value == "pending"

    item = TaskItem(occurrence_id=occurrence.id)
    actions: list[str] = []
    item.action_callback = actions.append
    item.secondary_callback = actions.append
    item.trigger_action()
    item.trigger_secondary()
    assert actions == [occurrence.id, occurrence.id]

    ui_app.root.current = "today"
    today.open_add_task()
    assert ui_app.root.current == "tasks"
    management._delete(enabled.id)
    assert len(ui_app.services.get("tasks").list_templates()) == 1


def test_message_shopify_history_and_settings_ui(
    ui_app: ShiftChecklistApp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    today = ui_app.root.get_screen("today")
    management = ui_app.root.get_screen("tasks")
    settings_screen = ui_app.root.get_screen("settings")
    history = ui_app.root.get_screen("history")

    popup = today.open_message_check()
    note = next(
        widget for widget in popup.content.walk() if isinstance(widget, TextInput)
    )
    note.text = "All inboxes clear"
    record_button = next(
        widget
        for widget in popup.content.walk()
        if isinstance(widget, Button) and widget.text == "Record check"
    )
    record_button.dispatch("on_release")
    latest = ui_app.services.get("messages").latest_for_shift()
    assert latest.note == "All inboxes clear"

    form = TaskForm()
    configured = ui_app.services.get("settings").get()
    form.reset(categories=configured.categories, shopify=True)
    form.ids.title_input.text = "Update storefront"
    form.ids.store_input.text = "North Store"
    form.ids.description_input.text = "Publish approved banner"
    form.ids.shift_date_input.text = (
        ui_app.services.get("shift").current_shift_date().isoformat()
    )
    management._save_form(form, None, Popup())
    shopify_occurrence = ui_app.services.get("tasks").list_occurrences()[0].occurrence
    status_popup = today.open_shopify_status(shopify_occurrence.id)
    spinner = next(
        widget for widget in status_popup.content.walk() if isinstance(widget, Spinner)
    )
    spinner.text = ShopifyStatus.COMPLETED.value
    save_button = next(
        widget
        for widget in status_popup.content.walk()
        if isinstance(widget, Button) and widget.text == "Save status"
    )
    save_button.dispatch("on_release")
    completed = ui_app.services.get("tasks").list_occurrences()[0].occurrence
    assert completed.status is TaskStatus.COMPLETED

    settings_screen.refresh()
    settings_screen.ids.notifications_check.active = False
    settings_screen.ids.sound_check.active = False
    settings_screen.ids.client_interval_input.text = "45"
    settings_screen.ids.lead_input.text = "8"
    settings_screen.ids.time_format_spinner.text = TimeFormat.TWENTY_FOUR_HOUR.value
    settings_screen.save_settings()
    saved = ui_app.services.get("settings").get()
    assert saved.client_check_interval_minutes == 45
    assert saved.time_format is TimeFormat.TWENTY_FOUR_HOUR

    settings_screen.ids.category_input.text = "Reports"
    settings_screen.add_category()
    assert "Reports" in ui_app.services.get("settings").get().categories
    settings_screen.delete_category("Reports")
    assert "Reports" not in ui_app.services.get("settings").get().categories
    monkeypatch.setattr(
        ui_app.services.get("settings"), "open_data_directory", lambda: Path("data")
    )
    settings_screen.open_data_directory()

    records = ui_app.services.get("storage").load_daily_records()
    records.records[0].closed_at = ui_app.services.get("shift").now() + timedelta(seconds=1)
    ui_app.services.get("storage").save_daily_records(records)
    history.refresh()
    assert "1 closed" in history.summary_text
    detail_popup = history.open_detail(records.records[0].shift_date)
    assert "Shift snapshot" in detail_popup.title


def test_app_callbacks_and_dialog_helpers(ui_app: ShiftChecklistApp, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(ui_app, "refresh_screens", lambda: calls.append("refresh"))
    monkeypatch.setattr(
        ui_app,
        "reschedule_shift_boundary",
        lambda: calls.append("reschedule"),
    )
    ui_app._settings_changed()
    assert calls == ["reschedule", "refresh"]

    monkeypatch.setattr(ui_app.services.get("reminders"), "poll", lambda: [object()])
    ui_app._poll_reminders(0)
    assert calls[-1] == "refresh"

    message_popup = show_message("Notice", "Saved")
    assert message_popup.title == "Notice"
    confirmed: list[bool] = []
    confirm_popup = show_confirmation(
        "Confirm", "Continue?", lambda: confirmed.append(True)
    )
    confirm_button = next(
        widget
        for widget in confirm_popup.content.walk()
        if isinstance(widget, Button) and widget.text == "Confirm"
    )
    confirm_button.dispatch("on_release")
    assert confirmed == [True]


def test_failed_task_save_keeps_form_ready_for_correction(
    ui_app: ShiftChecklistApp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    management = ui_app.root.get_screen("tasks")
    form = TaskForm()
    form.reset(categories=ui_app.services.get("settings").get().categories)
    form.ids.title_input.text = "Keep this input"
    form.ids.category_spinner.text = "General"
    popup = Popup()
    dismissed: list[bool] = []
    monkeypatch.setattr(popup, "dismiss", lambda *args: dismissed.append(True))
    monkeypatch.setattr(
        ui_app.services.get("tasks"),
        "add_task",
        lambda _template: (_ for _ in ()).throw(OSError("disk unavailable")),
    )

    management._save_form(form, None, popup)

    assert form.ids.title_input.text == "Keep this input"
    assert form.submitting is False
    assert dismissed == []
