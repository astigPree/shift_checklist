# Shift Checklist

Shift Checklist is a local Windows desktop application for managing recurring
night-shift responsibilities, time-sensitive FastDTR reminders, repeated client
message checks, and conditional Shopify work. It is planned in Python and Kivy
and stores its data locally without requiring an account or server.

## Project status

The product rules, versioned local storage, core services, reminder engine, and
four main application screens are implemented. The runnable Kivy app supports
the active checklist, task/Shopify management, client-message checks, history,
and immediately applied settings. The app also writes rotating local logs and
surfaces storage recovery actions. Packaging and full manual Windows acceptance
testing remain before the MVP release.

## Project documents

- [Project description](project/PROJECT%20DESCRIPTION.md)
- [Implementation task plan](project/PROJECT%20TASK.md)
- [Product rules and acceptance examples](docs/PRODUCT_RULES.md)
- [Windows acceptance checklist](docs/WINDOWS_ACCEPTANCE.md)

## Decision log

| Decision | Chosen behavior |
| --- | --- |
| Shift identity | Records use an active shift date, not the date currently shown by the Windows clock. |
| Shift boundary | A shift starts at the configured daily reset time. The initial default is 12:00 PM local time. |
| Overnight times | With a noon reset, 4:00 AM and 8:00 AM belong to the shift that started the previous calendar day. |
| Timestamp storage | Store timezone-aware ISO 8601 timestamps; local 12-hour display is the default. |
| Recurrence | MVP supports `daily` and `one_time`; a one-time task targets exactly one shift date. |
| Stored task states | Occurrences are `pending`, `completed`, or `missed`; upcoming, due, and overdue are calculated UI states. |
| Shift close | Every incomplete occurrence becomes `missed`, including untimed and one-time tasks. Tasks do not carry automatically. |
| Reopening | Reopening a completed task returns it to pending and clears `completed_at`. |
| History | Closed daily records are immutable snapshots and survive template edits or deletion. |
| Reminders | At most one pre-due and one due notification are sent per occurrence; late startup sends only one due/overdue notification. |
| Client checks | Each click creates an immutable event and sets the next reminder from the configured interval. The default interval is 30 minutes. |
| Shopify work | Shopify requests are manually created one-time tasks; the app performs no Shopify API actions. |
| Data | Mutable files live under the current Windows user's local app-data directory and are saved atomically with backup recovery. |
| Deferred settings | System tray, Windows auto-start, arbitrary data relocation, cloud sync, and integrations are post-MVP. |

These decisions are specified precisely in
[docs/PRODUCT_RULES.md](docs/PRODUCT_RULES.md). If a decision changes, update
that document and its acceptance examples before changing implementation.

## Planned technology

- Python 3.11 (unless a newer interpreter is validated with the pinned Kivy version)
- Kivy and Kivy Language
- JSON storage for MVP
- Kivy Clock for scheduling
- Plyer for Windows desktop notifications
- PyInstaller for Windows packaging

## Development setup

Python 3.11 is the supported development interpreter. From PowerShell in the
project directory:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools
python -m pip install -r requirements-dev.txt
```

Kivy 2.3.1 provides a precompiled 64-bit Windows wheel for Python 3.11. Runtime
and development dependency versions are pinned for reproducible setup.

## Run

```powershell
.\.venv\Scripts\python.exe main.py
```

The app opens the active shift on Today. Use the bottom navigation to manage
task templates, review closed-shift history, or change settings. All user
mutations are saved immediately to the local JSON documents.

## Quality checks

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
powershell -ExecutionPolicy Bypass -File scripts\smoke_test.ps1
```

The smoke-test script opens the real Kivy window, cycles through all four
screens using empty, typical, and large datasets, then closes it automatically.
It is useful after UI, dependency, or packaging changes.

To run lint, tests, coverage, and all smoke datasets as one Windows preflight:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify_source.ps1
```

The hands-on release scenarios are in
[the Windows acceptance checklist](docs/WINDOWS_ACCEPTANCE.md).

## Development build

The reproducible release specification is created during the packaging
milestone. Until then, a disposable bootstrap build can be produced with:

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm --windowed `
  --onedir --name ShiftChecklist --add-data "shift_checklist.kv;." main.py
```

The output is written to `dist\ShiftChecklist`. This interim command is for
developer smoke testing, not release distribution.

## Data and backups

The application stores versioned JSON below the current user's
`%LOCALAPPDATA%\ShiftChecklist\data` directory. On a true first launch it creates
the task, history, message-check, and settings documents, seeds the editable
default checklist, and opens the current shift. Runtime data is never placed in
the repository or beside the packaged executable.

Each save uses an atomic replacement and keeps the previous valid primary as a
`.bak` file. Malformed data is preserved with a `.corrupt-<id>` suffix before a
valid backup is restored.

To make a manual backup:

1. Close Shift Checklist so no save is in progress.
2. Open Settings and note the exact data-directory path.
3. Copy the entire `data` directory—including JSON, `.bak`, and `logs`—to a
   dated folder on another local drive.
4. Open several copied JSON files and confirm they are readable before relying
   on the backup.

To restore, close the app, preserve the current data directory under a different
name, and copy the complete known-good directory back into the displayed
location. Do not merge individual JSON files from different backup dates. See
[the version 1 data schema](docs/DATA_SCHEMA.md) for the exact contracts and
recovery behavior.

Application logs rotate at approximately 1 MB and are stored under
`%LOCALAPPDATA%\ShiftChecklist\data\logs\shift-checklist.log`, with up to three
older log files retained. Logs contain lifecycle, severity, failure, and recovery
information; task notes and client-message notes are not deliberately logged.

For isolated development data:

```powershell
.\.venv\Scripts\python.exe main.py --data-dir .\dev-data
```

## Troubleshooting

- Confirm `.\.venv\Scripts\python.exe --version` reports Python 3.11.
- Reinstall pinned packages with
  `.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt`.
- Run `scripts\smoke_test.ps1` to distinguish startup/provider failures from
  later application logic failures.
- Kivy diagnostic logs are written below `%USERPROFILE%\.kivy\logs` during
  development.
- If Windows notifications are unavailable, reminders still appear in the
  in-app banner. Check the Kivy log for the platform-provider error.

## Project structure

```text
main.py                  Application entry point
shift_checklist.kv       Kivy layout and styling
constants.py             Stable application values and enums
models/                  Domain data models
screens/                 Today, Tasks, History, and Settings screens
widgets/                 Reusable Kivy widgets
services/                Storage and business behavior
assets/                  Icons and reminder sounds
tests/                   Automated tests
scripts/                 Developer helper scripts
packaging/               PyInstaller configuration and release assets
docs/                    Product decisions and technical documentation
project/                 Original description and implementation checklist
```

## Initial limitations

Reminders work only while the application is running. The MVP does not read
messages, operate FastDTR, modify Shopify, synchronize devices, or support
multiple users.
"# shift_checklist" 
