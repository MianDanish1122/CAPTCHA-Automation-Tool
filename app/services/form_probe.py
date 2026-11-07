"""
Non-transmitting form probe.

Records the real structure of a contact form (fields, labels, types, required flags, constraints, submit-button text,
where the CAPTCHA sits) and demonstrates that it can be filled with SYNTHETIC data -- without ever transmitting it.

Safety order (nothing is filled until every layer is in place; if a layer fails the probe aborts without filling):
  1. NetworkGuard.lock()          every request of any method to any host is aborted
  2. context.set_offline(True)    the browser itself has no network
  3. in-page submit shield        capture-phase submit/Enter handlers, form.submit()/requestSubmit() no-ops,
                                  fetch/XHR/sendBeacon/WebSocket neutralised
Then only visible, text-like fields are filled with fixed placeholder data. The probe NEVER clicks anything, NEVER
presses Enter, NEVER ticks checkboxes (consent boxes), NEVER selects options, NEVER fills hidden/honeypot fields and
NEVER interacts with a CAPTCHA widget or its response field. No token is read.
"""
import re
from typing import Any

SYNTHETIC = {
    "email": "qa.tester@example.invalid",
    "name": "QA Tester",
    "first_name": "QA",
    "last_name": "Tester",
    "phone": "555-0100",
    "company": "Example QA Co",
    "subject": "Automated QA inspection (not sent)",
    "message": "Automated QA inspection. This text was never submitted or transmitted.",
    "zip": "00000",
    "url": "https://example.invalid",
    "text": "QA test",
    "number": "1",
}

_INVENTORY_JS = r"""
() => {
  const labelFor = (el) => {
    if (el.id) { const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]'); if (l) return l.innerText.trim(); }
    const w = el.closest('label'); if (w) return w.innerText.trim();
    return (el.getAttribute('aria-label') || '').trim();
  };
  const vis = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && cs.visibility !== 'hidden' && cs.display !== 'none' && r.right > 0 && r.bottom > 0
           && r.left < innerWidth + 5000 && r.left > -1000; };
  const forms = [];
  document.querySelectorAll('form').forEach((f, idx) => {
    f.setAttribute('data-qa-form', String(idx));
    const fields = [];
    f.querySelectorAll('input, textarea, select').forEach((el, j) => {
      el.setAttribute('data-qa-field', idx + '-' + j);
      fields.push({
        key: idx + '-' + j, tag: el.tagName.toLowerCase(), type: (el.getAttribute('type') || (el.tagName === 'TEXTAREA' ? 'textarea' : el.tagName === 'SELECT' ? 'select' : 'text')).toLowerCase(),
        name: el.getAttribute('name') || '', id: el.id || '', label: labelFor(el).slice(0, 120),
        placeholder: (el.getAttribute('placeholder') || '').slice(0, 80), autocomplete: el.getAttribute('autocomplete') || '',
        required: el.required || el.getAttribute('aria-required') === 'true',
        maxlength: el.getAttribute('maxlength') ? Number(el.getAttribute('maxlength')) : null,
        pattern: el.getAttribute('pattern') || null, visible: vis(el),
        options: el.tagName === 'SELECT' ? el.options.length : null });
    });
    const buttons = [];
    f.querySelectorAll('button, input[type=submit], input[type=button], [role=button]').forEach(b => {
      buttons.push(((b.innerText || b.value || b.getAttribute('aria-label') || '') + '').trim().slice(0, 60));
    });
    const hasCaptchaBox = !!f.querySelector('.g-recaptcha, .h-captcha, .cf-turnstile, [data-sitekey]');
    const hasCaptchaFrame = !!f.querySelector('iframe[src*="recaptcha"], iframe[src*="hcaptcha"], iframe[src*="challenges.cloudflare.com"]');
    let action = f.getAttribute('action') || '';
    let host = ''; try { host = new URL(action || location.href, location.href).hostname; } catch (e) {}
    forms.push({ index: idx, method: (f.getAttribute('method') || 'get').toLowerCase(), action_host: host,
                 same_origin_action: host === location.hostname, fields, submit_buttons: buttons.filter(Boolean),
                 captcha_inside_form: hasCaptchaBox || hasCaptchaFrame });
  });
  return { url_host: location.hostname, forms,
           captcha_outside_forms: !![...document.querySelectorAll('.g-recaptcha, .h-captcha, .cf-turnstile')].find(e => !e.closest('form')) };
}
"""

_SHIELD_JS = r"""
() => {
  if (window.__qaShield) return true;
  const stop = (e) => { e.preventDefault(); e.stopImmediatePropagation(); return false; };
  window.addEventListener('submit', stop, true);
  window.addEventListener('keydown', (e) => { if (e.key === 'Enter') { stop(e); } }, true);
  window.addEventListener('keypress', (e) => { if (e.key === 'Enter') { stop(e); } }, true);
  window.addEventListener('beforeunload', (e) => { e.preventDefault(); }, true);
  HTMLFormElement.prototype.submit = function () {};
  HTMLFormElement.prototype.requestSubmit = function () {};
  window.fetch = () => Promise.reject(new TypeError('network disabled by inspection shield'));
  XMLHttpRequest.prototype.send = function () { throw new Error('network disabled by inspection shield'); };
  navigator.sendBeacon = () => false;
  window.WebSocket = function () { throw new Error('network disabled by inspection shield'); };
  window.__qaShield = true;
  return true;
}
"""

