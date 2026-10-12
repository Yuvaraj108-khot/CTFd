import argparse
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--port", help="Port for debug server to listen on", default=4000)
parser.add_argument(
    "--profile", help="Enable flask_profiler profiling", action="store_true"
)
parser.add_argument(
    "--disable-gevent",
    help="Disable importing gevent and monkey patching",
    action="store_false",
)
parser.add_argument(
    "--no-waitress",
    help="Do not use Waitress WSGI server; use built-in Werkzeug server instead",
    action="store_true",
)
args = parser.parse_args()

use_waitress = not args.no_waitress and not args.profile
try:
    import waitress
except ImportError:
    use_waitress = False

if not use_waitress and args.disable_gevent:
    print(" * Importing gevent and monkey patching. Use --disable-gevent to disable.")
    from gevent import monkey

    monkey.patch_all()

# Import not at top of file to allow gevent to monkey patch uninterrupted
from CTFd import create_app

app = create_app()

if args.profile:
    from flask_debugtoolbar import DebugToolbarExtension
    import flask_profiler

    app.config["flask_profiler"] = {
        "enabled": app.config["DEBUG"],
        "storage": {"engine": "sqlite"},
        "basicAuth": {"enabled": False},
        "ignore": ["^/themes/.*", "^/events"],
    }
    flask_profiler.init_app(app)
    app.config["DEBUG_TB_PROFILER_ENABLED"] = True
    app.config["DEBUG_TB_INTERCEPT_REDIRECTS"] = False

    toolbar = DebugToolbarExtension()
    toolbar.init_app(app)
    print(" * Flask profiling running at http://127.0.0.1:4000/flask-profiler/")

if use_waitress:
    print(f" * Serving CTFd with Waitress (multi-threaded, 16 workers) at http://127.0.0.1:{args.port}")
    waitress.serve(app, host="127.0.0.1", port=args.port, threads=16, connection_limit=100)
else:
    app.run(debug=True, threaded=True, host="127.0.0.1", port=args.port)

