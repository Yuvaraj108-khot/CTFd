import datetime
import json
import time
from typing import Any, Dict, List, Optional, Tuple

from flask import has_request_context, request, session

from CTFd.cache import cache, clear_challenges, clear_config, clear_standings
from CTFd.models import Challenges, ScheduleAuditLogs, Users, db
from CTFd.utils import get_config, set_config
from CTFd.utils.dates import (
    ctf_ended,
    ctf_paused,
    ctf_started,
    ctftime,
    isoformat,
    parse_iso_datetime,
    unix_time,
    unix_time_to_utc,
)
from CTFd.utils.logging import log
from CTFd.utils.user import get_current_user, get_ip, is_admin


def get_server_utc_timestamp() -> int:
    """Returns current UTC timestamp as integer seconds."""
    return int(time.time())


def get_schedule_status() -> Dict[str, Any]:
    """Computes comprehensive event timing and status for clients."""
    now = get_server_utc_timestamp()
    start_ts = get_config("start")
    end_ts = get_config("end")
    freeze_ts = get_config("freeze")
    is_p = ctf_paused()
    paused_at = get_config("paused_at")

    start = int(start_ts) if start_ts else None
    end = int(end_ts) if end_ts else None
    freeze = int(freeze_ts) if freeze_ts else None
    paused_at_int = int(paused_at) if paused_at else None

    # Determine status: "upcoming", "live", "paused", "ended"
    if is_p:
        status = "paused"
    elif end and now >= end:
        status = "ended"
    elif start and now < start:
        status = "upcoming"
    else:
        status = "live"

    # Compute remaining duration for live/paused
    time_remaining_seconds: Optional[int] = None
    if end:
        if is_p and paused_at_int:
            # During pause, remaining time is frozen from paused_at
            time_remaining_seconds = max(0, end - paused_at_int)
        elif not is_p:
            time_remaining_seconds = max(0, end - now)
        else:
            time_remaining_seconds = max(0, end - now)

    time_to_start_seconds: Optional[int] = None
    if start and now < start:
        time_to_start_seconds = max(0, start - now)

    is_frozen = bool(freeze and now >= freeze and (not end or now < end))
    score_vis = get_config("score_visibility", default="public")
    scores_hidden = score_vis in ["hidden", "admins"]

    return {
        "status": status,
        "is_paused": is_p,
        "is_frozen": is_frozen,
        "score_visibility": score_vis,
        "scores_hidden_from_users": scores_hidden,
        "server_time": now,
        "server_time_iso": datetime.datetime.utcnow().isoformat() + "Z",
        "start": start,
        "start_iso": isoformat(unix_time_to_utc(start)) if start else None,
        "end": end,
        "end_iso": isoformat(unix_time_to_utc(end)) if end else None,
        "freeze": freeze,
        "freeze_iso": isoformat(unix_time_to_utc(freeze)) if freeze else None,
        "paused_at": paused_at_int,
        "time_remaining_seconds": time_remaining_seconds,
        "time_to_start_seconds": time_to_start_seconds,
    }


def record_schedule_audit_log(
    action: str,
    details: Dict[str, Any],
    user: Optional[Users] = None,
    ip: Optional[str] = None,
) -> ScheduleAuditLogs:
    """Records an audit log entry into the database and application log."""
    if has_request_context():
        if user is None:
            user = get_current_user()
        if ip is None:
            ip = get_ip()
        user_id = user.id if user else session.get("id")
        user_name = user.name if user else "System/Admin"
    else:
        user_id = user.id if user else None
        user_name = user.name if user else "System/CLI"
        if ip is None:
            ip = "127.0.0.1"

    audit_entry = ScheduleAuditLogs(
        user_id=user_id,
        user_name=user_name,
        ip=ip,
        action=action,
        details=details,
        created_at=datetime.datetime.utcnow(),
    )
    db.session.add(audit_entry)
    db.session.commit()

    # Also record to CTFd application log if in request context
    if has_request_context():
        log(
            "schedule",
            "[{date}] {ip} - {user_name} ({user_id}) performed schedule action '{action}': {details}",
            user_name=user_name,
            user_id=user_id,
            action=action,
            details=json.dumps(details),
        )
    return audit_entry


