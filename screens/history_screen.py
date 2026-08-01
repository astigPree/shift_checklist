"""Read-only shift summaries and occurrence snapshots."""

from __future__ import annotations

from functools import partial

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from constants import TaskType
from screens.base import ServiceScreen


def _time_text(value: object | None) -> str:
    if value is None:
        return "—"
    return value.strftime("%I:%M %p").lstrip("0")


class HistoryScreen(ServiceScreen):
    """Display immutable records from earlier shifts, newest first."""

    summary_text = StringProperty("Closed shifts are shown newest first.")

    def on_pre_enter(self, *_args: object) -> None:
        Clock.schedule_once(lambda _elapsed: self.refresh(), 0)

    def refresh(self) -> None:
        if "history_list" not in self.ids:
            return
        try:
            summaries = self.service("history").list_summaries()
            self.summary_text = f"{len(summaries)} closed shift record(s)"
            target = self.ids.history_list
            target.clear_widgets()
            if not summaries:
                target.add_widget(
                    Label(
                        text=(
                            "No closed shifts yet. The current shift will appear here "
                            "after its reset boundary."
                        ),
                        color=(0.66, 0.73, 0.83, 1),
                        size_hint_y=None,
                        height=dp(82),
                    )
                )
                return
            for summary in summaries:
                text = (
                    f"{summary.shift_date.strftime('%A, %B %d, %Y')}\n"
                    f"{summary.completed}/{summary.total} completed · "
                    f"{summary.missed} missed · {summary.message_checks} message checks · "
                    f"Shopify {summary.shopify_completed}/{summary.shopify_total}"
                )
                button = Button(
                    text=text,
                    halign="left",
                    valign="middle",
                    size_hint_y=None,
                    height=dp(82),
                    padding=(dp(16), dp(8)),
                )
                button.bind(size=lambda widget, value: setattr(widget, "text_size", value))
                button.bind(on_release=partial(self.open_detail, summary.shift_date))
                target.add_widget(button)
        except Exception as error:
            self.show_message("Could not load history", str(error))

    def open_detail(self, shift_date: object, *_args: object) -> Popup:
        try:
            detail = self.service("history").get_shift_detail(shift_date)
        except Exception as error:
            return self.show_message("Shift history is unavailable", str(error))

        content = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(8),
            padding=(dp(14), dp(10)),
        )
        content.bind(minimum_height=content.setter("height"))
        if not detail.record.occurrences:
            content.add_widget(self._detail_label("No task snapshots in this shift."))
        for occurrence in detail.record.occurrences:
            scheduled = _time_text(occurrence.scheduled_time)
            completed = _time_text(occurrence.completed_at)
            snapshot = (
                f"{occurrence.title}  [{occurrence.status.value.upper()}]\n"
                f"{occurrence.category} · scheduled {scheduled} · completed {completed}"
            )
            if occurrence.task_type is TaskType.SHOPIFY and occurrence.shopify_details:
                details = occurrence.shopify_details
                snapshot += (
                    f"\nShopify · {details.store_name} · {details.priority.value} · "
                    f"{details.status.value}"
                )
            content.add_widget(self._detail_label(snapshot))

        content.add_widget(
            self._section_label(f"Client-message checks ({len(detail.message_checks)})")
        )
        if not detail.message_checks:
            content.add_widget(self._detail_label("No message checks recorded."))
        for check in detail.message_checks:
            note = f" · {check.note}" if check.note else ""
            content.add_widget(
                self._detail_label(f"{_time_text(check.checked_at)}{note}")
            )

        scroll = ScrollView()
        scroll.add_widget(content)
        popup = Popup(
            title=f"Shift snapshot · {detail.record.shift_date.isoformat()}",
            content=scroll,
            size_hint=(0.82, 0.86),
        )
        popup.open()
        return popup

    @staticmethod
    def _detail_label(text: str) -> Label:
        label = Label(
            text=text,
            color=(0.88, 0.92, 0.98, 1),
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(66),
        )
        label.bind(size=lambda widget, value: setattr(widget, "text_size", value))
        return label

    @staticmethod
    def _section_label(text: str) -> Label:
        label = HistoryScreen._detail_label(text)
        label.bold = True
        label.height = dp(44)
        return label
