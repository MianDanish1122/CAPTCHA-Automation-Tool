"""
Shared, rendered-page CAPTCHA detection engine (used by the single-site crawler AND the batch workflow).

The Phase 2-7 detector read the static HTML at `domcontentloaded`. Real contact pages inject their widgets with
JavaScript, load them in provider iframes and often defer them, so this engine:

  1. lets the page settle (bounded wait for network quiet), then polls (bounded) while no provider evidence exists;
  2. collects evidence from the LIVE DOM: widget containers/attributes, provider <script> URLs, provider <iframe>
     elements and attached frame URLs, response-token fields, badges, and inline widget API calls;
  3. classifies provider and SUBTYPE where observable and records whether the widget actually LOADED;
  4. reports provider resources that the egress guard blocked, so "not detected" is never confused with
     "could not be observed".

The pure function `classify_observation` has no browser dependency and is unit-tested with recorded shapes.
Nothing here clicks, types into or submits anything, and no token is ever read.
"""
import asyncio
import re
import time
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from app.services.browser_scanner import detect_captcha_in_html

# ------------------------------------------------------------------ in-page evidence collector (read-only)
_COLLECT_JS = r"""
() => {
  const attr = (el, n) => el.getAttribute(n);
  const vis = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
      return {w: Math.round(r.width), h: Math.round(r.height),
              visible: r.width > 1 && r.height > 1 && cs.visibility !== 'hidden' && cs.display !== 'none'}; };
  const out = {containers: [], scripts: [], iframes: [], token_fields: [], badges: 0, inline_hits: [], title: document.title};
  const sel = '.g-recaptcha, .h-captcha, .cf-turnstile, [data-sitekey]';
  document.querySelectorAll(sel).forEach(el => out.containers.push({
      cls: (el.className && el.className.toString ? el.className.toString() : '').slice(0, 120),
      has_sitekey: !!attr(el, 'data-sitekey'), size: attr(el, 'data-size'), theme: attr(el, 'data-theme'),
      appearance: attr(el, 'data-appearance'), execution: attr(el, 'data-execution'),
      callback: !!attr(el, 'data-callback'), tag: el.tagName.toLowerCase(), ...vis(el)}));
  document.querySelectorAll('script[src]').forEach(s => out.scripts.push(s.src));
  document.querySelectorAll('iframe').forEach(f => out.iframes.push(
      {src: f.src || attr(f, 'src') || '', title: attr(f, 'title') || '', ...vis(f)}));
  document.querySelectorAll('textarea[name="g-recaptcha-response"], textarea[name="h-captcha-response"], ' +
      'input[name="cf-turnstile-response"], input[name="g-recaptcha-response"], input[name="h-captcha-response"]')
      .forEach(t => out.token_fields.push({name: attr(t, 'name')}));   // name only: the VALUE is never read
  out.badges = document.querySelectorAll('.grecaptcha-badge').length;
  const needles = ['grecaptcha.execute', 'grecaptcha.render', 'grecaptcha.enterprise', 'hcaptcha.execute',
                   'hcaptcha.render', 'turnstile.render', 'turnstile.execute'];
  document.querySelectorAll('script:not([src])').forEach(s => {
      const t = s.textContent || ''; needles.forEach(n => { if (t.indexOf(n) !== -1 && out.inline_hits.indexOf(n) === -1) out.inline_hits.push(n); }); });
  return out;
}
"""

_RECAPTCHA_HOSTS = ("google.com", "recaptcha.net", "gstatic.com")


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _is_recaptcha_url(url: str) -> bool:
    h = _host(url)
    return (h.endswith("recaptcha.net") or h.endswith("google.com") or h.endswith("gstatic.com")) and "/recaptcha" in url


def _is_hcaptcha_url(url: str) -> bool:
    h = _host(url)
    return h == "hcaptcha.com" or h.endswith(".hcaptcha.com")


def _is_turnstile_url(url: str) -> bool:
    return _host(url) == "challenges.cloudflare.com" and ("/turnstile" in url or "challenge-platform" in url)


def _qs(url: str) -> dict[str, str]:
    q = parse_qs(urlparse(url).query)
    frag = parse_qs(urlparse(url).fragment)
    merged = {k: v[0] for k, v in {**q, **frag}.items() if v}
    return merged


