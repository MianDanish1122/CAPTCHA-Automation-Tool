"""
Safe, self-contained DEMO environment (synthetic / owned data only).

    python -m scripts.demo_env setup [--reset]   # isolated DB + 2 demo accounts + imported OCR benchmark results
    python -m scripts.demo_env site              # serve the owned demo website on http://127.0.0.1:8090/
    python -m scripts.demo_env env               # print the exact environment for starting the backend (PowerShell)

Everything lives in ./demo_runtime (git-ignored): the demo database, and a credentials file that holds
RANDOM passwords generated on this machine. Nothing is hard-coded; your real database (data/) and real
accounts are never touched. The demo site is served from this machine only: no third-party site is scanned.
"""
import argparse
import http.server
import os
import secrets
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "demo_runtime"
DB_FILE = RUNTIME / "demo.db"
CREDS = RUNTIME / "demo_credentials.txt"
SITE_PORT = 8090
DEMO_USERS = (("demo_operator", "operator"), ("demo_admin", "admin"))


def database_url() -> str:
    return f"sqlite:///{DB_FILE.as_posix()}"


# --------------------------------------------------------------------------- demo website (owned)
_HOME = """<!doctype html><html><head><title>Acme Demo Store</title></head><body style="font-family:sans-serif">
<h1>Acme Demo Store</h1><p>A fictional site served from this machine for the CAPTCHA Inspector demo.</p>
<nav><a href="/contact">Contact us</a> | <a href="/support">Support</a> | <a href="/about">About</a></nav></body></html>"""

# A production-STYLE reCAPTCHA widget (made-up site key): detected and routed to a human, never solved.
_CONTACT = """<!doctype html><html><head><title>Contact Acme</title>
<script src="https://www.google.com/recaptcha/api.js" async defer></script></head><body style="font-family:sans-serif">
<h1>Contact us</h1><form method="post"><label>Email <input name="email"></label><br>
<label>Message <textarea name="message"></textarea></label><br>
<div class="g-recaptcha" data-sitekey="6LdDEMOEXAMPLEKEYxxxxxxxxxxxxxxxxxxxxxxx"></div>
<button>Send</button></form></body></html>"""

_SUPPORT = """<!doctype html><html><head><title>Acme Support</title></head><body style="font-family:sans-serif">
<h1>Support</h1><form method="post"><label>Your question <textarea name="message"></textarea></label><br>
<button>Submit</button></form></body></html>"""

_ABOUT = "<!doctype html><html><head><title>About Acme</title></head><body><h1>About</h1><p>Fictional company.</p></body></html>"

PAGES = {"/": _HOME, "/contact": _CONTACT, "/support": _SUPPORT, "/about": _ABOUT}


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        body = PAGES.get(self.path.split("?")[0])
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def cmd_site(_):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", SITE_PORT), _Handler)
    print(f"Demo website: http://127.0.0.1:{SITE_PORT}/   (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


# --------------------------------------------------------------------------- setup
def cmd_setup(args):
    RUNTIME.mkdir(exist_ok=True)
    if DB_FILE.exists():
        if not args.reset:
            sys.exit(f"{DB_FILE} already exists. Re-run with --reset to start from a clean demo database.")
        DB_FILE.unlink()
    os.environ["DATABASE_URL"] = database_url()
    os.environ["APP_ENV"] = "development"
    sys.path.insert(0, str(ROOT))

    from alembic import command
    from alembic.config import Config
    from argparse import Namespace
    from app.database import SessionLocal
    from app.models import User
    from app.services.auth_service import hash_password
    from scripts.ocr_benchmark import cmd_import_results

    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    lines = ["CAPTCHA Inspector DEMO accounts (random, generated locally). Do NOT show this file on screen.", ""]
    db = SessionLocal()
    try:
        for name, role in DEMO_USERS:
            password = secrets.token_urlsafe(12) + "Aa1!"
            db.add(User(username=name, email=f"{name}@demo.invalid", role=role, hashed_password=hash_password(password)))
            lines.append(f"{role:9s} username={name}  password={password}")
        db.commit()
    finally:
        db.close()
    CREDS.write_text("\n".join(lines) + "\n", encoding="utf-8")
    cmd_import_results(Namespace(file="evaluation_test2.json"))  # real, measured held-out OCR results
    print(f"Demo database ready: {DB_FILE}")
    print(f"Demo credentials file (open it privately; never on screen): {CREDS}")


def cmd_env(_):
    print("# paste into the PowerShell window that starts the BACKEND")
    print(f"$env:DATABASE_URL = '{database_url()}'")
    print("$env:APP_ENV = 'development'")
    print("$env:ALLOW_DEV_LOOPBACK = 'true'        # lets the inspector scan the local demo site only")
    print("$env:ENABLE_LIVE_SCAN = 'false'         # no arbitrary external scanning")
    print("$env:ALLOWED_DOMAINS = 'localhost'")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup")
    s.add_argument("--reset", action="store_true")
    s.set_defaults(fn=cmd_setup)
    sub.add_parser("site").set_defaults(fn=cmd_site)
    sub.add_parser("env").set_defaults(fn=cmd_env)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
