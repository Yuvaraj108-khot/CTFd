import sys
from CTFd import create_app
from CTFd.constants.themes import DEFAULT_THEME
from CTFd.utils import set_config, get_config
from CTFd.cache import clear_config, clear_standings, clear_challenges, clear_pages

app = create_app()

print("[+] Checking CTFd setup status...")
with app.app_context():
    is_already_setup = get_config("setup")
    if not is_already_setup:
        print("[+] Running initial setup...")
        with app.test_client() as client:
            client.get("/setup")
            with client.session_transaction() as sess:
                data = {
                    "ctf_name": "CTFd",
                    "ctf_description": "Capture The Flag Competition",
                    "name": "admin",
                    "email": "admin@ctfd.io",
                    "password": "adminpassword",
                    "user_mode": "teams",
                    "nonce": sess.get("nonce"),
                    "ctf_theme": DEFAULT_THEME,
                    "challenge_visibility": "public",
                    "account_visibility": "public",
                    "score_visibility": "public",
                    "registration_visibility": "public",
                }
            resp = client.post("/setup", data=data, follow_redirects=True)
            print(f"[+] Setup response status: {resp.status_code}")
        print("[+] Setup completed successfully! Admin login: admin / adminpassword")
    else:
        print("[*] CTFd is already marked as setup.")

    # Ensure challenge & score visibility are public so non-logged-in users can view them
    set_config("challenge_visibility", "public")
    set_config("account_visibility", "public")
    set_config("score_visibility", "public")
    set_config("registration_visibility", "public")
    clear_config()
    clear_challenges()
    clear_standings()
    clear_pages()

print("[+] Initial setup and configuration confirmed.")
