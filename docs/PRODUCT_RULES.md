# Product Rules and Acceptance Examples

Status: accepted for MVP implementation

This document removes ambiguity from the project description. These rules are
the contract for services, UI behavior, tests, and historical data.

## 1. Time and active shift

1. All calculations use the computer's local timezone.
2. Persisted timestamps are timezone-aware ISO 8601 strings including an offset.
3. The UI displays local time according to the time-display setting, which
   defaults to 12-hour format with AM/PM.
4. `reset_time` is the boundary between shifts and defaults to `12:00 PM`.
5. The `shift_date` is the local calendar date on which that shift began.
6. The interval for a shift is start-inclusive and end-exclusive. With the
   default setting, shift `2026-08-01` runs from August 1 at 12:00 PM through,
   but not including, August 2 at 12:00 PM.
7. A scheduled clock time on or after the reset time occurs on `shift_date`.
   A scheduled clock time before the reset time occurs on the following calendar
   date. This mapping must work for any configured reset time.
8. If Windows timezone or clock settings change, new calculations use the new
   local setting; already stored timestamps retain their original offset.

### Acceptance examples

| Current local time | Reset time | Expected active `shift_date` |
| --- | --- | --- |
| Aug 1, 11:59 AM | 12:00 PM | `2026-07-31` |
| Aug 1, 12:00 PM | 12:00 PM | `2026-08-01` |
| Aug 1, 11:59 PM | 12:00 PM | `2026-08-01` |
| Aug 2, 4:00 AM | 12:00 PM | `2026-08-01` |
| Aug 2, 8:00 AM | 12:00 PM | `2026-08-01` |
| Aug 2, 12:00 PM | 12:00 PM | `2026-08-02` |

For shift `2026-08-01`, a task scheduled for 8:00 PM is due on August 1;
tasks scheduled for 4:00 AM and 8:00 AM are due on August 2.

## 2. Templates and occurrences

1. A task template defines reusable behavior. A task occurrence is the snapshot
   placed into a daily record for one shift.
2. A `daily` template creates one occurrence at the start of every shift while
   the template is enabled.
3. A `one_time` template creates one occurrence only for its `target_shift_date`.
4. Opening the same shift repeatedly must never create duplicate occurrences.
5. New templates added during an open shift appear in that shift when they are
   daily or target that shift.
6. Editing a template updates its pending occurrence in the open shift and all
   future occurrences. A completed occurrence keeps its completion timestamp,
   but its visible snapshot fields may be updated until the shift closes.
7. Deleting a template requires confirmation. It removes its pending occurrence
   from the open shift and prevents future occurrences. A completed occurrence
   and every closed historical occurrence remain intact.
8. Disabling a template has the same current/future scheduling effect as deletion
   but retains the template so it can be enabled later.
9. Manual ordering is stored on templates and copied to occurrences.

### Acceptance examples

- A daily FastDTR task exists once on every shift until disabled or deleted.
- A Shopify request targeted to shift `2026-08-01` does not appear on shift
  `2026-08-02`.
- Restarting the app five times during one shift still produces one occurrence
  per applicable template.
- Deleting a task on August 3 does not remove its August 1 completion from History.

## 3. Task status and progress

1. Persisted occurrence states are `pending`, `completed`, and `missed`.
2. `upcoming`, `due`, and `overdue` are derived display/reminder states for a
   pending scheduled occurrence; they are not saved as the canonical status.
3. A scheduled pending task is upcoming before its due time, due during the
   scheduler tick that reaches its due time, and overdue afterward.
4. An untimed task stays pending and never becomes overdue during an open shift.
5. Completing an occurrence changes its state to `completed` and records one
   `completed_at` timestamp.
6. Reopening it changes the state to `pending` and clears `completed_at`.
7. When a shift closes, every incomplete occurrence becomes `missed`, whether
   scheduled, unscheduled, daily, or one-time. Nothing carries automatically.
8. A user who wants unfinished work on the next shift creates/reschedules a new
   one-time task before closure or creates a new task on the next shift.
9. Daily progress is `completed active occurrences / total active occurrences`.
   Removed pending occurrences are not in the denominator. Completed occurrences
   retained after template deletion remain in it.

### Acceptance examples

- Completing 6 of 8 active occurrences displays `6 of 8 tasks completed`.
- Reopening one of those tasks changes the display to `5 of 8` and removes the
  old completion time.
- At rollover, the three remaining pending tasks are stored as missed in the
  closed record; new daily occurrences begin pending in the new record.

## 4. Reminder rules

1. A task can enable or disable reminders and can define non-negative
   `reminder_lead_minutes`.
2. An enabled timed occurrence may produce one pre-due notification and one due
   notification. Fired flags are persisted on the occurrence.
3. The pre-due window begins at `due_at - reminder_lead_minutes` and ends before
   `due_at`. The due window begins at `due_at`.
4. If the app first evaluates a pending task after its due time, it sends one
   due/overdue notification, marks both reminder opportunities handled, and does
   not send a stale pre-due notification.
5. Completing, deleting, or disabling the relevant pending occurrence suppresses
   future notification for it.
6. Reopening a task does not replay a notification whose fired flag was already
   persisted.