def validate_event_schedule(
    start_val: Optional[Any],
    end_val: Optional[Any],
    freeze_val: Optional[Any] = None,
) -> Tuple[bool, Optional[str], Optional[int], Optional[int], Optional[int]]:
    """
    Validates event start, end, and freeze times.
    Converts inputs (integers, strings, or ISO datetimes) to UTC unix timestamps.
    Returns (is_valid, error_message, start_ts, end_ts, freeze_ts).
    """
    def to_timestamp(val):
        if val in (None, "", "null"):
            return None
        if isinstance(val, (int, float)):
            return int(val)
        if isinstance(val, str):
            val_str = val.strip()
            if not val_str:
                return None
            if val_str.isdigit():
                return int(val_str)
            # Parse ISO datetime
            try:
                dt = parse_iso_datetime(val_str)
                if dt:
                    return unix_time(dt)
            except Exception:
                raise ValueError(f"Could not parse datetime string: {val_str}")
        if isinstance(val, datetime.datetime):
            return unix_time(val)
        raise ValueError(f"Unrecognized datetime format: {val}")

    try:
        start_ts = to_timestamp(start_val)
        end_ts = to_timestamp(end_val)
        freeze_ts = to_timestamp(freeze_val)
    except ValueError as e:
        return False, str(e), None, None, None

    if start_ts and end_ts:
        if end_ts <= start_ts:
            return False, "End time must be after start time.", None, None, None

    if freeze_ts:
        if start_ts and freeze_ts < start_ts:
            return False, "Score freeze time cannot be before the event start time.", None, None, None
        if end_ts and freeze_ts > end_ts:
            return False, "Score freeze time cannot be after the event end time.", None, None, None

    return True, None, start_ts, end_ts, freeze_ts


def pause_competition(admin_user: Optional[Users] = None) -> Dict[str, Any]:
    """Pauses the competition and marks paused_at."""
    if ctf_paused():
        return {"success": False, "message": "Competition is already paused."}

    now = get_server_utc_timestamp()
    set_config("paused", True)
    set_config("paused_at", now)
    clear_config()

    details = {
        "paused_at": now,
        "paused_at_iso": datetime.datetime.utcnow().isoformat() + "Z",
    }
    record_schedule_audit_log(
        action="pause_competition",
        details=details,
        user=admin_user,
    )
    return {"success": True, "message": "Competition has been paused.", "paused_at": now}


def resume_competition(extend_end_time: bool = True, admin_user: Optional[Users] = None) -> Dict[str, Any]:
    """Resumes the competition and automatically extends end time & unlocks by paused duration."""
    if not ctf_paused():
        return {"success": False, "message": "Competition is not paused."}

    now = get_server_utc_timestamp()
    paused_at = int(get_config("paused_at") or 0)
    pause_duration = max(0, now - paused_at) if paused_at else 0

    end = int(get_config("end") or 0)
    new_end = end
    if extend_end_time and end and pause_duration > 0:
        new_end = end + pause_duration
        set_config("end", new_end)

    # Shift freeze time if it was in the future relative to paused_at
    freeze = int(get_config("freeze") or 0)
    new_freeze = freeze
    if extend_end_time and freeze and paused_at and freeze > paused_at and pause_duration > 0:
        new_freeze = freeze + pause_duration
        set_config("freeze", new_freeze)

    # Shift future challenge unlocks by the pause duration
    shifted_challenges = 0
    if extend_end_time and pause_duration > 0:
        cutoff = datetime.datetime.utcfromtimestamp(paused_at) if paused_at else datetime.datetime.utcnow()
        future_chals = Challenges.query.filter(Challenges.scheduled_at > cutoff).all()
        for chal in future_chals:
            chal.scheduled_at = chal.scheduled_at + datetime.timedelta(seconds=pause_duration)
            shifted_challenges += 1
        if shifted_challenges:
            db.session.commit()
            clear_challenges()

    set_config("paused", False)
    set_config("paused_at", None)
    clear_config()
    clear_standings()

    details = {
        "paused_at": paused_at,
        "resumed_at": now,
        "pause_duration_seconds": pause_duration,
        "extended_end_time": extend_end_time,
        "old_end": end,
        "new_end": new_end,
        "shifted_challenges_count": shifted_challenges,
    }
    record_schedule_audit_log(
        action="resume_competition",
        details=details,
        user=admin_user,
    )
    return {
        "success": True,
        "message": f"Competition resumed! Duration extended by {pause_duration}s." if pause_duration else "Competition resumed.",
        "pause_duration_seconds": pause_duration,
        "new_end": new_end,
    }


