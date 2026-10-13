import datetime
from typing import Any, Dict, List

from flask import request
from flask_restx import Namespace, Resource

from CTFd.cache import clear_challenges, clear_config, clear_standings
from CTFd.models import Challenges, ScheduleAuditLogs, db
from CTFd.utils import get_config, set_config
from CTFd.utils.dates import (
    ctf_ended,
    ctf_paused,
    ctf_started,
    isoformat,
    parse_iso_datetime,
    unix_time,
    unix_time_to_utc,
)
from CTFd.utils.decorators import admins_only
from CTFd.utils.events.schedule import (
    expire_event_now,
    get_schedule_status,
    pause_competition,
    quick_adjust_timer,
    record_schedule_audit_log,
    reset_to_default_timer,
    resume_competition,
    set_scoreboard_visibility,
    validate_event_schedule,
)
from CTFd.utils.user import get_current_user, is_admin

schedule_namespace = Namespace(
    "schedule", description="Endpoints for Event Timing and Challenge Scheduling"
)


@schedule_namespace.route("/status")
class ScheduleStatus(Resource):
    """Public endpoint providing real-time event status and locked challenge countdowns."""

    def get(self):
        status_data = get_schedule_status()

        # Find locked challenges (scheduled_at in future)
        now_dt = datetime.datetime.utcnow()
        scheduled_query = (
            Challenges.query.filter(
                Challenges.state != "hidden",
                Challenges.scheduled_at.isnot(None),
                Challenges.scheduled_at > now_dt,
            )
            .order_by(Challenges.scheduled_at.asc(), Challenges.value.asc())
            .all()
        )

        locked_chals = []
        for c in scheduled_query:
            diff_secs = max(0, int((c.scheduled_at - now_dt).total_seconds()))
            locked_chals.append(
                {
                    "id": c.id,
                    "category": c.category,
                    "value": c.value,
                    "scheduled_at": c.scheduled_at.isoformat() + "Z",
                    "unlock_in_seconds": diff_secs,
                    "is_locked": True,
                }
            )

        status_data["locked_challenges"] = locked_chals
        return {"success": True, "data": status_data}


@schedule_namespace.route("/admin")
class ScheduleAdminData(Resource):
    """Admin-only endpoint to get full schedule configuration, challenge schedule, and audit logs."""

    @admins_only
    def get(self):
        status_data = get_schedule_status()

        # Fetch all challenges with scheduling info
        chals = Challenges.query.order_by(Challenges.category.asc(), Challenges.value.asc()).all()
        challenges_data = []
        now_dt = datetime.datetime.utcnow()
        for c in chals:
            is_locked = bool(c.scheduled_at and c.scheduled_at > now_dt)
            challenges_data.append(
                {
                    "id": c.id,
                    "name": c.name,
                    "category": c.category,
                    "value": c.value,
                    "state": c.state,
                    "scheduled_at": c.scheduled_at.isoformat() + "Z" if c.scheduled_at else None,
                    "is_locked": is_locked,
                    "unlock_in_seconds": max(0, int((c.scheduled_at - now_dt).total_seconds())) if is_locked else 0,
                }
            )

        # Fetch recent audit logs (last 50)
        logs = (
            ScheduleAuditLogs.query.order_by(ScheduleAuditLogs.created_at.desc())
            .limit(50)
            .all()
        )
        audit_data = []
        for l in logs:
            audit_data.append(
                {
                    "id": l.id,
                    "user_id": l.user_id,
                    "user_name": l.user_name,
                    "ip": l.ip,
                    "action": l.action,
                    "details": l.details,
                    "created_at": l.created_at.isoformat() + "Z",
                }
            )

        return {
            "success": True,
            "data": {
                "event": status_data,
                "challenges": challenges_data,
                "audit_logs": audit_data,
            },
        }


