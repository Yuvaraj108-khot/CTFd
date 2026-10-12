# Event Timing & Challenge Scheduling Feature

## Overview
The Event Timing & Challenge Scheduling system adds precision clock controls, dynamic challenge unlocking, live participant countdowns, and tamper-evident audit logging to CTFd.

---

## 1. Admin Experience

### Accessing the Event Schedule
1. Log in as an administrator (`admin` / `adminpassword`).
2. Click **Schedule** in the top navigation bar (or navigate directly to `/admin/schedule`).

### Features & Controls
- **Live Platform Telemetry**:
  - Digital competition countdown clock (`HH : MM : SS`).
  - Dynamic status badge: `LIVE`, `PAUSED`, `UPCOMING`, `ENDED`, or `ENDING_SOON` (< 1 hour remaining).
  - Shows UTC server time and local admin timezone simultaneously.
- **Quick Time Extensions & Modifiers**:
  - One-click adjustments: `+15m`, `+30m`, `+1h`, `+2h`, `-15m`, `-30m`.
- **Exact Duration & Timestamps**:
  - Set custom duration (Hours, Minutes, Seconds).
  - Explicit start time, end time, and scoreboard freeze time pickers.
  - Automatically translates between admin's local timezone and UTC storage.
  - Validates boundaries: end must be after start; freeze must be valid; shows clear errors.
- **Confirmation Preview**:
  - Before applying changes to the live CTF, a modal displays a before-and-after diff of all affected parameters.
- **Clock Controls & Emergency Actions**:
  - **Pause / Resume**: Freezes competition clock and blocks flag submissions. When resumed, end time and future challenge drop intervals are automatically extended by the pause duration.
  - **Expire Clock Immediately**: Instantly locks the event and submissions.
  - **Reset to 6-Hour CTF**: Starts a fresh 6-hour CTF clock from the current time.
- **Challenge Unlock Scheduling & Wave Drops**:
  - Set individual unlock timestamps for any challenge.
  - **Wave Drop Scheduler**: Automatically distribute challenges across 2, 3, or 4 waves evenly spaced throughout the competition.
- **Audit Log**:
  - Records every schedule change in the database with timestamp, admin username, client IP, action name, and details diff.

---

## 2. Participant / User Experience

- **Navbar Competition Telemetry**:
  - Every page displays the real-time event status and live countdown clock.
- **Challenge Board**:
  - **Upcoming Event**: Displays a prominent hero countdown banner: `Competition Starts In: [HH:MM:SS]`.
  - **Paused Event**: Shows a warning banner informing participants that submissions are frozen.
  - **Ended Event**: Shows an alert stating that submissions are closed.
  - **Locked Challenges**:
    - Scheduled challenges display a lock icon, points, and a live countdown timer (`Unlocks in MM:SS`).
    - Titles, descriptions, files, and flags are strictly hidden on the server until unlocked.
    - **Real-Time Auto-Reveal**: As soon as the unlock time arrives, challenges reveal themselves on the page without requiring a page refresh.
- **Flag Submissions**:
  - Submissions are server-enforced and disabled before event start, during pause, after event end, or before a challenge unlocks.
  - Friendly status messages explain clearly why submissions are unavailable.

---

## 3. Backend & API Reference

All schedule endpoints require authentication and admin authorization, except `/api/v1/schedule/status`.

### Public Endpoints
- `GET /api/v1/schedule/status`:
  - Returns `status` (`upcoming`, `live`, `paused`, `ended`), `server_time`, `time_remaining_seconds`, `time_to_start_seconds`, and `locked_challenges`.

### Admin-Only Endpoints
- `GET /api/v1/schedule/admin`:
  - Returns full schedule configuration, all challenge unlock times, and the 50 most recent audit logs.
- `POST /api/v1/schedule/event`:
  - Updates start, end, and freeze times. Supports `{ "preview": true }` to inspect diff before publishing.
- `POST /api/v1/schedule/pause`:
  - Toggles pause/resume with `{ "action": "pause" | "resume", "extend_end_time": true }`.
- `POST /api/v1/schedule/quick-adjust`:
  - Extends/reduces timer (`{ "seconds": 900 }`) or triggers `{ "action": "expire" | "reset" }`.
- `POST /api/v1/schedule/challenges`:
  - Sets individual unlock times (`mode="individual"`) or distributes challenges into waves (`mode="waves", "waves": 3`).

---

## 4. Database Schema
- **`schedule_audit_logs` Table**:
  - `id`: Primary key
  - `user_id`: Foreign key to `users.id`
  - `user_name`: Name of admin
  - `ip`: Client IP address
  - `action`: String (e.g. `update_event_schedule`, `pause_competition`, `resume_competition`, `quick_adjust_timer`)
  - `details`: JSON payload of previous vs new state
  - `created_at`: UTC timestamp
- **`config` Keys**:
  - `start`, `end`, `freeze` (UTC unix timestamps)
  - `paused` (boolean)
  - `paused_at` (UTC timestamp when pause began)
- **`challenges` Table**:
  - `scheduled_at` (UTC timestamp for challenge unlock)

---

## 5. Automated Tests
Run the event schedule test suite anytime with:
```bash
uv run pytest tests/test_event_schedule.py
```
