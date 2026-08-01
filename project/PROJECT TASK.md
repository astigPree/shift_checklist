# Shift Checklist — Implementation Task Plan

This file converts `PROJECT DESCRIPTION.md` into an ordered plan for building,
testing, packaging, and releasing a runnable Windows desktop application.

## 1. Delivery target and scope

### 1.1 MVP release goal

Deliver a single-user Windows desktop application built with Python and Kivy
that runs without an account or server and can:

- [ ] Display the checklist for the active work shift.
- [ ] Add, edit, delete, enable/disable, and reorder task templates.
- [ ] Create daily and one-time tasks with optional scheduled times and notes.
- [ ] Mark tasks complete and preserve the completion timestamp.
- [ ] Show upcoming/due/overdue reminders while the app is running.
- [ ] Record repeated client-message checks and calculate the next check time.
- [ ] Create and track conditional Shopify work.
- [ ] Reset recurring tasks for each new shift without changing prior history.
- [ ] Display daily progress and historical records.
- [ ] Save all data locally and recover safely from missing/corrupt files.
- [ ] Be packaged as a Windows executable that can be launched by a non-developer.

### 1.2 Explicit non-goals for the first release

- [x] Do not implement cloud sync, accounts, teams, or a web dashboard.
- [x] Do not read client messages automatically.
- [x] Do not log into or perform actions in FastDTR.
- [x] Do not connect to Shopify Admin APIs or modify Shopify automatically.
- [x] Do not require an internet connection.
- [x] Defer system-tray mode, Windows auto-start, multi-schedule support, exports,
      SQLite, and mobile apps until after the MVP.

## 2. Resolve product rules before implementation

Record the chosen values in a short decision log in `README.md` and encode them
as settings/defaults. The recommended choices below make the night shift work
correctly but must remain configurable where noted.

- [x] Define an **active shift date**, rather than relying on the calendar date.
      Recommended rule: the daily reset time is the start of a new shift; before
      that time, the active shift belongs to the previous calendar date.
- [x] Set the first-launch daily reset time. Recommended default: `12:00 PM`
      local time, so tasks completed at 4:00 AM and 8:00 AM remain in the same
      overnight shift. Make it configurable.
- [x] Store timestamps as timezone-aware ISO 8601 strings, display them in the
      computer's local timezone, and use 12-hour time in the UI.
- [x] Define recurrence for MVP as `daily` or `one_time`. A one-time task must
      have a target shift date and must not appear on later shifts.
- [x] Define task states as `pending`, `completed`, and `missed`. Treat an
      incomplete scheduled task as `overdue` in the live UI; finalize it as
      `missed` only when its shift closes.
- [x] Decide completion behavior: completing a task stores `completed_at`;
      reopening it clears the timestamp and returns it to `pending`.
- [x] Decide edit behavior: template edits affect the current open shift and
      future shifts, but never rewrite closed history. History keeps snapshots.
- [x] Decide delete behavior: deleting a template requires confirmation and
      does not delete historical snapshots.
- [x] Define reminder behavior: one optional pre-due reminder plus a due
      notification; each reminder fires at most once per task occurrence.
- [x] Define untimed task behavior: it can be completed but never becomes
      overdue and produces no scheduled notification.
- [x] Define client-check behavior: each click creates an immutable event;
      `next_check_at = checked_at + configured_interval`.
- [x] Define Shopify fields and statuses: store/client, description, requested
      time, priority, notes, and `Pending`, `In Progress`, `Waiting for
      Clarification`, `Ready for Review`, or `Completed`.
- [x] Confirm that the initial release supports one local Windows user and one
      active shift at a time.

## 3. Bootstrap the project

- [x] Install a supported 64-bit Python version (use Python 3.11 unless the
      selected Kivy version has been verified with a newer interpreter).
- [x] Create and activate a virtual environment:

  ```powershell
  py -3.11 -m venv .venv
  .\.venv\Scripts\Activate.ps1
  python -m pip install --upgrade pip
  ```

- [x] Create `requirements.txt` with pinned compatible versions of Kivy, Plyer,
      platformdirs, and any sound/Windows notification dependencies.
- [x] Create `requirements-dev.txt` with pytest, coverage, Ruff, and PyInstaller.
- [x] Install dependencies and verify Kivy can open a minimal window:

  ```powershell
  python -m pip install -r requirements.txt
  python -m pip install -r requirements-dev.txt
  ```

- [x] Add `.gitignore` entries for `.venv/`, `__pycache__/`, `.pytest_cache/`,
      coverage output, `build/`, `dist/`, runtime data, and logs.
