"""Reusable task add/edit form and input conversion."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time

from kivy.properties import BooleanProperty, ListProperty
from kivy.uix.boxlayout import BoxLayout

from constants import Priority, Recurrence, ShopifyStatus, TaskType
from models import ShopifyDetails, TaskTemplate


def parse_time_text(value: str, *, required: bool = False) -> time | None:
    """Parse common 12/24-hour user input into a clock time."""

    normalized = value.strip()
    if not normalized:
        if required:
            raise ValueError("a time is required")
        return None
    for pattern in ("%H:%M", "%I:%M %p", "%I:%M%p"):
        try:
            return datetime.strptime(normalized.upper(), pattern).time()
        except ValueError:
            continue
    raise ValueError("use a time such as 04:00, 4:00 AM, or 16:00")


def parse_date_text(value: str) -> date:
    """Parse the task form's explicit ISO shift date."""

    try:
        return date.fromisoformat(value.strip())
    except ValueError as error:
        raise ValueError("use a shift date in YYYY-MM-DD format") from error


class TaskForm(BoxLayout):
    """Collect task fields while preserving input after validation failures."""

    categories = ListProperty([])
    shopify_enabled = BooleanProperty(False)
    submitting = BooleanProperty(False)

    def reset(self, *, categories: list[str], shopify: bool = False) -> None:
        self.categories = categories
        self.ids.title_input.text = ""
        self.ids.category_spinner.values = categories
        self.ids.category_spinner.text = "Shopify" if shopify else categories[0]
        self.ids.schedule_input.text = ""
        self.ids.reminder_check.active = False
        self.ids.lead_input.text = "5"
        self.ids.recurrence_spinner.text = "One time" if shopify else "Daily"
        self.ids.shift_date_input.text = date.today().isoformat() if shopify else ""
        self.ids.notes_input.text = ""
        self.ids.enabled_check.active = True
        self.ids.type_spinner.text = "Shopify" if shopify else "General"
        self.ids.store_input.text = ""
        self.ids.description_input.text = ""
        self.ids.requested_input.text = datetime.now().astimezone().strftime(
            "%Y-%m-%d %H:%M"
        )
        self.ids.priority_spinner.text = Priority.NORMAL.value
        self.ids.shopify_status_spinner.text = ShopifyStatus.PENDING.value
        self.shopify_enabled = shopify
        self.submitting = False

    def load_template(self, template: TaskTemplate, *, categories: list[str]) -> None:
        self.categories = categories
        self.ids.title_input.text = template.title
        self.ids.category_spinner.values = categories
        self.ids.category_spinner.text = template.category
        self.ids.schedule_input.text = (
            template.scheduled_time.strftime("%H:%M")
            if template.scheduled_time is not None
            else ""
        )
        self.ids.reminder_check.active = template.reminder_enabled
        self.ids.lead_input.text = str(template.reminder_lead_minutes)
        self.ids.recurrence_spinner.text = (
            "Daily" if template.recurrence is Recurrence.DAILY else "One time"
        )
        self.ids.shift_date_input.text = (
            template.target_shift_date.isoformat()
            if template.target_shift_date is not None
            else ""
        )
        self.ids.notes_input.text = template.notes
        self.ids.enabled_check.active = template.enabled
        self.ids.type_spinner.text = (
            "Shopify" if template.task_type is TaskType.SHOPIFY else "General"
        )
        self.shopify_enabled = template.task_type is TaskType.SHOPIFY
        if template.shopify_details is not None:
            details = template.shopify_details
            self.ids.store_input.text = details.store_name
            self.ids.description_input.text = details.description
            self.ids.requested_input.text = details.requested_at.strftime("%Y-%m-%d %H:%M")
            self.ids.priority_spinner.text = details.priority.value
            self.ids.shopify_status_spinner.text = details.status.value
        self.submitting = False

    def task_values(
        self,
        *,
        now: datetime,
        existing: TaskTemplate | None = None,
    ) -> dict[str, object]:
        """Validate UI values and return model-ready add/update fields."""

        title = self.ids.title_input.text.strip()
        if not title:
            self.ids.title_input.focus = True
            raise ValueError("title cannot be blank")
        category = self.ids.category_spinner.text.strip()
        if category not in self.categories:
            raise ValueError("choose a configured category")
        task_type = (
            TaskType.SHOPIFY
            if self.ids.type_spinner.text == "Shopify"
            else TaskType.GENERAL
        )
        recurrence = (
            Recurrence.ONE_TIME
            if self.ids.recurrence_spinner.text == "One time"
            else Recurrence.DAILY
        )
        if task_type is TaskType.SHOPIFY:
            recurrence = Recurrence.ONE_TIME
            category = "Shopify"
        target_shift_date = (
            parse_date_text(self.ids.shift_date_input.text)
            if recurrence is Recurrence.ONE_TIME
            else None
        )
        scheduled_time = parse_time_text(self.ids.schedule_input.text)
        reminder_enabled = self.ids.reminder_check.active
        if reminder_enabled and scheduled_time is None:
            raise ValueError("a scheduled time is required when reminders are enabled")
        try:
            lead_minutes = int(self.ids.lead_input.text.strip())
        except ValueError as error:
            raise ValueError("reminder lead must be a whole number") from error
        if lead_minutes < 0:
            raise ValueError("reminder lead cannot be negative")

        shopify_details = None
        if task_type is TaskType.SHOPIFY:
            shopify_details = self._shopify_details(now=now, existing=existing)
        return {
            "title": title,
            "category": category,
            "notes": self.ids.notes_input.text.strip(),
            "scheduled_time": scheduled_time,
            "reminder_enabled": reminder_enabled,
            "reminder_lead_minutes": lead_minutes,
            "recurrence": recurrence,
            "target_shift_date": target_shift_date,
            "enabled": self.ids.enabled_check.active,
            "task_type": task_type,
            "shopify_details": shopify_details,
        }

    def make_template(self, *, now: datetime) -> TaskTemplate:
        return TaskTemplate(created_at=now, updated_at=now, **self.task_values(now=now))

    def _shopify_details(
        self,
        *,
        now: datetime,
        existing: TaskTemplate | None,
    ) -> ShopifyDetails:
        requested_text = self.ids.requested_input.text.strip()
        try:
            requested_at = datetime.strptime(requested_text, "%Y-%m-%d %H:%M").replace(
                tzinfo=now.tzinfo
            )
        except ValueError as error:
            raise ValueError("Shopify requested time must use YYYY-MM-DD HH:MM") from error
        status = ShopifyStatus(self.ids.shopify_status_spinner.text)
        previous = existing.shopify_details if existing is not None else None
        completed_at = None
        if status is ShopifyStatus.COMPLETED:
            completed_at = (
                previous.completed_at
                if previous is not None and previous.completed_at is not None
                else now
            )
        details = ShopifyDetails(
            store_name=self.ids.store_input.text,
            description=self.ids.description_input.text,
            requested_at=requested_at,
            priority=Priority(self.ids.priority_spinner.text),
            status=status,
            completed_at=completed_at,
        )
        if previous is not None:
            details = replace(details, extra=previous.extra)
        return details