# ------------------------------------------------------------------ pure classification
def classify_observation(obs: dict[str, Any], frame_urls: Optional[list[str]] = None,
                         blocked_provider_resources: Optional[list[str]] = None) -> dict[str, Any]:
    """
    Turn collected evidence into provider / subtype / widget state. Returns:
      detections: [{provider, subtype, widget_state, widget_loaded, evidence:[...]}], plus convenience fields.
    widget_state: "iframe_loaded" | "badge_only" | "container_only" | "script_only" | "api_call_only"
    """
    frame_urls = frame_urls or []
    iframes = obs.get("iframes", [])
    scripts = obs.get("scripts", [])
    containers = obs.get("containers", [])
    inline = obs.get("inline_hits", [])
    token_fields = [t["name"] for t in obs.get("token_fields", [])]
    found: dict[str, dict[str, Any]] = {}

    def entry(provider: str) -> dict[str, Any]:
        return found.setdefault(provider, {"provider": provider, "subtype": None, "widget_state": None,
                                           "widget_loaded": False, "evidence": [], "_flags": set()})

    # ---- reCAPTCHA
    rc_scripts = [s for s in scripts if _is_recaptcha_url(s)]
    rc_frames = [f for f in iframes if _is_recaptcha_url(f["src"])] + \
        [{"src": u, "visible": True, "w": 0, "h": 0} for u in frame_urls if _is_recaptcha_url(u)]
    rc_containers = [c for c in containers if "g-recaptcha" in c["cls"]]
    rc_inline = [i for i in inline if i.startswith("grecaptcha")]
    rc_fields = [n for n in token_fields if n == "g-recaptcha-response"]
    if rc_scripts or rc_frames or rc_containers or rc_inline or rc_fields or obs.get("badges"):
        e = entry("google_recaptcha")
        if rc_scripts:
            e["evidence"].append(f"script: {_host(rc_scripts[0])}{urlparse(rc_scripts[0]).path}")
        for f in rc_frames[:3]:
            e["evidence"].append(f"iframe: {_host(f['src'])}{urlparse(f['src']).path}")
        if rc_containers:
            e["evidence"].append("container: .g-recaptcha")
        if rc_inline:
            e["evidence"].append("inline api: " + ", ".join(rc_inline))
        if rc_fields:
            e["evidence"].append("token field: g-recaptcha-response (name only)")
        if obs.get("badges"):
            e["evidence"].append("badge: .grecaptcha-badge")
        anchors = [f for f in rc_frames if "/recaptcha/api2/anchor" in f["src"] or "/recaptcha/enterprise/anchor" in f["src"]]
        enterprise = any("/enterprise" in u for u in rc_scripts) or any("/enterprise/" in f["src"] for f in rc_frames) \
            or "grecaptcha.enterprise" in inline
        size = None
        if anchors:
            size = _qs(anchors[0]["src"]).get("size")
        declared_size = next((c["size"] for c in rc_containers if c.get("size")), None)
        render_param = None
        for s in rc_scripts:
            r = _qs(s).get("render")
            if r and r not in ("explicit", "onload"):
                render_param = r
        if size == "invisible" or declared_size == "invisible" or (obs.get("badges") and not anchors) \
                or any(c.get("execution") for c in rc_containers if False):
            sub = "invisible"
        elif render_param and not rc_containers and not anchors:
            sub = "v3_score_based"
        elif size == "normal" or size == "compact" or declared_size in ("normal", "compact") or anchors or rc_containers:
            sub = "v2_checkbox"
        elif rc_inline and "grecaptcha.execute" in rc_inline:
            sub = "invisible_or_v3"
        else:
            sub = "unknown"
        if enterprise:
            sub = f"enterprise_{sub}" if sub != "unknown" else "enterprise"
        e["subtype"] = sub
        if anchors:
            e["widget_state"] = "iframe_loaded"
        elif obs.get("badges"):
            e["widget_state"] = "badge_only"
        elif rc_containers:
            e["widget_state"] = "container_only"
        elif rc_scripts:
            e["widget_state"] = "script_only"
        else:
            e["widget_state"] = "api_call_only"
        e["widget_loaded"] = e["widget_state"] in ("iframe_loaded", "badge_only")

    # ---- hCaptcha
    hc_scripts = [s for s in scripts if _is_hcaptcha_url(s)]
    hc_frames = [f for f in iframes if _is_hcaptcha_url(f["src"])] + \
        [{"src": u, "visible": True, "w": 0, "h": 0} for u in frame_urls if _is_hcaptcha_url(u)]
    hc_containers = [c for c in containers if "h-captcha" in c["cls"]]
    hc_inline = [i for i in inline if i.startswith("hcaptcha")]
    hc_fields = [n for n in token_fields if n == "h-captcha-response"]
    if hc_scripts or hc_frames or hc_containers or hc_inline or hc_fields:
        e = entry("hcaptcha")
        if hc_scripts:
            e["evidence"].append(f"script: {_host(hc_scripts[0])}{urlparse(hc_scripts[0]).path}")
        for f in hc_frames[:3]:
            e["evidence"].append(f"iframe: {_host(f['src'])}")
        if hc_containers:
            e["evidence"].append("container: .h-captcha")
        if hc_inline:
            e["evidence"].append("inline api: " + ", ".join(hc_inline))
        if hc_fields:
            e["evidence"].append("token field: h-captcha-response (name only)")
        size = next((c["size"] for c in hc_containers if c.get("size")), None) or \
            next((_qs(f["src"]).get("size") for f in hc_frames if _qs(f["src"]).get("size")), None)
        e["subtype"] = "invisible" if size == "invisible" or "hcaptcha.execute" in hc_inline else "checkbox"
        e["widget_state"] = "iframe_loaded" if hc_frames else ("container_only" if hc_containers else
                                                              ("script_only" if hc_scripts else "api_call_only"))
        e["widget_loaded"] = e["widget_state"] == "iframe_loaded"

    # ---- Cloudflare Turnstile
    ts_scripts = [s for s in scripts if _is_turnstile_url(s)]
    ts_frames = [f for f in iframes if _is_turnstile_url(f["src"])] + \
        [{"src": u, "visible": True, "w": 0, "h": 0} for u in frame_urls if _is_turnstile_url(u)]
    ts_containers = [c for c in containers if "cf-turnstile" in c["cls"]]
    ts_inline = [i for i in inline if i.startswith("turnstile")]
    ts_fields = [n for n in token_fields if n == "cf-turnstile-response"]
    if ts_scripts or ts_frames or ts_containers or ts_inline or ts_fields:
        e = entry("cloudflare_turnstile")
        if ts_scripts:
            e["evidence"].append(f"script: {_host(ts_scripts[0])}{urlparse(ts_scripts[0]).path}")
        for f in ts_frames[:3]:
            e["evidence"].append(f"iframe: {_host(f['src'])}")
        if ts_containers:
            e["evidence"].append("container: .cf-turnstile")
        if ts_inline:
            e["evidence"].append("inline api: " + ", ".join(ts_inline))
        if ts_fields:
            e["evidence"].append("token field: cf-turnstile-response (name only)")
        appearance = next((c["appearance"] for c in ts_containers if c.get("appearance")), None)
        if appearance == "interaction-only":
            e["subtype"] = "interaction_only"
        elif appearance == "execute" or "turnstile.execute" in ts_inline:
            e["subtype"] = "execute_on_demand"
        else:
            e["subtype"] = "managed_or_non_interactive"
        e["widget_state"] = "iframe_loaded" if ts_frames else ("container_only" if ts_containers else
                                                              ("script_only" if ts_scripts else "api_call_only"))
        e["widget_loaded"] = e["widget_state"] == "iframe_loaded"

    detections = []
    for d in found.values():
        d.pop("_flags", None)
        detections.append(d)
    primary = next((d for d in detections if d["widget_loaded"]), detections[0] if detections else None)
    blocked = blocked_provider_resources or []
    return {
        "detections": detections,
        "primary": primary,
        "providers": [d["provider"] for d in detections],
        "any_widget_loaded": any(d["widget_loaded"] for d in detections),
        "blocked_provider_resources": blocked,
        "observability_note": (
            "Provider resources were blocked by the egress policy; absence of a widget is NOT evidence of absence."
            if blocked and not detections else None
        ),
    }