- [x] Add a basic `README.md` with prerequisites, setup, run, test, build, data
      location, backup, and troubleshooting instructions.

## 4. Create the application structure

- [x] Create this package layout (add `__init__.py` files where applicable):

  ```text
  shift_checklist/
  |-- main.py
  |-- shift_checklist.kv
  |-- requirements.txt
  |-- requirements-dev.txt
  |-- models/
  |   |-- task.py
  |   |-- daily_record.py
  |   |-- message_check.py
  |   `-- settings.py
  |-- screens/
  |   |-- today_screen.py
  |   |-- task_management_screen.py
  |   |-- history_screen.py
  |   `-- settings_screen.py
  |-- widgets/
  |   |-- task_item.py
  |   |-- task_form.py
  |   `-- progress_card.py
  |-- services/
  |   |-- storage_service.py
  |   |-- task_service.py
  |   |-- shift_service.py
  |   |-- reminder_service.py
  |   |-- history_service.py
  |   `-- message_check_service.py
  |-- assets/
  |   |-- icons/
  |   `-- sounds/
  |-- tests/
  |-- scripts/
  `-- packaging/
  ```

- [x] Keep Python responsible for application state and behavior; use the KV
      file for layout/style and small UI bindings only.
- [x] Add a central `AppState` or service container so screens share the same
      task, shift, reminder, history, and settings services.
- [x] Add constants/enums for recurrence, task status, Shopify status, priority,
      and default categories; do not scatter display strings through the code.

## 5. Define and version the local data contracts

Use stable UUID strings for identifiers and add `schema_version` to every root
JSON document. Keep task definitions separate from per-shift task occurrences.

### 5.1 `tasks.json`

- [x] Define a task-template schema containing:
      `id`, `title`, `category`, `notes`, `scheduled_time`, `reminder_enabled`,
      `reminder_lead_minutes`, `recurrence`, `target_shift_date`, `enabled`,
      `sort_order`, `task_type`, `shopify_details`, `created_at`, and `updated_at`.
- [x] Validate required fields, time formats, enum values, and non-negative
      reminder intervals when loading and saving.
- [x] Preserve unknown future fields where practical or migrate them explicitly.

### 5.2 `daily_records.json`

- [x] Store one record per active shift date with `opened_at`, `closed_at`, and
      task occurrence snapshots.
- [x] Give each occurrence its own ID plus `template_id`, copied title/category/
      schedule/notes, `status`, `completed_at`, and reminder-fired flags.
- [x] Store enough snapshot data that later template edits/deletes cannot change
      old history.

### 5.3 `message_checks.json`

- [x] Store append-only events containing `id`, `shift_date`, `checked_at`,
      optional `note`, and the calculated `next_check_at`.

### 5.4 `settings.json`

- [x] Store notifications enabled, sound enabled/path, client-check interval,
      reminder lead time, reset time, categories, time display preference, and
      the last successfully opened app version.
- [x] Supply safe defaults when a setting is absent.

### 5.5 Storage location and safety

- [x] Use `platformdirs` and store mutable data under the user's local app-data
      directory (for example `%LOCALAPPDATA%\ShiftChecklist\data`), not beside
      a packaged executable.
- [x] Allow a development-only data-directory override through a dedicated
      environment variable or command-line option for tests.
- [x] Create missing directories/files on first launch.
- [x] Write JSON atomically: serialize to a temporary file, flush it, replace the
      target, and retain a last-known-good `.bak` copy.
- [x] Protect in-process reads/writes with a lock so Kivy callbacks cannot overlap.
- [x] On malformed JSON, preserve the corrupt file, attempt backup recovery, and
      show a clear error instead of silently deleting user data.
- [x] Add schema-migration hooks even if version 1 needs no migration yet.

## 6. Implement models and core services

### 6.1 Models

- [x] Implement typed model classes/dataclasses for task templates, occurrences,
      daily records, message checks, app settings, and Shopify metadata.
- [x] Implement `to_dict`/`from_dict` conversion at one boundary.
- [x] Normalize and validate user input in the models or a dedicated validator.

### 6.2 Storage service

- [x] Implement load/save/backup/recovery for every JSON document.
- [x] Seed defaults only when no task file has ever existed; never re-add defaults
      merely because the user deleted every task.
- [x] Add a storage health check and useful, non-sensitive log messages.

### 6.3 Shift service

- [x] Calculate the active shift date from local time and configured reset time.
- [x] On startup, finalize any previously open shift before creating/loading the
      current one.
