# Development guide

## Environment

Use 64-bit Python 3.11 on Windows:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Run the app with `main.py`. Use `--data-dir` only for isolated development and
testing. Production data resolves through `platformdirs`.

## Architecture

- `models/` owns validation and versioned serialization boundaries.
- `services/` owns storage, shift, task, history, settings, message-check,
  reminder, and logging behavior.
- `screens/` owns Kivy event handlers and delegates business mutations to
  services.
- `widgets/` contains reusable task/form/progress controls.
- `shift_checklist.kv` owns layout and shared presentation styles.
- `main.py` creates the service container, schedules rollover/reminders, and
  installs the application exception boundary.

Mutable documents use atomic replacement and backup recovery. Closed shift
records are snapshots and must never be rewritten by template changes.

## Quality and smoke checks

Run the complete source gate:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify_source.ps1
```

Tests must use temporary data directories and controllable clocks. Normal
workflow tests must not access the user's real app data or network.

## Schema migrations

Every root JSON document has `schema_version`. To add a schema version:

1. Update `SCHEMA_VERSION` and the affected model parser/serializer.
2. Register a sequential migration with `StorageService.register_migration`.
3. Preserve unknown fields or explicitly document why they are removed.
4. Add tests for old input, migrated output, backups, unsupported future versions,
   and failure recovery.
5. Update `docs/DATA_SCHEMA.md`, `CHANGELOG.md`, and upgrade acceptance tests.

Never edit a user's file in place without atomic write and backup behavior.

## Packaging

Build and validate a console diagnostic package first:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build.ps1 -Diagnostic
```

Build the windowed release, run packaged smoke/data-location checks, scan with
Windows Security, create a ZIP, and write its SHA-256 file:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\package_release.ps1
```

PyInstaller uses `packaging\shift_checklist.spec`. It includes the KV file,
icons, sounds, end-user documents, Plyer Windows providers, DPI manifest, and
version resource. Release output is `onedir` for transparent troubleshooting.
Every build audits missing imports against the reviewed list in
`packaging\KNOWN_WARNINGS.md`; a new missing-module name fails packaging until
it is investigated.

The clean-profile and full manual scenarios in `docs/WINDOWS_ACCEPTANCE.md`
remain required release gates.