@schedule_namespace.route("/event")
class ScheduleEventUpdate(Resource):
    """Admin-only endpoint to update or preview event start, end, and freeze times."""

    @admins_only
    def post(self):
        req_data = request.get_json() or {}
        preview_mode = bool(req_data.get("preview", False))

        start_val = req_data.get("start")
        end_val = req_data.get("end")
        freeze_val = req_data.get("freeze")

        is_valid, err_msg, start_ts, end_ts, freeze_ts = validate_event_schedule(
            start_val, end_val, freeze_val
        )
        if not is_valid:
            return {"success": False, "errors": {"schedule": err_msg}}, 400

        current_start = int(get_config("start") or 0) or None
        current_end = int(get_config("end") or 0) or None
        current_freeze = int(get_config("freeze") or 0) or None

        preview_summary = {
            "previous": {
                "start": current_start,
                "start_iso": isoformat(unix_time_to_utc(current_start)) if current_start else None,
                "end": current_end,
                "end_iso": isoformat(unix_time_to_utc(current_end)) if current_end else None,
                "freeze": current_freeze,
                "freeze_iso": isoformat(unix_time_to_utc(current_freeze)) if current_freeze else None,
            },
            "new": {
                "start": start_ts,
                "start_iso": isoformat(unix_time_to_utc(start_ts)) if start_ts else None,
                "end": end_ts,
                "end_iso": isoformat(unix_time_to_utc(end_ts)) if end_ts else None,
                "freeze": freeze_ts,
                "freeze_iso": isoformat(unix_time_to_utc(freeze_ts)) if freeze_ts else None,
            },
        }

        # If preview requested, return diff without updating database
        if preview_mode:
            return {
                "success": True,
                "preview": True,
                "data": preview_summary,
            }

        # Apply changes
        set_config("start", start_ts)
        set_config("end", end_ts)
        set_config("freeze", freeze_ts)
        clear_config()
        clear_standings()

        admin_user = get_current_user()
        record_schedule_audit_log(
            action="update_event_schedule",
            details=preview_summary,
            user=admin_user,
        )

        return {
            "success": True,
            "message": "Event schedule successfully updated.",
            "data": get_schedule_status(),
        }


@schedule_namespace.route("/pause")
class SchedulePauseToggle(Resource):
    """Admin-only endpoint to pause or resume the event."""

    @admins_only
    def post(self):
        req_data = request.get_json() or {}
        action = req_data.get("action")  # "pause" or "resume"
        extend = bool(req_data.get("extend_end_time", True))
        admin_user = get_current_user()

        if action == "pause":
            res = pause_competition(admin_user=admin_user)
        elif action == "resume":
            res = resume_competition(extend_end_time=extend, admin_user=admin_user)
        else:
            # Auto-toggle based on current state
            if ctf_paused():
                res = resume_competition(extend_end_time=extend, admin_user=admin_user)
            else:
                res = pause_competition(admin_user=admin_user)

        res["status"] = get_schedule_status()
        return res


@schedule_namespace.route("/quick-adjust")
class ScheduleQuickAdjust(Resource):
    """Admin-only endpoint for quick time modifiers (+15m, +30m, +1h, -15m, expire, reset)."""

    @admins_only
    def post(self):
        req_data = request.get_json() or {}
        action = req_data.get("action")
        admin_user = get_current_user()

        if action == "expire":
            res = expire_event_now(admin_user=admin_user)
        elif action == "reset":
            hours = int(req_data.get("hours", 6))
            res = reset_to_default_timer(duration_hours=hours, admin_user=admin_user)
        elif "seconds" in req_data:
            seconds = int(req_data["seconds"])
            res = quick_adjust_timer(seconds=seconds, admin_user=admin_user)
        else:
            return {"success": False, "errors": {"action": "Invalid quick adjust parameters."}}, 400

        res["status"] = get_schedule_status()
        return res


