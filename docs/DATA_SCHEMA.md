# Local Data Schema (Version 1)

All files are UTF-8 JSON documents with `schema_version: 1`. Timestamps use
timezone-aware ISO 8601 strings, dates use `YYYY-MM-DD`, and local scheduled
times use 24-hour `HH:MM` strings. IDs are canonical UUID strings.

The model classes in `models/` are the executable source of truth. Unknown
fields are preserved during compatible load/save round trips, while invalid
known fields are rejected.

## Storage directory

Normal Windows runs use:

```text
%LOCALAPPDATA%\ShiftChecklist\data
```

Developers and tests can override it with the `--data-dir` option or the
`SHIFT_CHECKLIST_DATA_DIR` environment variable. Explicit command-line paths
take priority over the environment variable.

## `tasks.json`

```json
{
  "schema_version": 1,
  "tasks": []
}
```

Each task template contains:

| Field | Type | Rule |
| --- | --- | --- |
| `id` | UUID string | Unique within the document |
| `title` | string | Required and non-blank |
| `category` | string | Required and non-blank |
| `notes` | string | May be blank |
| `scheduled_time` | `HH:MM` or null | Local clock time |
| `reminder_enabled` | boolean | Requires a scheduled time when true |
| `reminder_lead_minutes` | integer | Zero or greater |
| `recurrence` | string | `daily` or `one_time` |
| `target_shift_date` | date or null | Required only for one-time tasks |
| `enabled` | boolean | Controls active/future materialization |
| `sort_order` | integer | Zero or greater |
| `task_type` | string | `general` or `shopify` |
| `shopify_details` | object or null | Required only for Shopify tasks |
| `created_at` | timestamp | Required and timezone-aware |
| `updated_at` | timestamp | Must not precede creation |

Shopify details contain `store_name`, `description`, `requested_at`, `priority`,
`status`, and optional `completed_at`. Shopify tasks must be one-time tasks. A
Completed status requires a completion timestamp; other statuses prohibit one.

## `daily_records.json`

```json
{
  "schema_version": 1,
  "records": []
}
```

Each record contains one unique `shift_date`, `opened_at`, optional `closed_at`,
and an `occurrences` array. At most one record can be open.

Each occurrence is an independent snapshot containing its own UUID,
`template_id`, `shift_date`, copied task fields, persisted `status`, optional
`completed_at`, pre-due/due reminder-fired flags, and `created_at`. Completed
occurrences require a completion timestamp; pending and missed occurrences must
not have one.

## `message_checks.json`

```json
{
  "schema_version": 1,
  "checks": []
}
```

Each event contains a unique `id`, `shift_date`, `checked_at`, `next_check_at`,
and optional-note string. The next-check timestamp must be later than the check.

## `settings.json`

```json
{
  "schema_version": 1,
  "settings": {
    "notifications_enabled": true,
    "sound_enabled": true,
    "reminder_sound_path": null,
    "client_check_interval_minutes": 30,
    "default_reminder_lead_minutes": 5,
    "reset_time": "12:00",
    "categories": [
      "Client Monitoring",
      "FastDTR",
      "Shopify",
      "End of Shift",
      "General"
    ],
    "time_format": "12h",
    "last_opened_app_version": "0.1.0-dev",
    "default_tasks_seeded": false
  }
}
```

Categories must be non-empty and case-insensitively unique. Client-check
interval must be positive; reminder lead may be zero. The seed marker prevents
defaults from being re-added after a user intentionally deletes all tasks.

## Atomic saves and recovery

1. The validated document is written to a temporary file in the same directory.
2. The temporary file is flushed and synchronized to disk.
3. The current primary is atomically copied to `<filename>.bak`.
4. The temporary file atomically replaces the primary.

When a primary is malformed, it is copied to a unique `.corrupt-<id>` file. If
the `.bak` file validates, the primary is restored and a recovery notice is made
available to the UI. If no valid backup exists, storage raises a recovery error
and never silently replaces the user's data with defaults.

Future schema versions are rejected to prevent an older app from destroying
newer data. Older versions load only when a sequential migration hook has been
registered for every required version step.
