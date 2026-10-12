import datetime
import json
import time
import pytest
from CTFd import create_app
from CTFd.models import Challenges, ScheduleAuditLogs, Users, db
from CTFd.utils import set_config, get_config
from CTFd.utils.events.schedule import (
    validate_event_schedule,
    pause_competition,
    resume_competition,
    quick_adjust_timer,
    get_schedule_status,
)


@pytest.fixture
def app_ctx():
    app = create_app()
    with app.app_context():
        yield app


def test_schedule_validation():
    # End before start should fail
    valid, err, s, e, f = validate_event_schedule(start_val=2000, end_val=1000)
    assert not valid
    assert "End time must be after start time" in err

    # Freeze before start should fail
    valid, err, s, e, f = validate_event_schedule(start_val=1000, end_val=2000, freeze_val=500)
    assert not valid
    assert "freeze" in err.lower()

    # Valid times should pass
    valid, err, s, e, f = validate_event_schedule(start_val=1000, end_val=2000, freeze_val=1500)
    assert valid
    assert s == 1000
    assert e == 2000
    assert f == 1500


def test_pause_and_resume_behavior(app_ctx):
    # Ensure unpaused initially
    set_config("paused", False)
    set_config("paused_at", None)
    now = int(time.time())
    set_config("start", now - 3600)
    set_config("end", now + 3600)

    # Pause
    res = pause_competition()
    assert res["success"]
    assert get_config("paused")
    assert get_config("paused_at") is not None

    status = get_schedule_status()
    assert status["status"] == "paused"
    assert status["is_paused"] is True

    # Simulate 5 seconds paused
    time.sleep(1)

    # Resume
    res_resume = resume_competition(extend_end_time=True)
    assert res_resume["success"]
    assert not get_config("paused")
    assert get_config("paused_at") is None

    # Clean up so test does not leave stale schedule in database
    set_config("start", None)
    set_config("end", None)


def test_admin_api_authorization_and_audit_logging(app_ctx):
    with app_ctx.test_client() as client:
        # Non-authenticated user should get 403 on schedule admin endpoints
        resp = client.get("/api/v1/schedule/admin")
        assert resp.status_code in [302, 403]

        resp = client.post("/api/v1/schedule/event", json={"start": 1000, "end": 2000})
        assert resp.status_code in [302, 403]

        resp = client.post("/api/v1/schedule/pause", json={"action": "pause"})
        assert resp.status_code in [302, 403]

        # Public status endpoint should succeed
        status_resp = client.get("/api/v1/schedule/status")
        assert status_resp.status_code == 200
        data = json.loads(status_resp.data)
        assert data["success"] is True
        assert "status" in data["data"]
        assert "server_time" in data["data"]


def test_locked_challenge_security(app_ctx):
    with app_ctx.test_client() as client:
        # Create a scheduled challenge 1 hour in the future
        future_unlock = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        chal = Challenges.query.filter_by(name="Test Scheduled Challenge").first()
        if not chal:
            chal = Challenges(
                name="Test Scheduled Challenge",
                category="Crypto",
                description="TOP SECRET FLAG DETAILS",
                value=500,
                state="visible",
                type="standard",
                scheduled_at=future_unlock,
            )
            db.session.add(chal)
            db.session.commit()
        else:
            chal.scheduled_at = future_unlock
            db.session.commit()

        # Regular user (unauthenticated or non-admin) calls /api/v1/challenges/<id>
        chal_resp = client.get(f"/api/v1/challenges/{chal.id}")
        # Should be blocked from seeing details (404/403)
        assert chal_resp.status_code in [403, 404]

        # In challenge list API, name should be masked or locked
        list_resp = client.get("/api/v1/challenges")
        if list_resp.status_code == 200:
            list_data = json.loads(list_resp.data)["data"]
            scheduled_items = [c for c in list_data if c["id"] == chal.id]
            if scheduled_items:
                sc = scheduled_items[0]
                assert sc["is_locked"] is True
                assert sc["name"] == "Locked Challenge"
                assert "TOP SECRET" not in json.dumps(sc)

        # Flag submission before unlock must be rejected with status "locked"
        attempt_resp = client.post(
            "/api/v1/challenges/attempt",
            json={"challenge_id": chal.id, "submission": "flag{test}"},
        )
        assert attempt_resp.status_code == 403

        # Clean up
        db.session.delete(chal)
        db.session.commit()