@schedule_namespace.route("/challenges")
class ScheduleChallengesUpdate(Resource):
    """Admin-only endpoint to update challenge unlock times or configure waves."""

    @admins_only
    def post(self):
        req_data = request.get_json() or {}
        mode = req_data.get("mode", "individual")  # "individual" or "waves"
        admin_user = get_current_user()

        if mode == "waves":
            # Auto-align question drops evenly across competition duration
            waves_count = int(req_data.get("waves", 3))
            if waves_count < 1:
                return {"success": False, "errors": {"waves": "Wave count must be at least 1."}}, 400

            now_ts = int(datetime.datetime.utcnow().timestamp())
            start_ts = int(get_config("start") or now_ts)
            end_ts = int(get_config("end") or (start_ts + 6 * 3600))
            if end_ts <= start_ts:
                end_ts = start_ts + 6 * 3600

            duration = end_ts - start_ts
            interval = duration // waves_count

            # Sort challenges by position / value
            all_chals = Challenges.query.order_by(Challenges.position.asc(), Challenges.value.asc()).all()
            if not all_chals:
                return {"success": True, "message": "No challenges to schedule."}

            chals_per_wave = max(1, len(all_chals) // waves_count)
            changes = []

            for idx, chal in enumerate(all_chals):
                wave_index = min(waves_count - 1, idx // chals_per_wave)
                if wave_index == 0:
                    unlock_dt = None  # Immediately unlocked
                else:
                    unlock_ts = start_ts + (wave_index * interval)
                    unlock_dt = datetime.datetime.utcfromtimestamp(unlock_ts)

                old_sched = chal.scheduled_at.isoformat() + "Z" if chal.scheduled_at else None
                chal.scheduled_at = unlock_dt
                changes.append(
                    {
                        "id": chal.id,
                        "name": chal.name,
                        "old_scheduled_at": old_sched,
                        "new_scheduled_at": unlock_dt.isoformat() + "Z" if unlock_dt else None,
                        "wave": wave_index + 1,
                    }
                )

            db.session.commit()
            clear_challenges()

            record_schedule_audit_log(
                action="schedule_challenge_waves",
                details={"waves": waves_count, "interval_seconds": interval, "changes": changes},
                user=admin_user,
            )

            return {
                "success": True,
                "message": f"Successfully distributed {len(all_chals)} challenges across {waves_count} waves.",
                "changes": changes,
            }

        # Individual challenge unlock time edits
        challenges_list = req_data.get("challenges", [])
        if not challenges_list:
            return {"success": False, "errors": {"challenges": "No challenge data provided."}}, 400

        changes = []
        for item in challenges_list:
            c_id = item.get("id")
            unlock_str = item.get("scheduled_at")
            chal = Challenges.query.filter_by(id=c_id).first()
            if not chal:
                continue

            old_sched = chal.scheduled_at.isoformat() + "Z" if chal.scheduled_at else None
            new_dt = None
            if unlock_str not in (None, "", "null"):
                try:
                    new_dt = parse_iso_datetime(unlock_str)
                except Exception:
                    return {
                        "success": False,
                        "errors": {"scheduled_at": f"Invalid datetime format for challenge {chal.name} ({c_id})."},
                    }, 400

            chal.scheduled_at = new_dt
            changes.append(
                {
                    "id": chal.id,
                    "name": chal.name,
                    "old_scheduled_at": old_sched,
                    "new_scheduled_at": new_dt.isoformat() + "Z" if new_dt else None,
                }
            )

        db.session.commit()
        clear_challenges()

        record_schedule_audit_log(
            action="update_challenge_unlock_times",
            details={"changes": changes},
            user=admin_user,
        )

        return {
            "success": True,
            "message": f"Updated unlock times for {len(changes)} challenges.",
            "changes": changes,
        }


@schedule_namespace.route("/scoreboard-visibility")
class ScheduleScoreboardVisibility(Resource):
    """Admin-only endpoint to inspect and toggle scoreboard/leaderboard visibility for participants."""

    @admins_only
    def get(self):
        status = get_schedule_status()
        return {
            "success": True,
            "data": {
                "score_visibility": status.get("score_visibility"),
                "is_hidden": status.get("scores_hidden_from_users", False),
            },
        }

    @admins_only
    def post(self):
        req_data = request.get_json() or {}
        action = req_data.get("action")
        visibility = req_data.get("visibility")

        if action == "hide" or visibility == "hidden":
            target = "hidden"
        elif action == "show" or visibility == "public":
            target = "public"
        elif visibility:
            target = visibility
        else:
            status = get_schedule_status()
            target = "public" if status.get("scores_hidden_from_users") else "hidden"

        admin_user = get_current_user()
        result = set_scoreboard_visibility(visibility=target, admin_user=admin_user)
        return {"success": True, "data": result}

