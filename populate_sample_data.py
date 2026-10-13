import datetime
import random
from CTFd import create_app
from CTFd.models import (
    Users,
    Teams,
    Challenges,
    Flags,
    Solves,
    Awards,
    db,
)
from CTFd.cache import clear_challenges, clear_config, clear_standings

app = create_app()

with app.app_context():
    print("Populating sample data for CTFd...")

    # 1. Categories and Challenges
    challenge_configs = [
        {"name": "Warmup: Base64 Mystery", "category": "Crypto", "value": 100, "flag": "flag{b4s3_64_1s_n0t_3ncrypt10n}"},
        {"name": "SQLi Injection Basics", "category": "Web", "value": 150, "flag": "flag{1_equ4ls_1_alw4ys_tru3}"},
        {"name": "Hidden in the Pixels", "category": "Forensics", "value": 200, "flag": "flag{st3g4n0_m4st3r_2026}"},
        {"name": "Binary Patching 101", "category": "Reverse", "value": 250, "flag": "flag{gdb_p4tch_jmp_n0p}"},
        {"name": "JWT Token Tampering", "category": "Web", "value": 300, "flag": "flag{n0n3_4lg0r1thm_byp4ss}"},
        {"name": "RSA Small Exponent Attack", "category": "Crypto", "value": 350, "flag": "flag{h4st4d_br04dc4st_4tt4ck}"},
        {"name": "Memory Dump Analysis", "category": "Forensics", "value": 400, "flag": "flag{v0l4t1l1ty_pr0c3ss_tr33}"},
        {"name": "ROP Emporium Jump", "category": "Pwn", "value": 450, "flag": "flag{r3turn_0r13nt3d_pr0gr4mm1ng}"},
        {"name": "Future Wave 1 Challenge", "category": "Misc", "value": 200, "flag": "flag{unl0ck3d_w4v3_1}", "scheduled_offset_minutes": 30},
        {"name": "Future Wave 2 Boss", "category": "Reverse", "value": 500, "flag": "flag{f1n4l_b0ss_d3f34t3d}", "scheduled_offset_minutes": 90},
    ]

    now_utc = datetime.datetime.utcnow()
    created_chals = []

    for c_cfg in challenge_configs:
        existing = Challenges.query.filter_by(name=c_cfg["name"]).first()
        if not existing:
            sched_at = None
            if "scheduled_offset_minutes" in c_cfg:
                sched_at = now_utc + datetime.timedelta(minutes=c_cfg["scheduled_offset_minutes"])

            chal = Challenges(
                name=c_cfg["name"],
                description=f"Can you solve this exciting {c_cfg['category']} challenge and capture the flag?",
                value=c_cfg["value"],
                category=c_cfg["category"],
                state="visible",
                scheduled_at=sched_at,
            )
            db.session.add(chal)
            db.session.commit()
            created_chals.append(chal)

            flag = Flags(
                challenge_id=chal.id,
                content=c_cfg["flag"],
                type="static",
            )
            db.session.add(flag)
            db.session.commit()
            print(f"Created challenge: {chal.name} (ID: {chal.id})")
        else:
            created_chals.append(existing)

    # 2. Teams and Users
    team_data = [
        {"team_name": "CyberDragons", "members": [("dragon_lead", "dragon1@ctf.io"), ("dragon_pwn", "dragon2@ctf.io")]},
        {"team_name": "NullPointers", "members": [("segfault_sam", "sam@ctf.io"), ("null_byte", "byte@ctf.io")]},
        {"team_name": "BinaryBeasts", "members": [("hex_hunter", "hex@ctf.io"), ("bit_flipper", "bit@ctf.io")]},
        {"team_name": "ZeroDaySquad", "members": [("root_admin", "root@ctf.io"), ("zero_cool", "cool@ctf.io")]},
        {"team_name": "PhishHookers", "members": [("bait_master", "bait@ctf.io"), ("hook_line", "hook@ctf.io")]},
        {"team_name": "ShadowNet", "members": [("dark_knight", "dark@ctf.io"), ("stealth_fox", "fox@ctf.io")]},
    ]

    created_users = []
    created_teams = []

    for t_info in team_data:
        team = Teams.query.filter_by(name=t_info["team_name"]).first()
        if not team:
            team = Teams(name=t_info["team_name"], email=f"{t_info['team_name'].lower()}@ctf.io")
            db.session.add(team)
            db.session.commit()
            print(f"Created team: {team.name}")
        created_teams.append(team)

        for u_name, u_email in t_info["members"]:
            user = Users.query.filter_by(email=u_email).first()
            if not user:
                user = Users(
                    name=u_name,
                    email=u_email,
                    password="password123",
                    team_id=team.id,
                    type="user",
                    verified=True,
                )
                db.session.add(user)
                db.session.commit()
                print(f"Created user: {user.name} ({user.email}) on team {team.name}")
            else:
                user.team_id = team.id
                db.session.commit()
            created_users.append(user)

    # 3. Create realistic Solves across the last 3 hours
    unlocked_chals = [c for c in created_chals if not c.scheduled_at or c.scheduled_at <= now_utc]

    # Clean up stale teams from earlier tests to prevent 10-day timeline gaps
    active_team_names = [t_info["team_name"] for t_info in team_data]
    stale_teams = Teams.query.filter(~Teams.name.in_(active_team_names)).all()
    if stale_teams:
        stale_team_ids = [t.id for t in stale_teams]
        Solves.query.filter(Solves.account_id.in_(stale_team_ids)).delete(synchronize_session=False)
        Awards.query.filter(Awards.account_id.in_(stale_team_ids)).delete(synchronize_session=False)
        Users.query.filter(Users.team_id.in_(stale_team_ids)).delete(synchronize_session=False)
        Teams.query.filter(Teams.id.in_(stale_team_ids)).delete(synchronize_session=False)
        db.session.commit()

    solve_count = 0
    event_start_dt = now_utc - datetime.timedelta(hours=3)

    for idx, team in enumerate(created_teams):
        # Pick a random subset of unlocked challenges for each team
        # Team 0 solves most, Team 5 solves fewer to create a dynamic leaderboard ranking
        sample_size = max(2, len(unlocked_chals) - idx)
        team_chals = random.sample(unlocked_chals, min(len(unlocked_chals), sample_size))

        team_users = [u for u in created_users if u.team_id == team.id]
        if not team_users:
            continue

        min_offset = 12 + (idx * 5)
        max_offset = 165 - (idx * 6)
        timestamps = sorted([
            random.randint(min_offset, max(min_offset + 10, max_offset))
            for _ in range(len(team_chals))
        ])

        for c_idx, chal in enumerate(team_chals):
            existing_solve = Solves.query.filter_by(account_id=team.id, challenge_id=chal.id).first()
            if not existing_solve:
                user = random.choice(team_users)
                solve_time = event_start_dt + datetime.timedelta(minutes=timestamps[c_idx])

                solve = Solves(
                    user_id=user.id,
                    team_id=team.id,
                    challenge_id=chal.id,
                    ip="127.0.0.1",
                    provided="flag{sample}",
                    date=solve_time,
                )
                db.session.add(solve)
                solve_count += 1

    # 4. Optional small awards (Bonus Points)
    if created_teams:
        top_team = created_teams[0]
        top_user = [u for u in created_users if u.team_id == top_team.id][0]
        existing_award = Awards.query.filter_by(name="First Blood Bonus").first()
        if not existing_award:
            award = Awards(
                user_id=top_user.id,
                team_id=top_team.id,
                name="First Blood Bonus",
                description="Fastest solve on Crypto",
                value=50,
                date=now_utc - datetime.timedelta(minutes=100),
            )
            db.session.add(award)

    db.session.commit()
    clear_standings()
    clear_challenges()
    clear_config()

    print(f"Done! Created {len(created_chals)} challenges, {len(created_teams)} teams, {len(created_users)} users, and {solve_count} solves.")
