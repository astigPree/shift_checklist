# Windows acceptance checklist

Use this checklist before packaging and again against the packaged build. These
checks intentionally require a person to inspect notifications, focus behavior,
window layout, Windows permissions, and behavior over real elapsed time.

## Test record

- Tester:
- Date:
- Windows version:
- Display resolution and scaling:
- Build/source revision:
- Data-directory backup location:

## Automated preflight

From PowerShell in the project directory:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify_source.ps1
```

Record the result. The command verifies Python 3.11, lint, all automated tests,
at least 80% coverage, and real Kivy startup/navigation with empty, typical, and
large datasets.

## Source and first launch

- [ ] Start `main.py` at 100% Windows display scaling and confirm Today is fully
      visible at 1100×720 without clipped text or controls.
- [ ] Repeat at every supported scaling setting, including 125% and 150%.
- [ ] Confirm the first launch shows the editable default tasks once.
- [ ] In Settings, confirm the displayed data directory resolves below the
      current user's local app-data directory.
- [ ] Close and reopen the app; confirm defaults were not duplicated.

## Full overnight workflow

- [ ] Record a client-message check with a note and verify its next time.
- [ ] Complete JDK checkout and Happy BUM check-in tasks around 4:00 AM.
- [ ] Create a one-time Shopify request, move it through each status, and finish
      it as Completed.
- [ ] Record the final client-message check and complete Happy BUM checkout near
      8:00 AM.
- [ ] Reopen one completed task, confirm its completion time clears, and complete
      it again.
- [ ] Confirm every change survives an immediate close/reopen.

## Reminders and rollover

- [ ] Create a temporary task a few minutes ahead with a pre-due reminder.
- [ ] Confirm one pre-due notification, one due notification, an in-app banner,
      and the configured sound.
- [ ] Leave the task overdue across several polling intervals; confirm no repeated
      desktop notification spam.
- [ ] Complete a second task before its reminder; confirm its reminder is
      suppressed.
- [ ] Put Windows to sleep across a reminder boundary and confirm one appropriate
      reminder after wake.
- [ ] Set a temporary reset boundary a few minutes ahead, acknowledge the warning,
      and leave the app open across it. Confirm the old shift closes, pending work
      becomes missed, a new shift opens, and History shows the immutable snapshot.

## Failure and recovery behavior

Perform these checks only after making a manual backup. Use a disposable
development data directory when possible.

- [ ] Deny Windows notification permission; confirm the in-app banner still works.
- [ ] Configure a missing sound file; confirm the reminder appears and the app
      remains usable.
- [ ] Corrupt a primary JSON file that has a valid `.bak`; confirm the primary is
      preserved with a `.corrupt-*` suffix, the backup is restored, and the app
      displays a recovery notice.
- [ ] Test a disposable unwritable data directory; confirm the app reports the
      failure without silently replacing valid data.
- [ ] Review `logs\shift-checklist.log`; confirm timestamps/severity are present
      and task/message notes are not logged.

## Interaction and packaged-build checks

- [ ] Use mouse and keyboard to navigate every form and dialog; confirm focus is
      visible and no dialog extends beyond the display.
- [ ] Exercise empty, typical, and long task/history lists and their scrollbars.
- [ ] Edit and delete a template; confirm previously closed history is unchanged.
- [ ] Launch the packaged GUI build from Explorer and confirm no terminal window
      is required.
- [ ] Test the packaged build on a clean Windows user profile without Python.

Record failures with exact steps, expected behavior, actual behavior, screenshots,
and the relevant sanitized log excerpt. Do not mark the manual acceptance section
complete until every supported configuration passes.