7. Editing a pending occurrence recalculates its due time. Fired flags reset only
   for reminder times that move into the future; this must not create immediate
   duplicates.
8. Polling, wake-from-sleep, restart, and shift rollover must not cause duplicate
   notifications.
9. When Windows notification delivery fails or is disabled, an in-app banner is
   the fallback. Sound failure is non-fatal.
10. Reminders are available only while the application is running.

### Acceptance examples

- A 4:00 AM task with a five-minute lead sends at most one notification at/after
  3:55 AM and at most one at/after 4:00 AM.
- If the app opens at 4:10 AM, it sends one overdue notification, not both a
  3:55 AM and a 4:00 AM notification.
- Completing the task at 3:58 AM prevents its 4:00 AM notification.
- Restarting at 4:01 AM after the due notification fired does not fire it again.

## 5. Client-message checks

1. The default interval is 30 minutes and can be configured to a positive whole
   number of minutes.
2. Clicking **Client Messages Checked** creates an immutable event containing its
   shift date, timestamp, optional note, and calculated next-check timestamp.
3. `next_check_at` equals `checked_at + configured interval`.
4. A new check replaces the active next reminder but does not modify older events.
5. If no check exists in the active shift, the first reminder is scheduled for
   one configured interval after the later of shift start or application start.
6. The Today screen shows `Not checked this shift` until the first active-shift
   event, while History still shows earlier events.
7. At shift rollover, the active-shift display and initial reminder reset; prior
   events remain in History.

### Acceptance examples

- With a 30-minute interval, a check at 3:30 AM displays 4:00 AM as next reminder.
- Checks at 3:30 AM and 3:45 AM remain as two events; the active reminder moves
  from 4:00 AM to 4:15 AM.

## 6. Shopify tasks

1. Shopify work is manually entered and uses `one_time` recurrence.
2. Required fields are store/client, description, requested timestamp, priority,
   target shift date, and status. Notes are optional.
3. Priorities are `Low`, `Normal`, `High`, and `Urgent`; default is `Normal`.
4. Statuses are `Pending`, `In Progress`, `Waiting for Clarification`, `Ready for
   Review`, and `Completed`.
5. Any non-completed status can move to another status. Moving to `Completed`
   completes the task occurrence and records `completed_at`.
6. Moving a completed Shopify item back to another status reopens its occurrence
   and clears `completed_at`.
7. Priority affects grouping within Shopify work; stable manual order breaks ties.
8. The app does not contact Shopify or store Shopify credentials.

## 7. History and immutability

1. Rollover closes the previous daily record before opening the next one.
2. A closed record stores task snapshots, completion/missed states, completion
   times, message checks, and Shopify details.
3. Closed records are read-only in MVP.
4. Template changes, category changes, and deletions never rewrite closed records.
5. If the app was not opened for several shifts, it closes the last known open
   shift and opens only the current shift. It does not invent empty records for
   days on which the app was never used.

## 8. Settings and category rules

1. MVP settings are notification enabled, sound enabled/path, default reminder
   lead, client-check interval, reset time, categories, and time display.
2. Settings save immediately after validation and reschedule affected reminders.
3. Changing reset time requires confirmation if it changes the active shift date.
   After confirmation, the app closes the old record and opens the newly resolved
   shift exactly once.
4. A category in use cannot be deleted until the user selects a replacement for
   all templates using it.
5. The data directory can be displayed and opened but not relocated in MVP.
6. Auto-start and system-tray controls are not shown until implemented.

## 9. Local storage and recovery

1. Mutable JSON, backups, and logs are stored below the per-user Windows local
   app-data directory, not the source or packaged executable directory.
2. First launch creates missing directories and versioned JSON roots.
3. Saves use a temporary file and atomic replacement while retaining a
   last-known-good backup.
4. A malformed primary file is preserved for diagnosis and recovered from backup
   when possible. The user receives a visible error/recovery message.
5. Defaults seed only when task storage has never existed. An intentionally empty
   task list remains empty after restart.
6. The application performs no network requests during normal MVP operation.

## 10. MVP scope boundary

The MVP does not implement system-tray operation, Windows auto-start, arbitrary
data relocation, SQLite, export, cloud sync, online accounts, team support,
FastDTR integration, client-message integration, Shopify integration, or a mobile
application. These items require a later scoped release.

## 11. End-to-end acceptance scenario

Given reset time 12:00 PM and active shift `2026-08-01`:

1. The app opens during the evening of August 1 and creates the shift once.
2. Daily tasks appear pending; a conditional Shopify task can be added manually.
3. Client checks append timestamped events and move the next reminder.
4. The 3:55 AM pre-reminder and 4:00 AM due reminder map to August 2 while still
   belonging to shift `2026-08-01`.
5. JDK checkout and Happy BUM check-in can be completed independently with their
   own timestamps.
6. A Shopify status of Completed records its completion time.
7. The 8:00 AM Happy BUM checkout still belongs to shift `2026-08-01`.
8. At August 2, 12:00 PM, incomplete occurrences become missed and the record is
   closed. Shift `2026-08-02` is opened with fresh daily occurrences.
9. History shows the closed shift exactly as completed, even after a related task
   template is edited or deleted.
10. Closing and reopening the app never duplicates tasks, events, or notifications.
