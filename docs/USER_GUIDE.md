# Shift Checklist user guide

## Installation

Extract the complete `ShiftChecklist` folder from the release ZIP, then run
`ShiftChecklist.exe`. Keep all files in the extracted folder together. The app
does not require Python, an account, or an internet connection.

Windows may show a reputation warning for an unsigned first release. Verify the
published SHA-256 checksum before opening it. Do not bypass a malware detection;
report it with the release file and checksum for investigation.

## First launch and shift dates

On first launch the app creates editable default tasks and opens the active
shift. A shift date is based on the configured reset time, not simply midnight.
With the default noon reset, work performed at 4:00 AM or 8:00 AM remains part
of the shift that started on the previous calendar day.

## Today

Today shows the live clock, active shift date, completed/total progress, upcoming
and overdue counts, next reminder, and ordered task cards.

- Select **Complete** to save a completion timestamp immediately.
- Select **Reopen** to clear the completion timestamp and return the task to
  pending.
- Select **Client Messages Checked** to save an immutable check event and an
  optional note. The next check time uses the interval in Settings.
- For Shopify work, select **Change status** to update the manual workflow.

The labels PENDING, UPCOMING, DUE NOW, OVERDUE, COMPLETED, and MISSED accompany
status colors so color is not the only indicator.

## Tasks and Shopify work

The Tasks screen lists every template, including disabled templates.

- Add a general daily or one-time task with an optional schedule and reminder.
- Use the up/down controls to retain a predictable manual order.
- Edit or enable/disable a template. Changes affect the open shift and future
  shifts, but never rewrite closed history.
- Delete only after confirmation. Completed historical snapshots are retained.

Use **+ Shopify work** only when a real request arrives. Supply the store/client,
description, requested time, priority, status, notes, and target shift date.
Shopify work is local and manual: the app never connects to Shopify.

## Reminders

Scheduled tasks can produce one pre-due reminder and one due reminder. Overdue
status remains visible without repeated desktop spam. Client-message reminders
run independently and reset after each recorded check.

Reminders work only while Shift Checklist is running. If Windows notifications
are disabled or unavailable, the app still shows an in-app banner. A missing or
unsupported sound file is logged and does not stop the reminder.

## History

History shows closed shifts newest first. Select a shift to review its immutable
task snapshots, scheduled and completion times, FastDTR entries, Shopify status,
and client-message checks. History is read-only in version 0.1.0.

## Settings

Settings controls desktop notifications, sound, sound-file path, default task
reminder lead, client-message interval, daily reset time, clock format, and task
categories. Changes save immediately.

Changing reset time may close the current shift. Read the warning carefully.
Deleting a category used by a task requires selecting a replacement. **Open data
folder** opens the exact local storage location.

## Data, backup, and recovery

Mutable data is stored below `%LOCALAPPDATA%\ShiftChecklist\data`, never in the
installed application folder. Each JSON save is atomic and retains a `.bak`
copy. If a primary file is malformed, the app preserves it with a `.corrupt-*`
suffix and restores the last valid backup when possible.

To back up:

1. Close the app.
2. Open Settings and note the displayed data directory.
3. Copy the entire directory to a dated folder on another drive.
4. Confirm several copied JSON files open successfully.

To restore, close the app, preserve the current directory under another name,
and replace it with one complete known-good backup. Do not combine JSON files
from different backup dates.

Logs are under `data\logs`. They contain technical lifecycle and failure details,
not deliberately recorded task or client-message notes.

## Privacy and limitations

Version 0.1.0 is local-only and supports one Windows user and one active shift.
It has no cloud sync, account, team dashboard, automatic FastDTR activity,
message reading, Shopify API integration, system tray, auto-start, or cloud
backup.
