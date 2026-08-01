"""Application settings, categories, local storage, and About UI."""

from __future__ import annotations

from functools import partial

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner

from constants import APP_VERSION, TimeFormat
from screens.base import ServiceScreen
from services import CategoryInUseError, ResetTimeConfirmationRequired
from widgets import parse_time_text


class SettingsScreen(ServiceScreen):
    """Configure persisted settings and editable categories."""

    data_directory_text = StringProperty("")
    about_text = StringProperty(
        f"Shift Checklist {APP_VERSION} · Local-only: no account, cloud, or API access."
    )

    def on_pre_enter(self, *_args: object) -> None:
        Clock.schedule_once(lambda _elapsed: self.refresh(), 0)

    def refresh(self) -> None:
        if "notifications_check" not in self.ids:
            return
        try:
            settings = self.service("settings").get()
            self.ids.notifications_check.active = settings.notifications_enabled
            self.ids.sound_check.active = settings.sound_enabled
            self.ids.sound_path_input.text = settings.reminder_sound_path or ""
            self.ids.client_interval_input.text = str(
                settings.client_check_interval_minutes
            )
            self.ids.lead_input.text = str(settings.default_reminder_lead_minutes)
            self.ids.reset_time_input.text = settings.reset_time.strftime("%H:%M")
            self.ids.time_format_spinner.text = settings.time_format.value
            self.data_directory_text = str(self.service("storage").data_directory)
            self._render_categories(settings.categories)
        except Exception as error:
            self.show_message("Could not load settings", str(error))

    def save_settings(self, *, confirm_reset_change: bool = False) -> None:
        try:
            client_interval = int(self.ids.client_interval_input.text.strip())
            reminder_lead = int(self.ids.lead_input.text.strip())
            if client_interval < 1:
                raise ValueError("client-message interval must be at least 1 minute")
            if reminder_lead < 0:
                raise ValueError("default reminder lead cannot be negative")
            reset_time = parse_time_text(self.ids.reset_time_input.text, required=True)
            sound_path = self.ids.sound_path_input.text.strip() or None
            self.service("settings").update(
                notifications_enabled=self.ids.notifications_check.active,
                sound_enabled=self.ids.sound_check.active,
                reminder_sound_path=sound_path,
                client_check_interval_minutes=client_interval,
                default_reminder_lead_minutes=reminder_lead,
                reset_time=reset_time,
                time_format=TimeFormat(self.ids.time_format_spinner.text),
                confirm_reset_change=confirm_reset_change,
            )
            self.refresh_all()
            self.show_message("Settings saved", "Your changes are active and saved locally.")
        except ResetTimeConfirmationRequired as error:
            self.show_confirmation(
                "Change the active shift?",
                f"{error}\n\nPending tasks in the old shift will be finalized as missed.",
                lambda: self.save_settings(confirm_reset_change=True),
            )
        except Exception as error:
            self.show_message("Settings were not saved", str(error))

    def add_category(self) -> None:
        name = self.ids.category_input.text
        try:
            self.service("settings").add_category(name)
            self.ids.category_input.text = ""
            self.refresh_all()
        except Exception as error:
            self.show_message("Category was not added", str(error))

    def delete_category(self, name: str, *_args: object) -> None:
        try:
            self.service("settings").delete_category(name)
            self.refresh_all()
        except CategoryInUseError:
            self._replacement_dialog(name)
        except Exception as error:
            self.show_message("Category was not deleted", str(error))

    def _replacement_dialog(self, name: str) -> Popup:
        categories = [
            category
            for category in self.service("settings").get().categories
            if category != name
        ]
        content = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))
        content.add_widget(
            Label(
                text=(
                    f'"{name}" is used by one or more tasks. Choose a replacement '
                    "before deleting it."
                ),
                color=(0.92, 0.95, 1, 1),
                halign="left",
                text_size=(dp(420), None),
            )
        )
        replacement = Spinner(
            text=categories[0],
            values=categories,
            size_hint_y=None,
            height=dp(44),
        )
        content.add_widget(replacement)
        actions = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))
        cancel = Button(text="Cancel")
        replace_button = Button(text="Replace and delete")
        actions.add_widget(cancel)
        actions.add_widget(replace_button)
        content.add_widget(actions)
        popup = Popup(
            title="Replace category references",
            content=content,
            size_hint=(None, None),
            size=(dp(520), dp(300)),
            auto_dismiss=False,
        )
        cancel.bind(on_release=popup.dismiss)

        def apply(_button: Button) -> None:
            try:
                self.service("settings").delete_category(
                    name, replacement=replacement.text
                )
                popup.dismiss()
                self.refresh_all()
            except Exception as error:
                self.show_message("Category was not deleted", str(error))

        replace_button.bind(on_release=apply)
        popup.open()
        return popup

    def _render_categories(self, categories: list[str]) -> None:
        target = self.ids.category_list
        target.clear_widgets()
        for category in categories:
            row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
            label = Label(
                text=category,
                color=(0.88, 0.92, 0.98, 1),
                halign="left",
                valign="middle",
            )
            label.bind(size=lambda widget, value: setattr(widget, "text_size", value))
            delete = Button(text="Delete", size_hint_x=None, width=dp(88))
            delete.bind(on_release=partial(self.delete_category, category))
            row.add_widget(label)
            row.add_widget(delete)
            target.add_widget(row)

    def open_data_directory(self) -> None:
        try:
            self.service("settings").open_data_directory()
        except Exception as error:
            self.show_message("Data folder could not be opened", str(error))
