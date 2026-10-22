import os
import sys
import traceback

# 1. Ensure the application root is in the Python search path
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# 2. Set default environment settings for production
os.environ.setdefault("FLASK_ENV", "production")

# Ensure required runtime directories exist
for path in [
    os.path.join(PROJECT_DIR, ".data", "filesystem_cache"),
    os.path.join(PROJECT_DIR, "CTFd", "uploads"),
    os.path.join(PROJECT_DIR, "CTFd", "logs"),
]:
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass

# 3. Initialize CTFd application with diagnostic fallback
try:
    from CTFd import create_app

    # Phusion Passenger (cPanel) looks for 'application'
    application = create_app()
    app = application
except Exception as e:
    err_trace = traceback.format_exc()
    print(err_trace, file=sys.stderr)

    # Diagnostic response page to aid troubleshooting during cPanel setup
    def application(environ, start_response):
        start_response("500 Internal Server Error", [("Content-Type", "text/html; charset=utf-8")])
        error_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>CTFd Initialization Error</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace; background: #0f172a; color: #f8fafc; padding: 30px; }}
        .card {{ background: #1e293b; border-radius: 8px; padding: 24px; max-width: 900px; margin: auto; box-shadow: 0 4px 20px rgba(0,0,0,0.5); }}
        h1 {{ color: #ef4444; margin-top: 0; font-size: 22px; }}
        pre {{ background: #020617; color: #fca5a5; padding: 16px; border-radius: 6px; overflow-x: auto; font-size: 13px; line-height: 1.5; }}
        .tips {{ margin-top: 20px; font-size: 14px; color: #94a3b8; line-height: 1.6; }}
        .tips ul {{ padding-left: 20px; }}
        .tips li {{ margin-bottom: 6px; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>CTFd Startup Error (cPanel / Phusion Passenger)</h1>
        <p>An exception occurred while creating the CTFd application:</p>
        <pre>{err_trace}</pre>
        <div class="tips">
            <strong>Common Causes &amp; Solutions:</strong>
            <ul>
                <li><strong>Database Connection:</strong> Check <code>CTFd/config.ini</code> or <code>DATABASE_URL</code> to ensure your MySQL user, password, and database name are correct.</li>
                <li><strong>Missing Packages:</strong> Ensure all packages in <code>requirements.txt</code> have been installed in your cPanel Python virtual environment.</li>
                <li><strong>Permissions:</strong> Verify that <code>.data/</code>, <code>CTFd/uploads/</code>, and <code>CTFd/logs/</code> are writable (chmod 755 or 775).</li>
            </ul>
        </div>
    </div>
</body>
</html>"""
        return [error_html.encode("utf-8")]

    app = application

if __name__ == "__main__":
    application.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
