"""Today's active shift checklist, progress, and client-message controls."""

from __future__ import annotations

from datetime import datetime, timedelta

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import BooleanProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from constants import LiveTaskState, ShopifyStatus, TaskStatus, TaskType
from screens.base import ServiceScreen
from widgets import TaskItem

STATE_PRESENTATION = {
    LiveTaskState.PENDING: ("PENDING", (0.43, 0.57, 0.72, 1)),
    LiveTaskState.UPCOMING: ("UPCOMING", (0.31, 0.62, 0.92, 1)),
    LiveTaskState.DUE: ("DUE NOW", (0.98, 0.68, 0.25, 1)),
    LiveTaskState.OVERDUE: ("OVERDUE", (0.94, 0.31, 0.33, 1)),
    LiveTaskState.COMPLETED: ("COMPLETED", (0.25, 0.72, 0.46, 1)),
    LiveTaskState.MISSED: ("MISSED", (0.65, 0.35, 0.38, 1)),
}


def format_clock(value: datetime | None) -> str:
    if value is None:
        return "Not yet"
    return value.strftime("%b %d, %I:%M %p").replace(" 0", " ")


class TodayScreen(ServiceScreen):
    """Display and mutate the active shift without owning business rules."""

    clock_text = StringProperty("")
    shift_text = StringProperty("Active shift")
    message_status = StringProperty("No client-message check recorded this shift.")
    next_reminder_text = StringProperty("Next reminder: calculating…")
    overdue_text = StringProperty("No overdue tasks.")
    banner_text = StringProperty("")
    banner_visible = BooleanProperty(False)

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._clock_event = None
        self._last_refresh_minute: tuple[int, int, int, int, int] | None = None
        self._banner_event = None

    def on_pre_enter(self, *_args: object) -> None:
        Clock.schedule_once(lambda _elapsed: self.refresh(), 0)

    def on_enter(self, *_args: object) -> None:
        if self._clock_event is None:
            self._clock_event = Clock.schedule_interval(self._tick, 1)
        self._tick(0)

    def on_leave(self, *_args: object) -> None:
        if self._clock_event is not None:
            self._clock_event.cancel()
            self._clock_event = None

    def _tick(self, _elapsed: float) -> None:
        current = self.service("shift").now()
        self.clock_text = current.strftime("%A, %B %d · %I:%M:%S %p").replace(
            " 0", " "
        )
        minute_key = (
            current.year,
            current.month,
            current.day,
            current.hour,
            current.minute,
        )
        if self._last_refresh_minute != minute_key:
            self._last_refresh_minute = minute_key
            self.refresh()

    def refresh(self) -> None:
        if "task_list" not in self.ids:
            return
        try:
            shift = self.service("shift")
            tasks = self.service("tasks")
            messages = self.service("messages")
            current = shift.now()
            record = shift.ensure_current_shift(at=current)
            views = tasks.list_occurrences(at=current)
            self.shift_text = f"Active shift · {record.shift_date.strftime('%A, %B %d, %Y')}"
            self.ids.task_list.clear_widgets()

            counts = {state: 0 for state in LiveTaskState}
            for view in views:
                counts[view.state] += 1
                self.ids.task_list.add_widget(self._task_item(view))
            if not views:
                self.ids.task_list.add_widget(
                    Label(
                        text="No tasks for this shift. Use Add task to create one.",
                        color=(0.66, 0.73, 0.83, 1),
                        size_hint_y=None,
                        height=dp(72),
                    )
                )

            self.ids.progress_card.set_counts(
                completed=counts[LiveTaskState.COMPLETED],
                total=len(views),
                overdue=counts[LiveTaskState.OVERDUE],
                upcoming=counts[LiveTaskState.UPCOMING] + counts[LiveTaskState.DUE],
            )
            latest = messages.latest_for_shift(record.shift_date)
            if latest is None:
                self.message_status = (
                    "No check recorded · next reminder "
                    f"{format_clock(messages.next_reminder(at=current))}"
                )
            else:
                self.message_status = (
                    f"Last checked {format_clock(latest.checked_at)} · "
                    f"next {format_clock(latest.next_check_at)}"
                )
            self.next_reminder_text = self._next_reminder_text(views, current)
            overdue = [view for view in views if view.state is LiveTaskState.OVERDUE]
            if overdue:
                urgent = min(overdue, key=lambda view: view.due_at or current)
                self.overdue_text = f"Needs attention: {urgent.occurrence.title}"
            else:
                self.overdue_text = "No overdue tasks."
        except Exception as error:
            self.show_message("Could not refresh Today", str(error))

    def _task_item(self, view: object) -> TaskItem:
        occurrence = view.occurrence
        state_label, state_color = STATE_PRESENTATION[view.state]
        scheduled = (
            occurrence.scheduled_time.strftime("%I:%M %p").lstrip("0")
            if occurrence.scheduled_time is not None
            else "Any time"
        )
        reminder = " · reminder on" if occurrence.reminder_enabled else ""
        shopify = ""
        secondary = ""
        if occurrence.task_type is TaskType.SHOPIFY and occurrence.shopify_details:
            shopify = (
                f" · {occurrence.shopify_details.store_name}"
                f" · {occurrence.shopify_details.status.value}"
            )
            secondary = "Change status"
        notes = occurrence.notes.strip()
        return TaskItem(
            occurrence_id=occurrence.id,
            title_text=occurrence.title,
            detail_text=f"{occurrence.category} · {scheduled}{reminder}{shopify}",
            state_text=state_label,
            state_color=state_color,
            notes_text=notes if notes else "No notes",
            action_text=(
                "Reopen"
                if occurrence.status is TaskStatus.COMPLETED
                else "Complete"
            ),
            secondary_text=secondary,
            action_callback=self.toggle_completion,
            secondary_callback=self.open_shopify_status,
        )

    def _next_reminder_text(self, views: list[object], current: datetime) -> str:
        candidates: list[tuple[datetime, str]] = []
        for view in views:
            occurrence = view.occurrence
            if (
                occurrence.status is not TaskStatus.PENDING
                or not occurrence.reminder_enabled
                or view.due_at is None
            ):
                continue
            pre_due = view.due_at - timedelta(minutes=occurrence.reminder_lead_minutes)
            if not occurrence.pre_due_reminder_fired and pre_due >= current:
                candidates.append((pre_due, f"Upcoming: {occurrence.title}"))
            elif not occurrence.due_reminder_fired and view.due_at >= current:
                candidates.append((view.due_at, f"Due: {occurrence.title}"))
        client_due = self.service("messages").next_reminder(at=current)
        if client_due >= current:
            candidates.append((client_due, "Check client messages"))
        if not candidates:
            return "Next reminder: none scheduled"
        when, label = min(candidates, key=lambda item: item[0])
        return f"Next reminder · {format_clock(when)} · {label}"

    def toggle_completion(self, occurrence_id: str) -> None:
        try:
            occurrence = next(
                view.occurrence
                for view in self.service("tasks").list_occurrences()
                if view.occurrence.id == occurrence_id
            )
            if occurrence.status is TaskStatus.COMPLETED:
                self.service("tasks").reopen_occurrence(occurrence_id)
            else:
                self.service("tasks").complete_occurrence(occurrence_id)
            self.refresh_all()
        except Exception as error:
            self.show_message("Task could not be updated", str(error))

    def open_message_check(self) -> Popup:
        content = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))
        content.add_widget(
            Label(
                text="Optional note (stored only on this computer)",
                color=(0.92, 0.95, 1, 1),
                size_hint_y=None,
                height=dp(34),
            )
        )
        note = TextInput(multiline=True, hint_text="Note", size_hint_y=None, height=dp(100))
        content.add_widget(note)
        actions = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))
        cancel = Button(text="Cancel")
        save = Button(text="Record check")
        actions.add_widget(cancel)
        actions.add_widget(save)
        content.add_widget(actions)
        popup = Popup(
            title="Client Messages Checked",
            content=content,
            size_hint=(None, None),
            size=(dp(520), dp(300)),
            auto_dismiss=False,
        )
        cancel.bind(on_release=popup.dismiss)

        def record(_button: Button) -> None:
            try:
                self.service("messages").record_check(note.text)
                popup.dismiss()
                self.refresh_all()
            except Exception as error:
                self.show_message("Check could not be recorded", str(error))

        save.bind(on_release=record)
        popup.open()
        return popup

    def open_shopify_status(self, occurrence_id: str) -> Popup:
        occurrence = next(
            view.occurrence
            for view in self.service("tasks").list_occurrences()
            if view.occurrence.id == occurrence_id
        )
        current_status = occurrence.shopify_details.status.value
        content = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))
        status = Spinner(
            text=current_status,
            values=[item.value for item in ShopifyStatus],
            size_hint_y=None,
            height=dp(44),
        )
        content.add_widget(status)
        save = Button(text="Save status", size_hint_y=None, height=dp(44))
        content.add_widget(save)
        popup = Popup(
            title=f"Shopify · {occurrence.title}",
            content=content,
            size_hint=(None, None),
            size=(dp(460), dp(220)),
            auto_dismiss=False,
        )

        def apply(_button: Button) -> None:
            try:
                self.service("tasks").set_shopify_status(occurrence_id, status.text)
                popup.dismiss()
                self.refresh_all()
            except Exception as error:
                self.show_message("Shopify status could not be updated", str(error))

        save.bind(on_release=apply)
        popup.open()
        return popup

    def open_add_task(self) -> None:
        if self.manager is None:
            return
        self.manager.current = "tasks"
        target = self.manager.get_screen("tasks")
        Clock.schedule_once(lambda _elapsed: target.open_add_form(), 0)

    def show_banner(self, event: object) -> None:
        self.banner_text = f"{event.title}: {event.message}"
        self.banner_visible = True
        if self._banner_event is not None:
            self._banner_event.cancel()
        self._banner_event = Clock.schedule_once(self._hide_banner, 12)

    def _hide_banner(self, _elapsed: float) -> None:
        self.banner_visible = False
        self._banner_event = None