- [x] Materialize enabled daily templates and matching one-time tasks into a new
      daily record exactly once.
- [x] Mark remaining scheduled occurrences from the closed shift as `missed`.
- [x] Keep unscheduled incomplete occurrences as pending in history or missed,
      according to the product decision in section 2, and test that rule.
- [x] Reschedule the next boundary whenever the reset-time setting changes.
- [x] Handle the app being left open across the reset boundary without requiring
      a restart.

### 6.4 Task service

- [x] Implement create, update, soft-enable/disable, confirmed delete, and reorder.
- [x] Reject blank titles and invalid dates/times with user-friendly messages.
- [x] Implement complete/reopen operations and save immediately after each action.
- [x] Implement live derived states: pending, upcoming, due, overdue, completed.
- [x] Expose filtered/sorted collections to the UI without duplicating business
      logic in screen classes.

### 6.5 History service

- [x] Return daily summaries and detailed task/message/Shopify records by shift.
- [x] Calculate completed, pending/missed, attendance, and message-check counts.
- [x] Keep history read-only from the initial UI.

### 6.6 Client-message check service

- [x] Record a check event with an optional note.
- [x] Return the most recent check for the active shift and globally.
- [x] Calculate the next reminder and reset/reschedule it after every check.

## 7. Seed first-launch defaults

- [x] Create editable default categories: Client Monitoring, FastDTR, Shopify,
      End of Shift, and General.
- [x] Seed the default recurring tasks described in the project description.
- [x] Assign practical times to the FastDTR tasks and keep preparatory reminders
      separate from the actual completion actions.
- [x] Avoid seeding “complete assigned Shopify update” as a mandatory daily task;
      Shopify work should be created as a one-time conditional task when requested.
- [x] Store seed data in code or a versioned asset, then load it only on true first
      launch.
- [x] Verify every seeded task can be edited, disabled, reordered, or deleted.

## 8. Build the Kivy application shell

- [x] Create the Kivy `App`, load the KV file explicitly, initialize services,
      open the active shift, and then display the first screen.
- [x] Use `ScreenManager` navigation for Today, Tasks, History, and Settings.
- [x] Add a consistent navigation bar, page title, and current date/time.
- [x] Establish reusable colors, spacing, typography, button, form, and status
      styles that remain legible at common Windows scaling levels.
- [x] Make long task lists scrollable and support keyboard/mouse interaction.
- [x] Display a recoverable error dialog for load/save/notification failures.
- [x] Save pending changes and stop scheduled callbacks cleanly on app exit.

## 9. Implement the Today screen

- [x] Display the active shift date and a clock that updates without blocking UI.
- [x] Display progress as `completed / total` plus counts for overdue and upcoming.
- [x] Render ordered task cards with title, category, scheduled time, state,
      reminder indicator, notes preview, and complete/reopen action.
- [x] Visually distinguish completed, upcoming, due, and overdue tasks without
      relying on color alone.
- [x] Add the **Client Messages Checked** action with optional-note dialog.
- [x] Display last checked and next reminder times.
- [x] Display the next scheduled reminder and the most urgent overdue task.
- [x] Add a shortcut to the add-task form.
- [x] Refresh immediately after task changes, completion, message checks, setting
      changes, and shift rollover.
- [x] Provide clear empty states for no tasks and no message checks.

## 10. Implement task management

- [x] List all templates with enabled state, category, recurrence, schedule, and
      drag/move controls for ordering.
- [x] Build a reusable add/edit form for title, category, schedule, reminder,
      reminder lead, recurrence, one-time shift date, notes, and enabled state.
- [x] Show Shopify-specific fields only when the Shopify task type/category is
      selected.
- [x] Validate in the form and again in the service before saving.
- [x] Add edit, enable/disable, and delete-confirmation actions.
- [x] Apply create/edit/delete/reorder changes to the Today screen consistently
      with the product rules in section 2.
- [x] Prevent duplicate submissions from repeated clicks.
- [x] Preserve form input if validation fails and focus the invalid field.

## 11. Implement Shopify task workflow

- [x] Create Shopify work as a one-time task for the active or selected shift.
- [x] Capture store/client name, task description, request timestamp, priority,
      status, notes, and completion timestamp.
- [x] Permit valid status transitions and show the status on Today and History.
- [x] When status becomes `Completed`, complete its task occurrence and timestamp
      it; define and test behavior when moved out of `Completed`.
- [x] Sort urgent/high-priority open work predictably without losing manual order.
- [x] Confirm that no Shopify or network API calls occur.

## 12. Implement reminders and notifications

