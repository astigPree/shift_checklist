# Shift Checklist 0.1.0

This is the first local Windows release of Shift Checklist.

## Install and launch

1. Download and verify `ShiftChecklist-0.1.0-windows-x64.zip`.
2. Extract the complete `ShiftChecklist` folder to a writable location.
3. Open the folder and double-click `ShiftChecklist.exe`.

Keep the complete folder together; do not run the executable directly from the
ZIP archive. Python is not required on the target computer.

## Included workflows

- Active overnight-shift checklist and progress
- Daily and one-time task management
- Manual Shopify request tracking
- Client-message check history and reminders
- Scheduled reminders while the app is open
- Closed-shift history and local settings
- Atomic local storage, backup recovery, and rotating logs

## Important limitations

The app must remain running for reminders. It does not read messages, operate
FastDTR, call Shopify APIs, use cloud storage, or support multiple users/devices.
Back up the local data directory manually; there is no cloud backup.

See `README.md` and `docs\USER_GUIDE.md` in the extracted folder for complete
instructions.