def quick_adjust_timer(seconds: int, admin_user: Optional[Users] = None) -> Dict[str, Any]:
    """Adds or subtracts seconds from the event end time."""
    now = get_server_utc_timestamp()
    current_end = int(get_config("end") or 0)

    # If end was never set, start from now
    base_end = current_end if current_end and current_end > now else now
    new_end = max(now + 60, base_end + seconds)

    set_config("end", new_end)
    clear_config()
    clear_standings()

    details = {
        "adjustment_seconds": seconds,
        "old_end": current_end,
        "new_end": new_end,
        "new_end_iso": isoformat(unix_time_to_utc(new_end)),
    }
    record_schedule_audit_log(
        action="quick_adjust_timer",
        details=details,
        user=admin_user,
    )
    return {
        "success": True,
        "message": f"Clock adjusted by {seconds // 60} minutes.",
        "old_end": current_end,
        "new_end": new_end,
    }


def expire_event_now(admin_user: Optional[Users] = None) -> Dict[str, Any]:
    """Immediately ends the competition clock."""
    now = get_server_utc_timestamp()
    current_end = int(get_config("end") or 0)

    # Set end to right now
    set_config("end", now)
    set_config("paused", False)
    set_config("paused_at", None)
    clear_config()
    clear_standings()

    details = {
        "old_end": current_end,
        "new_end": now,
        "action": "expired_immediately",
    }
    record_schedule_audit_log(
        action="expire_competition_now",
        details=details,
        user=admin_user,
    )
    return {"success": True, "message": "Competition clock expired immediately.", "end": now}


def reset_to_default_timer(duration_hours: int = 6, admin_user: Optional[Users] = None) -> Dict[str, Any]:
    """Resets CTF clock to a fresh duration starting from now."""
    now = get_server_utc_timestamp()
    new_end = now + (duration_hours * 3600)

    set_config("start", now)
    set_config("end", new_end)
    set_config("freeze", None)
    set_config("paused", False)
    set_config("paused_at", None)
    clear_config()
    clear_standings()

    details = {
        "duration_hours": duration_hours,
        "start": now,
        "end": new_end,
    }
    record_schedule_audit_log(
        action="reset_default_timer",
        details=details,
        user=admin_user,
    )
    return {
        "success": True,
        "message": f"Reset competition clock to {duration_hours}-hour CTF.",
        "start": now,
        "end": new_end,
    }


def set_scoreboard_visibility(visibility: str, admin_user: Optional[Users] = None) -> Dict[str, Any]:
    """
    Sets scoreboard visibility (e.g. 'public' or 'hidden') and logs to audit log.
    When set to 'hidden', non-admin participants cannot view the scoreboard or rankings.
    """
    from CTFd.constants.options import ConfigTypes, ScoreVisibilityTypes

    valid_types = [
        ScoreVisibilityTypes.PUBLIC,
        ScoreVisibilityTypes.PRIVATE,
        ScoreVisibilityTypes.HIDDEN,
        ScoreVisibilityTypes.ADMINS,
    ]
    if visibility not in valid_types:
        raise ValueError(f"Invalid visibility type: {visibility}. Must be one of {valid_types}")

    prev = get_config(ConfigTypes.SCORE_VISIBILITY, default=ScoreVisibilityTypes.PUBLIC)
    set_config(ConfigTypes.SCORE_VISIBILITY, visibility)
    clear_config()
    clear_standings()
    clear_challenges()

    is_hidden = visibility in [ScoreVisibilityTypes.HIDDEN, ScoreVisibilityTypes.ADMINS]
    record_schedule_audit_log(
        action="toggle_scoreboard_visibility",
        details={
            "previous_visibility": prev,
            "new_visibility": visibility,
            "hidden_from_users": is_hidden,
        },
        user=admin_user,
    )

    return {
        "success": True,
        "score_visibility": visibility,
        "is_hidden": is_hidden,
        "message": "Scoreboard is now hidden from participants." if is_hidden else "Scoreboard is now visible to participants.",
    }