_TOKEN_FIELD = re.compile(r"(g-recaptcha-response|h-captcha-response|cf-turnstile-response|captcha)", re.I)
_HONEYPOT = re.compile(r"(honeypot|honey_pot|hp_|leave.?blank|do.?not.?fill|trap)", re.I)


def choose_value(field: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return (kind, value) for a visible text-like field, or (None, reason) when it must not be filled."""
    t = field["type"]
    name = " ".join([field["name"], field["id"], field["label"], field["placeholder"], field["autocomplete"]]).lower()
    if t in ("hidden", "checkbox", "radio", "file", "password", "submit", "button", "image", "reset", "select"):
        return None, f"type '{t}' is never filled"
    if _TOKEN_FIELD.search(field["name"] + " " + field["id"]):
        return None, "CAPTCHA response field is never touched"
    if _HONEYPOT.search(name):
        return None, "looks like a honeypot field"
    if not field["visible"]:
        return None, "not visible"
    if t == "email" or "email" in name or "e-mail" in name:
        kind = "email"
    elif t == "tel" or re.search(r"phone|tel\b|mobile", name):
        kind = "phone"
    elif t == "url" or re.search(r"website|url", name):
        kind = "url"
    elif t == "number":
        kind = "number"
    elif t == "textarea" or re.search(r"message|comment|enquiry|inquiry|question|details|how can we help", name):
        kind = "message"
    elif re.search(r"first.?name|fname|given", name):
        kind = "first_name"
    elif re.search(r"last.?name|lname|surname|family", name):
        kind = "last_name"
    elif re.search(r"company|organi[sz]ation|business", name):
        kind = "company"
    elif re.search(r"subject|topic|regarding", name):
        kind = "subject"
    elif re.search(r"zip|postal|post.?code", name):
        kind = "zip"
    elif re.search(r"name|your.?name|full", name):
        kind = "name"
    else:
        kind = "text"
    value = SYNTHETIC[kind]
    if field.get("maxlength"):
        value = value[: field["maxlength"]]
    return kind, value


async def probe_and_fill(page, context, guard, fill: bool = True) -> dict[str, Any]:
    """Inventory the forms on the current page and (optionally) fill them with synthetic data under lockdown."""
    result: dict[str, Any] = {"form_count": 0, "forms": [], "filled_fields": 0, "skipped_fields": [], "filled_kinds": {},
                              "policy": {"network_locked": False, "browser_offline": False, "submit_shield": False,
                                         "submit_clicked": False, "enter_pressed": False, "captcha_touched": False,
                                         "data_transmitted": False},
                              "requests_blocked_while_locked": 0, "aborted_reason": None}
    try:
        inventory = await page.evaluate(_INVENTORY_JS)
    except Exception as exc:
        result["aborted_reason"] = f"inventory failed: {type(exc).__name__}"
        return result
    result["forms"] = inventory["forms"]
    result["form_count"] = len(inventory["forms"])
    result["captcha_outside_forms"] = inventory["captcha_outside_forms"]
    if not fill or not inventory["forms"]:
        return result

    # ---- all safety layers first; abort (without filling) if any layer cannot be established
    before = len(guard.summary()["blocked_requests"])
    try:
        guard.lock()
        result["policy"]["network_locked"] = True
        await context.set_offline(True)
        result["policy"]["browser_offline"] = True
        await page.evaluate(_SHIELD_JS)
        result["policy"]["submit_shield"] = True
    except Exception as exc:
        # stay locked (fail closed): the page is not used any further after a failed probe
        result["aborted_reason"] = f"safety layer failed ({type(exc).__name__}); nothing was filled"
        return result

    # ---- fill visible, text-like fields only (no clicks, no Enter, no checkboxes, no CAPTCHA)
    for form in inventory["forms"]:
        for field in form["fields"]:
            kind, value = choose_value(field)
            if kind is None:
                result["skipped_fields"].append({"form": form["index"], "name": field["name"] or field["id"],
                                                 "type": field["type"], "reason": value})
                continue
            try:
                await page.fill(f'[data-qa-field="{field["key"]}"]', value, timeout=2000)
                result["filled_fields"] += 1
                result["filled_kinds"][kind] = result["filled_kinds"].get(kind, 0) + 1
            except Exception as exc:
                result["skipped_fields"].append({"form": form["index"], "name": field["name"] or field["id"],
                                                 "type": field["type"], "reason": f"fill failed: {type(exc).__name__}"})
    await page.wait_for_timeout(300)  # let any input-triggered requests attempt (and be refused)
    result["requests_blocked_while_locked"] = len(guard.summary()["blocked_requests"]) - before
    return result
