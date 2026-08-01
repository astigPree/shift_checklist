"""Shared Kivy screen helpers for services and recoverable dialogs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from kivy.app import App
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen


class ServiceScreen(Screen):
    """Base screen with access to the application's explicit service registry."""

    def service(self, name: str) -> Any:
        app = App.get_running_app()
        if app is None or not hasattr(app, "services"):
            raise RuntimeError("application services are not available")
        return app.services.get(name)

    def refresh_all(self) -> None:
        """Refresh every initialized screen after a persisted mutation."""

        app = App.get_running_app()
        if app is not None and hasattr(app, "refresh_screens"):
            app.refresh_screens()

    def show_message(self, title: str, message: str) -> Popup:
        return show_message(title, message)

    def show_confirmation(
        self,
        title: str,
        message: str,
        on_confirm: Callable[[], None],
    ) -> Popup:
        return show_confirmation(title, message, on_confirm)


def _dialog_label(message: str) -> Label:
    return Label(
        text=message,
        halign="left",
        valign="middle",
        text_size=(dp(420), None),
        color=(0.92, 0.95, 1, 1),
    )


def show_message(title: str, message: str) -> Popup:
    """Show a readable non-fatal error/information popup."""

    content = BoxLayout(orientation="vertical", padding=dp(18), spacing=dp(12))
    content.add_widget(_dialog_label(message))
    close_button = Button(text="Close", size_hint_y=None, height=dp(44))
    content.add_widget(close_button)
    popup = Popup(
        title=title,
        content=content,
        size_hint=(None, None),
        size=(dp(500), dp(260)),
        auto_dismiss=False,
    )
    close_button.bind(on_release=popup.dismiss)
    popup.open()
    return popup


def show_confirmation(
    title: str,
    message: str,
    on_confirm: Callable[[], None],
) -> Popup:
    """Show a two-action confirmation and invoke the callback only on approval."""

    content = BoxLayout(orientation="vertical", padding=dp(18), spacing=dp(12))
    content.add_widget(_dialog_label(message))
    actions = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))
    cancel_button = Button(text="Cancel")
    confirm_button = Button(text="Confirm")
    actions.add_widget(cancel_button)
    actions.add_widget(confirm_button)
    content.add_widget(actions)
    popup = Popup(
        title=title,
        content=content,
        size_hint=(None, None),
        size=(dp(520), dp(280)),
        auto_dismiss=False,
    )

    def confirm(_button: Button) -> None:
        popup.dismiss()
        on_confirm()

    cancel_button.bind(on_release=popup.dismiss)
    confirm_button.bind(on_release=confirm)
    popup.open()
    return popup
