import os
import shutil
import sqlite3

def seed():
    target_db = "/var/uploads/ctfd.db"
    source_db = "/opt/CTFd/CTFd/ctfd.db"

    # Also check local path fallback
    if not os.path.exists(source_db):
        source_db = os.path.join(os.path.dirname(__file__), "CTFd", "ctfd.db")

    if not os.path.exists(source_db):
        print(f"[!] Source database {source_db} not found, skipping seed.")
        return

    # Check if target db is missing or empty (setup not completed)
    needs_overwrite = True
    if os.path.exists(target_db):
        try:
            conn = sqlite3.connect(target_db)
            cur = conn.cursor()
            cur.execute("SELECT value FROM config WHERE key='setup'")
            row = cur.fetchone()
            cur.execute("SELECT count(*) FROM challenges")
            chal_count = cur.fetchone()[0]
            conn.close()

            if row and row[0] in ("1", 1, True, "true") and chal_count > 0:
                print(f"[*] Target database already has setup=1 and {chal_count} challenges. Preserving existing DB.")
                needs_overwrite = False
            else:
                print(f"[!] Target database exists but is EMPTY (challenges: {chal_count}). Overwriting with populated source DB...")
        except Exception as e:
            print(f"[!] Target database check failed ({e}). Overwriting with clean source DB...")

    if needs_overwrite:
        os.makedirs(os.path.dirname(target_db), exist_ok=True)
        shutil.copy2(source_db, target_db)
        try:
            os.chmod(target_db, 0o666)
        except Exception:
            pass
        print(f"[+] Successfully copied populated database with 27 challenges into {target_db}")

    # Seed challenge uploads
    source_uploads = "/opt/CTFd/CTFd/uploads"
    target_uploads = "/var/uploads"
    if os.path.exists(source_uploads) and os.path.exists(target_uploads):
        for root, dirs, files in os.walk(source_uploads):
            rel_path = os.path.relpath(root, source_uploads)
            dest_dir = os.path.join(target_uploads, rel_path)
            os.makedirs(dest_dir, exist_ok=True)
            for f in files:
                src_file = os.path.join(root, f)
                dst_file = os.path.join(dest_dir, f)
                if not os.path.exists(dst_file):
                    shutil.copy2(src_file, dst_file)
                    try:
                        os.chmod(dst_file, 0o666)
                    except Exception:
                        pass
        print("[+] Challenge upload assets synced to /var/uploads.")

if __name__ == "__main__":
    seed()
