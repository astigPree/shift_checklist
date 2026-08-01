# Project Description: Shift Checklist Desktop App

## Project Overview

Shift Checklist is a simple local desktop application designed to help employees manage daily work responsibilities, scheduled attendance actions, client monitoring tasks, and occasional Shopify website updates.

The application will be built using Python and Kivy and will initially run locally on a Windows computer. It is intended as a lightweight personal productivity tool that helps the user remember important tasks during a work shift without requiring an internet connection, online account, or external server.

The application focuses on simplicity, task customization, reminders, and daily progress tracking.

---

## Problem Statement

During a work shift, the user needs to perform several recurring responsibilities, including:

* Checking client messages regularly
* Monitoring instructions from the boss
* Checking out from JDK through FastDTR at around 4:00 AM
* Checking in for Happy BUM through FastDTR at around 4:00 AM
* Completing Shopify website updates when requested
* Checking out from Happy BUM through FastDTR at around 8:00 AM

These responsibilities happen at different times and some tasks are conditional. Relying only on memory can result in missed messages, forgotten attendance actions, incomplete tasks, or delayed client responses.

A simple desktop checklist with reminders can help organize these responsibilities and reduce the chance of missing important actions.

---

## Proposed Solution

Shift Checklist will provide a customizable daily task management interface where users can create, edit, delete, schedule, and complete tasks.

The app will display all tasks for the current shift and notify the user when a scheduled task is approaching or already due.

The user will also be able to record repeated activities, such as checking client messages, and view the last time the activity was completed.

All application data will be saved locally on the computer.

---

## Main Objectives

The project aims to:

1. Help the user organize daily work responsibilities.
2. Provide reminders for time-sensitive tasks.
3. Allow all tasks to be customized.
4. Track completed and pending tasks.
5. Reduce missed FastDTR attendance actions.
6. Record when client messages were last checked.
7. Manage conditional Shopify website tasks.
8. Store task information locally without requiring an online server.
9. Provide a simple and easy-to-use Windows desktop interface.

---

## Target Users

The initial version is intended for a single user who performs client monitoring, attendance tracking, and Shopify website maintenance during a work shift.

The design may later support other employees or users who need a customizable shift-based checklist.

---

## Core Features

### 1. Daily Checklist

The main screen will display the tasks scheduled for the current day.

Each task will include:

* Task title
* Category
* Scheduled time
* Completion status
* Reminder status
* Optional notes
* Completion timestamp

Users can mark tasks as completed using a checkbox or completion button.

---

### 2. Customizable Tasks

Tasks will not be permanently hardcoded into the application.

The user can:

* Add a new task
* Edit an existing task
* Delete a task
* Change the task title
* Choose a category
* Set an optional scheduled time
* Enable or disable reminders
* Set a reminder interval
* Add notes
* Set the task as recurring or one-time
* Reorder tasks

Example custom tasks include:

* Check client messages
* Check out from JDK
* Check in for Happy BUM
* Check for Shopify update requests
* Complete assigned Shopify update
* Check out from Happy BUM

---

### 3. Task Categories

Tasks can be organized into categories such as:

* Client Monitoring
* FastDTR
* Shopify
* End of Shift
* General
* Custom Category

Categories will make the checklist easier to read and manage.

---

### 4. Scheduled Reminders

Tasks may include a scheduled time.

Example reminders:

* 3:55 AM — Prepare to check out from JDK
* 4:00 AM — Check out from JDK
* 4:00 AM — Check in for Happy BUM
* 7:55 AM — Prepare for the end-of-shift checkout
* 8:00 AM — Check out from Happy BUM

The application will check for upcoming tasks while it is running and show a desktop notification when a task is due.

---

### 5. Repeated Client Message Checks

Checking client messages happens multiple times during a shift, so it should not behave like a normal one-time task.

The app will provide a button such as:

**Client Messages Checked**

When clicked, the app will record:

* Date
* Time checked
* Optional note
* Next reminder time

Example:

```text
Last checked: 3:30 AM
Next reminder: 4:00 AM
```

The user can configure how often the app should remind them to check messages.

---

### 6. Shopify Task Management

Shopify website tasks are conditional because the boss may not request an update every day.

The application will allow the user to add a Shopify task when a request is received.

A Shopify task may include:

* Client or store name
* Task description
* Date and time requested
* Priority
* Current status
* Completion time
* Notes

Possible statuses:

* Pending
* In Progress
* Waiting for Clarification
* Ready for Review
* Completed

---

### 7. Daily Progress

The application will display the user’s current progress.

Example:

```text
Daily Progress: 6 of 8 tasks completed
```

The progress section may also display:

* Completed tasks
* Pending tasks
* Overdue tasks
* Upcoming tasks
* Last client message check

---

### 8. Automatic Daily Reset

Recurring tasks will automatically return to their pending state on the next workday.

The previous day’s completed task information will remain stored in the history.

One-time tasks will not automatically repeat unless configured by the user.

---

### 9. Daily History

The application will store previous daily records.

The history may include:

* Date
* Tasks completed
* Tasks missed
* Completion times
* Client message check records
* Shopify tasks
* FastDTR attendance actions
* Pending tasks

