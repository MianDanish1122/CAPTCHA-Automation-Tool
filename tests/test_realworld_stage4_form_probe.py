"""Stage 4 (real-world QA): non-transmitting form probe. The server logs EVERY request; after the probe starts it
must see none."""
import http.server
import threading

import pytest

from app.config import settings
from app.services.browser_scanner import get_shared_browser, inspect_website
from app.services.form_probe import choose_value, probe_and_fill
from app.services.network_guard import NetworkGuard, new_guarded_context

PAGE = b"""<html><head><title>Contact</title></head><body>
<form id=f method=post action="/psubmit">
  <label for=n>Your name</label><input id=n name=your-name required maxlength=12>
  <label>Email <input type=email name=email required></label>
  <input type=tel name=phone placeholder="Phone">
  <input name=subject>
  <textarea name=message required></textarea>
  <select name=topic><option>a</option><option>b</option></select>
  <label><input type=checkbox name=consent> I agree to the terms</label>
  <input type=hidden name=csrf value=SECRET-HIDDEN>
  <input name=website_hp style="position:absolute;left:-9999px" tabindex=-1>
  <input name=honeypot_field>
  <div class="g-recaptcha" data-sitekey="K"></div>
  <textarea name="g-recaptcha-response" style="display:block;width:50px;height:20px"></textarea>
  <button type=submit>Send message</button>
</form>
<form id=g method=get action="/gsubmit"><input name=q></form>
<script>
  // hostile-ish page behaviour: autosave on every keystroke, Enter handler, ping on input
  document.addEventListener('input', function(){ try { fetch('/autosave', {method:'POST', body:'x'}); } catch(e){}
      try { var x = new XMLHttpRequest(); x.open('POST','/xhr'); x.send('y'); } catch(e){}
      try { navigator.sendBeacon('/beacon','z'); } catch(e){}
      try { new Image().src='/pixel.gif?k=1'; } catch(e){} });
</script></body></html>"""


class _H(http.server.BaseHTTPRequestHandler):
    log: list = []

    def log_message(self, *a):
        pass

    def _rec(self):
        _H.log.append((self.command, self.path))

    def do_GET(self):
        self._rec()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(PAGE)))
        self.end_headers()
        self.wfile.write(PAGE)

    def do_POST(self):
        self._rec()
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n) if n else b""
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()


@pytest.fixture
def site():
    _H.log = []
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


