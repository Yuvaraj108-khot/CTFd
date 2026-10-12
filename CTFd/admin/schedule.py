import datetime
from flask import render_template

from CTFd.admin import admin
from CTFd.models import Challenges, ScheduleAuditLogs
from CTFd.utils.decorators import admins_only
from CTFd.utils.events.schedule import get_schedule_status


@admin.route("/admin/schedule")
@admins_only
def event_schedule():
    status_data = get_schedule_status()
    now_dt = datetime.datetime.utcnow()

    # Query all challenges
    challenges = Challenges.query.order_by(Challenges.category.asc(), Challenges.value.asc(), Challenges.id.asc()).all()
    challenges_list = []
    for c in challenges:
        is_locked = bool(c.scheduled_at and c.scheduled_at > now_dt)
        challenges_list.append(
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

    # Query recent schedule audit logs
    audit_logs = ScheduleAuditLogs.query.order_by(ScheduleAuditLogs.created_at.desc()).limit(50).all()

    return render_template(
        "admin/schedule.html",
        event=status_data,
        challenges=challenges_list,
        audit_logs=audit_logs,
    )
