"""Reusable shift progress card."""

from kivy.properties import NumericProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout


class ProgressCard(BoxLayout):
    """Display active shift completion and urgency totals."""

    completed = NumericProperty(0)
    total = NumericProperty(0)
    overdue = NumericProperty(0)
    upcoming = NumericProperty(0)
    summary_text = StringProperty("0 / 0 completed")

    def set_counts(
        self,
        *,
        completed: int,
        total: int,
        overdue: int,
        upcoming: int,
    ) -> None:
        self.completed = completed
        self.total = total
        self.overdue = overdue
        self.upcoming = upcoming
        self.summary_text = f"{completed} / {total} completed"