# ------------------------------------------------------------------ live inspection
async def settle_page(page, settle_ms: int = 6000, poll_ms: int = 500, evidence_wait_ms: int = 4000) -> dict[str, Any]:
    """
    Bounded wait so JavaScript-rendered widgets can appear: first network quiet (<= settle_ms), then keep polling
    (<= evidence_wait_ms) only while no provider evidence exists yet. Returns timing information.
    """
    started = time.perf_counter()
    network_idle = False
    try:
        await page.wait_for_load_state("networkidle", timeout=settle_ms)
        network_idle = True
    except Exception:
        pass
    waited = 0
    obs = await collect_evidence(page)
    while not _has_provider_evidence(obs) and waited < evidence_wait_ms:
        await page.wait_for_timeout(poll_ms)
        waited += poll_ms
        obs = await collect_evidence(page)
    return {"network_idle": network_idle, "extra_wait_ms": waited,
            "settle_seconds": round(time.perf_counter() - started, 2), "observation": obs}


async def collect_evidence(page) -> dict[str, Any]:
    try:
        return await page.evaluate(_COLLECT_JS)
    except Exception:
        return {"containers": [], "scripts": [], "iframes": [], "token_fields": [], "badges": 0, "inline_hits": []}


def _has_provider_evidence(obs: dict[str, Any]) -> bool:
    c = classify_observation(obs)
    return bool(c["detections"])


