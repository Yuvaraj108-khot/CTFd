from flask import abort, redirect, render_template, request, url_for

from CTFd.admin import admin
from CTFd.models import Challenges, Flags, Solves, Tags, db
from CTFd.plugins.challenges import CHALLENGE_CLASSES, get_chal_class
from CTFd.schemas.tags import TagSchema
from CTFd.utils.decorators import admins_only
from CTFd.utils.security.signing import serialize
from CTFd.utils.uploads import upload_file
from CTFd.utils.user import get_current_team, get_current_user


@admin.route("/admin/challenges")
@admins_only
def challenges_listing():
    q = request.args.get("q")
    field = request.args.get("field")
    filters = []

    if q:
        # The field exists as an exposed column
        if Challenges.__mapper__.has_property(field):
            filters.append(getattr(Challenges, field).like("%{}%".format(q)))

    query = Challenges.query.filter(*filters).order_by(Challenges.id.asc())
    challenges = query.all()
    total = query.count()

    return render_template(
        "admin/challenges/challenges.html",
        challenges=challenges,
        total=total,
        q=q,
        field=field,
    )


@admin.route("/admin/challenges/<int:challenge_id>")
@admins_only
def challenges_detail(challenge_id):
    challenges = dict(
        Challenges.query.with_entities(Challenges.id, Challenges.name).all()
    )
    challenge = Challenges.query.filter_by(id=challenge_id).first_or_404()
    solves = (
        Solves.query.filter_by(challenge_id=challenge.id)
        .order_by(Solves.date.asc())
        .all()
    )
    flags = Flags.query.filter_by(challenge_id=challenge.id).all()

    try:
        challenge_class = get_chal_class(challenge.type)
    except KeyError:
        abort(
            500,
            f"The underlying challenge type ({challenge.type}) is not installed. This challenge can not be loaded.",
        )

    update_j2 = render_template(
        challenge_class.templates["update"].lstrip("/"), challenge=challenge
    )

    update_script = url_for(
        "views.static_html", route=challenge_class.scripts["update"].lstrip("/")
    )
    return render_template(
        "admin/challenges/challenge.html",
        update_template=update_j2,
        update_script=update_script,
        challenge=challenge,
        challenges=challenges,
        solves=solves,
        flags=flags,
    )


@admin.route("/admin/challenges/preview/<int:challenge_id>")
@admins_only
def challenges_preview(challenge_id):
    challenge = Challenges.query.filter_by(id=challenge_id).first_or_404()
    chal_class = get_chal_class(challenge.type)
    user = get_current_user()
    team = get_current_team()

    files = []
    for f in challenge.files:
        token = {
            "user_id": user.id,
            "team_id": team.id if team else None,
            "file_id": f.id,
        }
        files.append(url_for("views.files", path=f.location, token=serialize(token)))

    tags = [
        tag["value"] for tag in TagSchema("user", many=True).dump(challenge.tags).data
    ]

    content = render_template(
        chal_class.templates["view"].lstrip("/"),
        solves=None,
        solved_by_me=False,
        files=files,
        tags=tags,
        hints=challenge.hints,
        max_attempts=challenge.max_attempts,
        attempts=0,
        challenge=challenge,
        rating=None,
        ratings=None,
    )
    return render_template(
        "admin/challenges/preview.html", content=content, challenge=challenge
    )


@admin.route("/admin/challenges/new", methods=["GET", "POST"])
@admins_only
def challenges_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip()
        custom_category = request.form.get("custom_category", "").strip()
        if category == "Custom" and custom_category:
            category = custom_category

        difficulty = request.form.get("difficulty", "Easy").strip()
        source_track = request.form.get("source_track", "ACM").strip()
        custom_track = request.form.get("custom_track", "").strip()
        if source_track == "Custom" and custom_track:
            source_track = custom_track

        value = request.form.get("value", 100)
        try:
            value = int(value)
        except (ValueError, TypeError):
            value = 100

        description = request.form.get("description", "").strip()
        flag = request.form.get("flag", "").strip()
        flag_data = request.form.get("flag_data", "")
        state = request.form.get("state", "visible")

        sandbox_enabled = (
            request.form.get("sandbox_enabled") == "on"
            or request.form.get("sandbox_enabled") == "true"
        )
        connection_info = (
            request.form.get("connection_info", "").strip() if sandbox_enabled else None
        )

        gdrive_links = request.form.getlist("gdrive_links[]") or request.form.getlist("gdrive_links")
        gdrive_names = request.form.getlist("gdrive_names[]") or request.form.getlist("gdrive_names")

        if gdrive_links:
            links_md = "\n\n### 🔗 Attachments & Links\n"
            for idx, link in enumerate(gdrive_links):
                if link and link.strip():
                    lname = (
                        gdrive_names[idx].strip()
                        if idx < len(gdrive_names) and gdrive_names[idx].strip()
                        else "Google Drive Link"
                    )
                    links_md += f"- [{lname}]({link.strip()})\n"
            description += links_md

        scheduled_at_val = request.form.get("scheduled_at")
        scheduled_dt = None
        if scheduled_at_val and scheduled_at_val.strip():
            try:
                from CTFd.utils.dates import parse_iso_datetime
                scheduled_dt = parse_iso_datetime(scheduled_at_val.strip())
            except Exception:
                scheduled_dt = None

        chal = Challenges(
            name=name,
            category=category,
            description=description,
            value=value,
            state=state,
            type="standard",
            connection_info=connection_info,
            scheduled_at=scheduled_dt,
        )
        db.session.add(chal)
        db.session.commit()

        if difficulty:
            t_diff = Tags(challenge_id=chal.id, value=difficulty)
            db.session.add(t_diff)
        if source_track:
            t_track = Tags(challenge_id=chal.id, value=f"Track: {source_track}")
            db.session.add(t_track)

        if flag:
            f = Flags(
                challenge_id=chal.id,
                content=flag,
                type="static",
                data=flag_data,
            )
            db.session.add(f)

        db.session.commit()

        files = request.files.getlist("files") or request.files.getlist("files[]")
        for f in files:
            if f and f.filename:
                upload_file(file=f, challenge_id=chal.id, type="challenge")

        from CTFd.cache import clear_challenges
        clear_challenges()

        if (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or request.is_json
            or request.form.get("ajax") == "true"
        ):
            return {"success": True, "data": {"id": chal.id}}

        return redirect(url_for("admin.challenges_listing"))

    types = CHALLENGE_CLASSES.keys()
    return render_template("admin/challenges/new.html", types=types)

