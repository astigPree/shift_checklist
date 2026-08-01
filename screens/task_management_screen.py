"""Task template CRUD, ordering, and Shopify task creation UI."""

from __future__ import annotations

from functools import partial

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup

from constants import Recurrence, TaskType
from screens.base import ServiceScreen
from widgets import TaskForm


class TaskManagementScreen(ServiceScreen):
    """Create, edit, disable, reorder, and confirm deletion of templates."""

    summary_text = StringProperty("Loading task templates…")

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._form_popup: Popup | None = None

    def on_pre_enter(self, *_args: object) -> None:
        Clock.schedule_once(lambda _elapsed: self.refresh(), 0)

    def refresh(self) -> None:
        if "template_list" not in self.ids:
            return
        try:
            templates = self.service("tasks").list_templates()
            enabled_count = sum(template.enabled for template in templates)
            self.summary_text = f"{len(templates)} templates · {enabled_count} enabled"
            target = self.ids.template_list
            target.clear_widgets()
            if not templates:
                target.add_widget(
                    Label(
                        text="No task templates. Add one to begin.",
                        color=(0.66, 0.73, 0.83, 1),
                        size_hint_y=None,
                        height=dp(72),
                    )
                )
                return
            for index, template in enumerate(templates):
                target.add_widget(self._template_row(template, index, len(templates)))
        except Exception as error:
            self.show_message("Could not load tasks", str(error))

    def _template_row(self, template: object, index: int, total: int) -> BoxLayout:
        row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(92),
            padding=(dp(14), dp(10)),
            spacing=dp(8),
        )
        info = BoxLayout(orientation="vertical", spacing=dp(3))
        title = template.title if template.enabled else f"{template.title} · DISABLED"
        title_label = Label(
            text=title,
            bold=True,
            color=(0.93, 0.96, 1, 1) if template.enabled else (0.55, 0.6, 0.68, 1),
            halign="left",
            valign="middle",
        )
        title_label.bind(size=lambda widget, value: setattr(widget, "text_size", value))
        schedule = (
            template.scheduled_time.strftime("%I:%M %p").lstrip("0")
            if template.scheduled_time
            else "Any time"
        )
        recurrence = (
            "Daily"
            if template.recurrence is Recurrence.DAILY
            else f"One time · {template.target_shift_date.isoformat()}"
        )
        kind = "Shopify" if template.task_type is TaskType.SHOPIFY else "General"
        detail_label = Label(
            text=f"{template.category} · {recurrence} · {schedule} · {kind}",
            color=(0.66, 0.73, 0.83, 1),
            halign="left",
            valign="middle",
            font_size="13sp",
        )
        detail_label.bind(size=lambda widget, value: setattr(widget, "text_size", value))
        info.add_widget(title_label)
        info.add_widget(detail_label)
        row.add_widget(info)

        for text, callback, disabled in (
            ("↑", partial(self.move_task, template.id, -1), index == 0),
            ("↓", partial(self.move_task, template.id, 1), index == total - 1),
            ("Edit", partial(self.open_edit_form, template.id), False),
            (
                "Disable" if template.enabled else "Enable",
                partial(self.toggle_enabled, template.id, not template.enabled),
                False,
            ),
            ("Delete", partial(self.confirm_delete, template.id, template.title), False),
        ):
            button = Button(text=text, size_hint_x=None, width=dp(76), disabled=disabled)
            button.bind(on_release=callback)
            row.add_widget(button)
        return row

    def open_add_form(self, *_args: object, shopify: bool = False) -> Popup:
        settings = self.service("settings").get()
        form = TaskForm()
        form.reset(categories=settings.categories, shopify=shopify)
        if shopify:
            form.ids.shift_date_input.text = (
                self.service("shift").current_shift_date().isoformat()
            )
        return self._open_form_popup(form, None)

    def open_shopify_form(self) -> Popup:
        return self.open_add_form(shopify=True)

    def open_edit_form(self, task_id: str, *_args: object) -> Popup:
        template = self._template(task_id)
        form = TaskForm()
        form.load_template(template, categories=self.service("settings").get().categories)
        return self._open_form_popup(form, template)

    def _open_form_popup(self, form: TaskForm, template: object | None) -> Popup:
        shell = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        shell.add_widget(form)
        actions = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(10))
        cancel = Button(text="Cancel")
        save = Button(text="Save task")
        actions.add_widget(cancel)
        actions.add_widget(save)
        shell.add_widget(actions)
        popup = Popup(
            title="Edit task" if template is not None else "Add task",
            content=shell,
            size_hint=(0.88, 0.92),
            auto_dismiss=False,
        )
        cancel.bind(on_release=popup.dismiss)
        save.bind(on_release=lambda _button: self._save_form(form, template, popup))
        self._form_popup = popup
        popup.open()
        return popup

    def _save_form(self, form: TaskForm, existing: object | None, popup: Popup) -> None:
        if form.submitting:
            return
        form.submitting = True
        try:
            now = self.service("shift").now()
            if existing is None:
                template = form.make_template(now=now)
                self.service("tasks").add_task(template)
            else:
                changes = form.task_values(now=now, existing=existing)
                self.service("tasks").update_task(existing.id, **changes)
            popup.dismiss()
            self._form_popup = None
            self.refresh_all()
        except Exception as error:
            form.submitting = False
            self.show_message("Task was not saved", str(error))

    def toggle_enabled(self, task_id: str, enabled: bool, *_args: object) -> None:
        try:
            self.service("tasks").set_enabled(task_id, enabled)
            self.refresh_all()
        except Exception as error:
            self.show_message("Task could not be updated", str(error))

    def move_task(self, task_id: str, direction: int, *_args: object) -> None:
        try:
            templates = self.service("tasks").list_templates()
            identifiers = [template.id for template in templates]
            current_index = identifiers.index(task_id)
            target_index = current_index + direction
            if not 0 <= target_index < len(identifiers):
                return
            identifiers[current_index], identifiers[target_index] = (
                identifiers[target_index],
                identifiers[current_index],
            )
            self.service("tasks").reorder_tasks(identifiers)
            self.refresh_all()
        except Exception as error:
            self.show_message("Tasks could not be reordered", str(error))

    def confirm_delete(self, task_id: str, title: str, *_args: object) -> Popup:
        return self.show_confirmation(
            "Delete task template?",
            f'Delete "{title}"? Closed history snapshots will remain unchanged.',
            lambda: self._delete(task_id),
        )

    def _delete(self, task_id: str) -> None:
        try:
            self.service("tasks").delete_task(task_id, confirmed=True)
            self.refresh_all()
        except Exception as error:
            self.show_message("Task could not be deleted", str(error))

    def _template(self, task_id: str) -> object:
        try:
            return next(
                template
                for template in self.service("tasks").list_templates()
                if template.id == task_id
            )
        except StopIteration as error:
            raise ValueError("task template no longer exists") from error