async def detect_on_page(page, guard=None, settle_ms: int = 6000, evidence_wait_ms: int = 4000) -> dict[str, Any]:
    """
    One call used by BOTH workflows. Returns a dict that is a superset of `detect_captcha_in_html`'s result
    (status / detected_providers / human_review_required / has_contact_form ...) with rendered-page evidence added.
    """
    settled = await settle_page(page, settle_ms=settle_ms, evidence_wait_ms=evidence_wait_ms)
    obs = settled["observation"]
    try:
        html = await page.content()
        title = await page.title()
    except Exception:
        html, title = "", ""
    base = detect_captcha_in_html(html, title)            # static markers + interstitial signatures + form heuristic
    frame_urls = [f.url for f in page.frames if f != page.main_frame]
    blocked = []
    if guard is not None:
        from app.services.provider_hosts import provider_for_url
        blocked = [b["url"] for b in guard.summary()["blocked_requests"] if provider_for_url(b["url"])]
    rendered = classify_observation(obs, frame_urls, blocked)

    # A bare substring in the page source (e.g. "hcaptcha.com" inside a config blob, a comment or marketing text) is
    # NOT a widget. When the live DOM was read successfully, providers seen only as static text are demoted to
    # `unconfirmed_static_mentions` and not reported as detected (found on breadtopia.com: hCaptcha text, Turnstile widget).
    dom_read_ok = "title" in obs
    static_only = [p for p in base["detected_providers"] if p not in rendered["providers"]] if dom_read_ok else []
    confirmed = [p for p in base["detected_providers"] if p not in static_only]
    providers = list(dict.fromkeys(confirmed + rendered["providers"]))
    status = base["status"]
    human_review = base["human_review_required"]
    if static_only and not providers and status == "captcha_detected":
        status, human_review = "no_known_captcha_detected", False
    if rendered["detections"] and status == "no_known_captcha_detected":
        status, human_review = "captcha_detected", True
    primary = rendered["primary"]
    method = base["detection_method"]
    if rendered["detections"]:
        method = "rendered_dom_iframe_inspection" if rendered["any_widget_loaded"] else "rendered_dom_markers"
    return {
        **base,
        "status": status,
        "detected_providers": providers,
        "human_review_required": human_review,
        "detection_method": method,
        "is_active_challenge": base["is_active_challenge"] or rendered["any_widget_loaded"],
        "captcha_subtype": primary["subtype"] if primary else None,
        "widget_state": primary["widget_state"] if primary else ("none" if not providers else "static_markers_only"),
        "widget_loaded": bool(rendered["any_widget_loaded"]),
        "detections": rendered["detections"],
        "unconfirmed_static_mentions": static_only,
        "blocked_provider_resources": blocked,
        "observability_note": rendered["observability_note"],
        "settle": {k: v for k, v in settled.items() if k != "observation"},
    }