- [x] Use one Kivy `Clock` polling callback (for example every 15–30 seconds) so
      all reminder logic runs on the application event loop.
- [x] Calculate exact due datetimes using active shift semantics, including times
      after midnight.
- [x] Fire the configured pre-due and due notification once per occurrence.
- [x] Continue showing overdue status in-app without repeatedly spamming desktop
      notifications.
- [x] Cancel/suppress future notifications for completed, deleted, or disabled
      occurrences.
- [x] Schedule repeated client-message reminders independently of task reminders.
- [x] Use Plyer for desktop notifications and provide an in-app banner fallback
      when Windows notifications are unavailable or disabled.
- [x] Play the selected sound only if enabled; missing sound assets must not crash.
- [x] Persist reminder-fired flags so restarting near a due time does not duplicate
      notifications.
- [x] Recalculate reminders after edits, completion/reopen, settings changes,
      message checks, wake-from-sleep, and shift rollover.
- [x] Document clearly that reminders run only while the app is running.

## 13. Implement History

- [x] List past shifts newest first with date and completion summary.
- [x] Open a shift detail view containing completed, missed/pending, FastDTR,
      Shopify, and client-message-check records.
- [x] Show task scheduled time and actual completion time.
- [x] Distinguish a task occurrence snapshot from the current template.
- [ ] Add simple date navigation/filtering if the history list becomes long.
- [x] Show clear empty and unavailable/corrupt-data states.

## 14. Implement Settings

- [x] Add controls for notifications, sound, default reminder lead, client-message
      interval, daily reset time, and category management.
- [x] Validate intervals and time values before saving.
- [x] Apply changes immediately and persist them atomically.
- [x] Warn before changing reset time if it would change the current active shift.
- [x] Prevent deleting a category that is in use, or require choosing a replacement.
- [x] Show the resolved local data directory and provide an “Open data folder”
      action; keep arbitrary storage relocation out of MVP.
- [x] Do not expose nonfunctional auto-start or system-tray settings in MVP.
- [x] Add an About section with app version and the local-only/privacy statement.

## 15. Logging, resilience, and privacy

- [x] Add rotating local logs under the app-data directory with timestamps and
      severity, excluding task notes or other unnecessary user content.
- [x] Add a top-level exception handler that logs the error and shows a readable
      message where safe.
- [x] Ensure every user mutation is saved immediately or clearly marked unsaved.
- [x] Test abrupt close/restart and confirm valid files can still load.
- [x] Verify the app makes no network request during normal operation.
- [x] Add a manual backup procedure to the README.

## 16. Automated tests

Use temporary directories and a controllable/fake clock; tests must never read or
write the user's real app-data directory.

### 16.1 Model and validation tests

- [x] Test serialization round trips and default values.
- [x] Test blank/invalid titles, times, dates, intervals, enums, and Shopify fields.
- [x] Test legacy/missing/unknown JSON fields and schema-version rejection.

### 16.2 Storage tests

- [x] Test first-launch creation and seed-once behavior.
- [x] Test atomic save, backup creation, backup recovery, and corrupt-file handling.
- [x] Test simulated write failures without losing the previous valid data.
- [x] Test concurrent callback access to the storage service.

### 16.3 Shift/task tests

- [x] Test active shift calculation before, at, and after reset time.
- [x] Test an overnight shift containing 4:00 AM and 8:00 AM tasks.
- [x] Test startup with no prior record, same open shift, and multiple missed shifts.
- [x] Test daily recurrence, one-time target dates, disabled tasks, edits, deletion,
      reorder, completion, reopening, and history snapshot immutability.
- [x] Test rollover while the app remains open.

### 16.4 Reminder/message tests

- [x] Test pre-due, due, and overdue boundaries.
- [x] Test notification deduplication across multiple polling ticks and restarts.
- [x] Test completed/deleted/edited task suppression and rescheduling.
- [x] Test client-check interval calculation and repeated reminder reset.
- [x] Test notification and sound failure fallbacks.

### 16.5 UI smoke tests

- [x] Test app startup, screen navigation, add/edit/delete, complete/reopen, client
      check, Shopify status change, history view, settings save, and clean exit.
- [x] Run smoke tests with empty, typical, and large data sets.

- [x] Make these local quality commands pass:

  ```powershell
  python -m ruff check .
  python -m pytest
  python -m coverage run -m pytest
  python -m coverage report --fail-under=80
  ```

## 17. Manual Windows acceptance testing