@pytest.mark.anyio
async def test_probe_records_structure_fills_synthetic_data_and_transmits_nothing(site):
    guard = NetworkGuard(allow_loopback=True, read_only=True, label="t-probe")
    browser = await get_shared_browser()
    ctx = await new_guarded_context(browser, guard)
    try:
        page = await ctx.new_page()
        await page.goto(site + "/", wait_until="domcontentloaded")
        await page.wait_for_timeout(300)
        baseline = len(_H.log)

        probe = await probe_and_fill(page, ctx, guard)

        # --- structure
        assert probe["form_count"] == 2 and probe["aborted_reason"] is None
        f0 = probe["forms"][0]
        assert f0["method"] == "post" and f0["same_origin_action"] and f0["captcha_inside_form"]
        assert "Send message" in f0["submit_buttons"]
        by_name = {f["name"]: f for f in f0["fields"]}
        assert by_name["your-name"]["label"] == "Your name" and by_name["your-name"]["required"] and by_name["your-name"]["maxlength"] == 12
        assert by_name["email"]["type"] == "email" and by_name["email"]["required"] and "Email" in by_name["email"]["label"]
        assert by_name["message"]["type"] == "textarea" and by_name["topic"]["options"] == 2

        # --- policy flags are all true/false as promised
        pol = probe["policy"]
        assert pol["network_locked"] and pol["browser_offline"] and pol["submit_shield"]
        assert not pol["submit_clicked"] and not pol["enter_pressed"] and not pol["captcha_touched"] and not pol["data_transmitted"]

        # --- what was filled (and what was deliberately not)
        vals = await page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('input,textarea,select')]
                                       .map(e => [e.name, e.type === 'checkbox' ? e.checked : e.value]))""")
        assert vals["your-name"] == "QA Tester"[:12] and vals["email"] == "qa.tester@example.invalid"
        assert vals["phone"].startswith("555") and "never submitted" in vals["message"] and vals["q"] == "QA test"
        assert vals["consent"] is False                                  # consent box never ticked
        assert vals["topic"] == "a"                                      # select untouched
        assert vals["csrf"] == "SECRET-HIDDEN"                           # hidden field untouched
        assert vals["website_hp"] == "" and vals["honeypot_field"] == ""  # honeypots untouched
        assert vals["g-recaptcha-response"] == ""                        # CAPTCHA response field untouched
        skipped = {s["name"]: s["reason"] for s in probe["skipped_fields"]}
        assert "CAPTCHA" in skipped["g-recaptcha-response"] and "honeypot" in skipped["honeypot_field"]
        assert probe["filled_fields"] >= 6

        # --- the page tried to phone home on every keystroke: all of it was refused, none reached the server
        assert probe["requests_blocked_while_locked"] >= 0
        await page.wait_for_timeout(500)
        assert _H.log[baseline:] == [], f"requests reached the server during the probe: {_H.log[baseline:]}"

        # --- and every way of submitting afterwards is also dead
        for js in ("document.getElementById('f').submit()", "document.getElementById('f').requestSubmit()",
                   "document.getElementById('g').submit()"):
            try:
                await page.evaluate(js)
            except Exception:
                pass
        for sel in ("input[name=email]", "input[name=q]"):
            try:
                await page.press(sel, "Enter", timeout=1500)
            except Exception:
                pass
        await page.wait_for_timeout(500)
        assert _H.log[baseline:] == []
    finally:
        await ctx.close()
        await guard.close()


@pytest.mark.anyio
async def test_probe_without_forms_or_with_fill_disabled_does_not_lock_or_fill(site):
    guard = NetworkGuard(allow_loopback=True, read_only=True, label="t-probe2")
    browser = await get_shared_browser()
    ctx = await new_guarded_context(browser, guard)
    try:
        page = await ctx.new_page()
        await page.goto(site + "/", wait_until="domcontentloaded")
        probe = await probe_and_fill(page, ctx, guard, fill=False)
        assert probe["form_count"] == 2 and probe["filled_fields"] == 0 and not probe["policy"]["network_locked"]
        assert guard.locked is False
    finally:
        await ctx.close()
        await guard.close()


@pytest.mark.anyio
async def test_inspect_website_probe_flag_end_to_end_with_screenshots(site, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "EVIDENCE_DIR", tmp_path / "evidence")
    monkeypatch.setattr(settings, "DETECTION_SETTLE_MS", 1200)
    monkeypatch.setattr(settings, "DETECTION_EVIDENCE_WAIT_MS", 500)
    r = await inspect_website(site + "/", allow_loopback=True, probe_forms=True, respect_robots=True,
                              evidence_dir=settings.EVIDENCE_DIR / "batches" / "t", evidence_name="probe")
    assert r["success"] and r["form_probe"]["filled_fields"] >= 6
    assert (tmp_path / r["screenshot_path"]).exists()
    assert (tmp_path / r["form_probe"]["filled_screenshot"]).exists()
    posts_or_extra = [e for e in _H.log if e[0] != "GET" or e[1] not in ("/", "/robots.txt")]
    assert posts_or_extra == [], posts_or_extra


@pytest.mark.parametrize("field,expect", [
    ({"type": "email", "name": "e", "id": "", "label": "", "placeholder": "", "autocomplete": "", "visible": True}, "email"),
    ({"type": "text", "name": "your-phone", "id": "", "label": "", "placeholder": "", "autocomplete": "", "visible": True}, "phone"),
    ({"type": "text", "name": "company", "id": "", "label": "", "placeholder": "", "autocomplete": "", "visible": True}, "company"),
    ({"type": "textarea", "name": "x", "id": "", "label": "", "placeholder": "", "autocomplete": "", "visible": True}, "message"),
    ({"type": "text", "name": "fname", "id": "", "label": "", "placeholder": "", "autocomplete": "", "visible": True}, "first_name"),
    ({"type": "text", "name": "zip", "id": "", "label": "", "placeholder": "", "autocomplete": "", "visible": True}, "zip"),
])
def test_choose_value_kinds(field, expect):
    assert choose_value(field)[0] == expect


@pytest.mark.parametrize("ftype", ["hidden", "checkbox", "radio", "file", "password", "submit", "select"])
def test_choose_value_never_fills_sensitive_types(ftype):
    f = {"type": ftype, "name": "n", "id": "", "label": "", "placeholder": "", "autocomplete": "", "visible": True}
    assert choose_value(f)[0] is None


def test_choose_value_respects_maxlength_and_invisible():
    f = {"type": "email", "name": "e", "id": "", "label": "", "placeholder": "", "autocomplete": "", "visible": True, "maxlength": 8}
    assert choose_value(f)[1] == "qa.teste"
    f["visible"] = False
    assert choose_value(f)[0] is None