This allows the user to review previous work activity when needed.

---

### 10. Local Data Storage

The first version will store data locally using JSON files.

Example storage files:

```text
data/
├── tasks.json
├── daily_records.json
├── message_checks.json
└── settings.json
```

JSON is suitable for the first version because the application is small and intended for one user.

SQLite may replace JSON later when the application requires more advanced history, filtering, reporting, and data relationships.

---

## Default Tasks

The application may include the following default tasks during the first launch:

### Client Monitoring

* Check client messages regularly
* Review instructions from the boss
* Record important or pending requests

### Around 4:00 AM

* Open FastDTR
* Check out from JDK
* Confirm the JDK checkout
* Check in for Happy BUM
* Confirm the Happy BUM check-in

### Shopify

* Check for Shopify update requests
* Complete the requested Shopify update
* Test the Shopify changes
* Inform the boss when the update is completed

### Around 8:00 AM

* Check client messages one final time
* Record pending tasks
* Open FastDTR
* Check out from Happy BUM
* Confirm the Happy BUM checkout

All default tasks can be edited or deleted.

---

## Main Application Screens

### Today Screen

The Today screen will contain:

* Current date and time
* Daily progress
* Today’s task list
* Upcoming reminder
* Overdue task warning
* Client message check button
* Add task button

---

### Task Management Screen

The Task Management screen will allow the user to:

* View all available tasks
* Add a new task
* Edit a task
* Delete a task
* Enable or disable tasks
* Set recurring schedules
* Change task categories
* Configure reminder times

---

### History Screen

The History screen will display:

* Previous daily checklists
* Completed tasks
* Missed tasks
* Attendance task completion times
* Client message monitoring records
* Shopify task history

---

### Settings Screen

The Settings screen will allow the user to configure:

* Notification settings
* Reminder sound
* Client message checking interval
* Daily reset time
* Default task categories
* Start application with Windows
* Minimize behavior
* Data storage location

---

## Application Workflow

```text
Open the application
        ↓
Load today’s recurring tasks
        ↓
Display pending and completed tasks
        ↓
Check client messages regularly
        ↓
Receive scheduled reminders
        ↓
Complete FastDTR actions
        ↓
Add Shopify tasks when requested
        ↓
Mark tasks as completed
        ↓
Save completion records
        ↓
Store the daily record in history
```

---

## Technology Stack

### Programming Language

Python

### Desktop Framework

Kivy

### Interface Design

Kivy Language using `.kv` files

### Local Storage

JSON for the first version

### Future Storage

SQLite

### Scheduling

Kivy Clock

### Desktop Notifications

Plyer notification module

### Target Platform

Windows desktop

---

## Suggested Project Structure

```text
shift_checklist/
├── main.py
├── shift_checklist.kv
├── requirements.txt
│
├── models/
│   └── task.py
│
├── screens/
│   ├── today_screen.py
│   ├── task_management_screen.py
│   ├── history_screen.py
│   └── settings_screen.py
│
├── widgets/
│   ├── task_item.py
│   ├── task_form.py
│   └── progress_card.py
│
├── services/
│   ├── task_service.py
│   ├── reminder_service.py
│   ├── history_service.py
│   └── storage_service.py
│
├── data/
│   ├── tasks.json
│   ├── daily_records.json
│   ├── message_checks.json
│   └── settings.json
│
└── assets/
    ├── icons/
    └── sounds/
```

---

## Minimum Viable Product

The first working version should include only the essential features:

1. Display daily tasks.
2. Add custom tasks.
3. Edit existing tasks.
4. Delete tasks.
5. Mark tasks as completed.
6. Save tasks locally.
7. Set an optional scheduled time.
8. Show desktop reminders.
9. Record the last client message check.
10. Reset recurring tasks daily.
11. Store basic daily history.

Features such as cloud synchronization, user accounts, team collaboration, online dashboards, and client platform integrations should not be included in the first version.

---

## Limitations of the Initial Version

The initial application will have the following limitations:

* It will run only on the local Windows computer.
* Notifications will work only while the application is running.
* It will not automatically read client messages.
* It will not connect directly to FastDTR.
* It will not automatically perform Shopify updates.
* It will not synchronize data between devices.
* It will support only one local user.

These limitations are intentional to keep the first version simple and practical.

---

## Future Enhancements

Possible future improvements include:

* Minimize to system tray
* Automatically start with Windows
* Background reminder service
* SQLite database
* Search and filtering
* Daily and weekly reports
* Missed-task reports
* Export history to CSV or PDF
* Desktop notification actions
* Task priority levels
* Multiple work schedules
* Multiple client profiles
* Cloud synchronization
* Mobile companion application
* Automatic notification monitoring
* FastDTR attendance integration, when officially supported
* Shopify Admin API integration for approved tasks
* Team and supervisor dashboards

---

## Expected Outcome

The completed application will provide a simple and reliable way to manage daily shift responsibilities.

It will help the user remember scheduled FastDTR actions, monitor client messages consistently, manage Shopify update requests, and keep a basic history of completed work.

The first version will prioritize usability, customization, local storage, and fast development using Python and Kivy.