- [ ] Launch from source on the supported Windows version and scaling settings.
- [ ] Verify a first launch creates defaults in the correct app-data directory.
- [ ] Complete the full sample overnight workflow across the configured reset:
      client check, JDK checkout, Happy BUM check-in, Shopify task, final client
      check, and Happy BUM checkout.
- [ ] Temporarily create reminders a few minutes ahead and verify pre-due, due,
      in-app fallback, sound, completion suppression, and no duplicates.
- [ ] Leave the app running through a reset boundary and verify history/rollover.
- [ ] Close and reopen at each critical state and verify all data persists.
- [ ] Edit/delete templates and verify closed historical records do not change.
- [ ] Test notification permission denied, missing sound, corrupt primary JSON,
      recovered backup, and an unwritable data directory.
- [ ] Verify all dialogs fit onscreen and keyboard focus/navigation is usable.
- [x] Confirm no terminal window is required for the packaged GUI build.

## 18. Package the Windows application

- [x] Add application name, semantic version, icon, and version metadata.
- [x] Create a reproducible PyInstaller `.spec` file that includes the KV file,
      icons, sounds, and required Kivy/Plyer hidden imports/providers.
- [x] First build a console-enabled diagnostic version and resolve all missing
      dependency or asset warnings.
- [x] Build the release version (prefer `onedir` initially for easier debugging;
      move to `onefile` only after it is proven reliable):

  ```powershell
  python -m PyInstaller packaging\shift_checklist.spec --clean --noconfirm
  ```

- [ ] Test the output on a clean Windows user profile without Python installed.
- [x] Verify packaged data is written to local app data, not the installation
      directory, and survives app upgrades.
- [x] Scan the release output with Windows Security and investigate warnings.
- [x] Zip the tested `dist` folder with README/release notes and a checksum.
- [ ] Optionally add an installer only after the portable packaged build passes.

## 19. Documentation and release handoff

- [x] Document installation, first launch, navigation, task management, Shopify
      tasks, reminders, client checks, history, settings, and data backup.
- [x] Document limitations: app must remain running; no FastDTR, messaging, or
      Shopify automation; one device/user; no cloud backup.
- [x] Add developer instructions for environment setup, architecture, data schema,
      tests, building, and making schema migrations.
- [x] Add `CHANGELOG.md`, license/usage terms, and release notes.
- [ ] Tag the tested commit as the first release and archive the exact artifact.

## 20. MVP definition of done

The MVP is complete only when all of the following are true:

- [ ] Every item in sections 1–19 that is not explicitly deferred is complete.
- [x] All automated quality commands pass.
- [ ] All manual Windows acceptance scenarios pass in both source and packaged form.
- [ ] No known issue can cause silent data loss, repeated notification spam, or an
      incorrect FastDTR reminder time.
- [ ] The application can be installed/unzipped, launched, used through an entire
      overnight shift, closed, reopened, and upgraded without losing history.
- [ ] A non-developer can run the app and find backup/recovery instructions using
      only the delivered documentation.

## 21. Recommended implementation sequence

Follow this order so every milestone ends in a runnable or testable state:

1. [x] Product rules and acceptance examples (sections 1–2).
2. [x] Environment, skeleton, and minimal Kivy window (sections 3–4).
3. [x] Schemas, models, safe storage, and tests (sections 5–6.2, 16.1–16.2).
4. [x] Shift/task logic, seed data, and tests (sections 6.3–7, 16.3).
5. [x] App shell and Today screen with persistence (sections 8–9).
6. [x] Task management and Shopify workflow (sections 10–11).
7. [x] Reminder/client-check engine and tests (sections 6.6, 12, 16.4).
8. [x] History and settings (sections 13–14).
9. [ ] Resilience, UI smoke tests, and full manual QA (sections 15–17).
10. [ ] Packaging, clean-machine validation, documentation, and release
       (sections 18–20).

## 22. Post-MVP backlog

Do not start these until the MVP definition of done is satisfied and the local
JSON version has been used successfully through real shifts.

- [ ] System tray/background operation and Windows auto-start.
- [ ] SQLite migration with an automatic, backed-up JSON importer.
- [ ] Search, advanced filters, weekly reports, and missed-task analytics.
- [ ] CSV/PDF exports and optional encrypted backups.
- [ ] Notification action buttons and richer snooze rules.
- [ ] Multiple schedules, users, clients, and devices.
- [ ] Cloud sync and team/supervisor dashboards.
- [ ] Official FastDTR integration, only if a supported API and authorization exist.
- [ ] Shopify Admin API integration with least-privilege credentials and explicit
      user confirmation for every change.
- [ ] Mobile companion application.
