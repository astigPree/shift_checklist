"""Reusable visual item for a task occurrence."""

from kivy.properties import ObjectProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout


class TaskItem(BoxLayout):
    """Render one occurrence and forward user actions to its owning screen."""

    occurrence_id = StringProperty("")
    title_text = StringProperty("")
    detail_text = StringProperty("")
    state_text = StringProperty("")
    notes_text = StringProperty("")
    action_text = StringProperty("Complete")
    secondary_text = StringProperty("")
    state_color = ObjectProperty((0.35, 0.55, 0.85, 1))
    action_callback = ObjectProperty(None, allownone=True)
    secondary_callback = ObjectProperty(None, allownone=True)

    def trigger_action(self) -> None:
        if self.action_callback is not None:
            self.action_callback(self.occurrence_id)

    def trigger_secondary(self) -> None:
        if self.secondary_callback is not None:
            self.secondary_callback(self.occurrence_id)
