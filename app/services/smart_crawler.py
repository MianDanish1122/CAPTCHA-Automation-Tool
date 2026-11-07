import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any
from urllib.parse import urlparse, urljoin, urlunparse, parse_qsl, urlencode
import urllib.robotparser

from playwright.async_api import BrowserContext, Page

from app.config import settings
from app.database import SessionLocal
from app.models import UrlScan, DiscoveredPage
from app.services.browser_scanner import get_shared_browser, detect_captcha_in_html
from app.services.security_guard import SecurityGuard
from app.services.network_guard import NetworkGuard, new_guarded_context

logger = logging.getLogger(__name__)

# Excluded static resource extensions
STATIC_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".bmp",
    ".css", ".js", ".mjs", ".map",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv",
    ".zip", ".tar", ".gz", ".rar", ".7z",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".webm",
    ".xml", ".json", ".rss", ".atom", ".txt",
)

# Scoring keywords
CONTACT_PATH_KEYWORDS = [
    "contact", "contact-us", "contactus", "get-in-touch",
    "reach-us", "reach-out", "feedback", "inquiry", "connect"
]

SUPPORT_PATH_KEYWORDS = [
    "support", "help", "customer-service", "help-center",
    "faq", "faqs", "knowledge-base", "desk", "ticket"
]

CONTACT_ANCHOR_KEYWORDS = [
    "contact", "contact us", "get in touch", "reach us",
    "reach out", "write to us", "message us", "email us", "connect"
]

SUPPORT_ANCHOR_KEYWORDS = [
    "support", "help", "customer service", "help center",
    "faq", "faqs", "submit a ticket", "ask a question", "help desk"
]

CONTACT_CONTENT_KEYWORDS = [
    "send a message", "contact us", "email us", "phone number",
    "our office", "headquarters", "inquiry form", "fill out the form",
    "get in touch with us", "leave a message", "we'd love to hear"
]

SUPPORT_CONTENT_KEYWORDS = [
    "customer support", "frequently asked questions", "help desk",
    "knowledge base", "submit a ticket", "support ticket", "ticket portal",
    "help center", "support team"
]


def normalize_url(url: str, base_url: Optional[str] = None) -> str:
    """
    Safely normalize URLs:
    - Resolves relative URLs against base_url
    - Strips fragments and tracking query parameters
    - Converts host to lowercase
    - Removes trailing slashes on paths
    """
    if not url:
        return ""

    url = url.strip()
    if url.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
        return ""

    if base_url:
        try:
            url = urljoin(base_url, url)
        except Exception:
            return ""

    try:
        parsed = urlparse(url)
    except Exception:
        return ""

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return ""

    netloc = parsed.netloc.lower()
    if ":" in netloc:
        host, port = netloc.split(":", 1)
        if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
            netloc = host

    path = parsed.path
    if not path:
        path = "/"
    elif len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    # Filter out tracking query parameters
    DROP_PARAMS = {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "fbclid", "gclid", "ref", "source", "_ga", "_gl", "mc_cid", "mc_eid"
    }

    clean_query = ""
    if parsed.query:
        try:
            pairs = parse_qsl(parsed.query, keep_blank_values=False)
            filtered = [(k, v) for k, v in pairs if k.lower() not in DROP_PARAMS]
            if filtered:
                filtered.sort(key=lambda x: x[0])
                clean_query = urlencode(filtered)
        except Exception:
            clean_query = ""

    return urlunparse((scheme, netloc, path, "", clean_query, ""))


def is_same_domain(url1: str, url2: str) -> bool:
    """Verify if two URLs share the same hostname or primary domain."""
    try:
        host1 = urlparse(url1).hostname or ""
        host2 = urlparse(url2).hostname or ""
        host1 = host1.lower().lstrip("www.")
        host2 = host2.lower().lstrip("www.")
        return host1 == host2 or host1.endswith("." + host2) or host2.endswith("." + host1)
    except Exception:
        return False


def calculate_page_score(
    url: str,
    anchor_text: str,
    page_title: str,
    page_html: str,
    forms_count: int,
    has_inputs: bool,
    has_textarea: bool,
    depth: int,
) -> tuple[str, float, dict[str, Any]]:
    """
    Score candidate page based on URL path, anchor text, title, content keywords, and form presence.
    Classify as contact_page, support_page, general_page, or unknown.
    """
    parsed = urlparse(url)
    path_lower = parsed.path.lower()
    anchor_lower = (anchor_text or "").lower()
    title_lower = (page_title or "").lower()
    html_lower = (page_html or "").lower()

    contact_score = 0.0
    support_score = 0.0
    evidence: dict[str, Any] = {
        "path_signals": [],
        "anchor_signals": [],
        "title_signals": [],
        "content_signals": [],
        "form_signals": [],
        "contact_score": 0.0,
        "support_score": 0.0,
        "classification_reason": "",
    }

    # 1. URL Path Signals
    for kw in CONTACT_PATH_KEYWORDS:
        if kw in path_lower:
            contact_score += 0.40
            evidence["path_signals"].append(f"Path matches contact keyword '{kw}'")
            break

    for kw in SUPPORT_PATH_KEYWORDS:
        if kw in path_lower:
            support_score += 0.40
            evidence["path_signals"].append(f"Path matches support keyword '{kw}'")
            break

    # 2. Anchor Text Signals
    for kw in CONTACT_ANCHOR_KEYWORDS:
        if kw in anchor_lower:
            contact_score += 0.25
            evidence["anchor_signals"].append(f"Anchor text matches contact keyword '{kw}'")
            break

    for kw in SUPPORT_ANCHOR_KEYWORDS:
        if kw in anchor_lower:
            support_score += 0.25
            evidence["anchor_signals"].append(f"Anchor text matches support keyword '{kw}'")
            break

    # 3. Page Title Signals
    for kw in CONTACT_PATH_KEYWORDS:
        if kw in title_lower:
            contact_score += 0.25
            evidence["title_signals"].append(f"Title matches contact keyword '{kw}'")
            break

    for kw in SUPPORT_PATH_KEYWORDS:
        if kw in title_lower:
            support_score += 0.25
            evidence["title_signals"].append(f"Title matches support keyword '{kw}'")
            break

    # 4. Content Signals
    for kw in CONTACT_CONTENT_KEYWORDS:
        if kw in html_lower:
            contact_score += 0.15
            evidence["content_signals"].append(f"Body contains contact phrase '{kw}'")
            break

    for kw in SUPPORT_CONTENT_KEYWORDS:
        if kw in html_lower:
            support_score += 0.15
            evidence["content_signals"].append(f"Body contains support phrase '{kw}'")
            break

    # 5. Form Signals
    if forms_count > 0:
        evidence["form_signals"].append(f"Page contains {forms_count} form(s)")
        if has_textarea:
            contact_score += 0.25
            evidence["form_signals"].append("Multi-line textarea detected (strong contact indicator)")
        elif has_inputs:
            contact_score += 0.15
            evidence["form_signals"].append("Interactive input fields detected")

    # Bound scores to 1.0
    contact_score = min(round(contact_score, 2), 1.0)
    support_score = min(round(support_score, 2), 1.0)
    evidence["contact_score"] = contact_score
    evidence["support_score"] = support_score

    # Classification
    if contact_score >= 0.45 and contact_score >= support_score:
        classification = "contact_page"
        confidence = contact_score
        evidence["classification_reason"] = (
            f"Classified as contact_page (score {contact_score}) based on URL path, anchor text, and form signals."
        )
    elif support_score >= 0.45:
        classification = "support_page"
        confidence = support_score
        evidence["classification_reason"] = (
            f"Classified as support_page (score {support_score}) based on support keywords and help desk indicators."
        )
    elif depth == 0 or (contact_score < 0.25 and support_score < 0.25):
        classification = "general_page"
        confidence = 0.85 if depth == 0 else 0.70
        evidence["classification_reason"] = (
            "Classified as general_page: domain landing page or navigation page without targeted contact forms."
        )
    else:
        classification = "unknown"
        confidence = 0.45
        evidence["classification_reason"] = "Signals indeterminate; page content did not strongly match known categories."

    return classification, confidence, evidence


@dataclass
class CrawlCandidate:
    url: str
    depth: int
    anchor_text: str = ""
    priority: int = 0


class SmartCrawler:
    """
    Intelligent website crawler engine:
    - Navigates domain with Playwright
    - Follows same-domain candidate links up to configurable depth and page limits
    - Discovers contact and support pages using heuristics
    - Inspects forms and detects CAPTCHAs without submitting forms or bypassing challenges
    - Enforces strict SSRF and redirect validation
    - Captures screenshots for evidence
    """

    def __init__(
        self,
        target_url: str,
        max_pages: Optional[int] = None,
        max_depth: Optional[int] = None,
        allow_loopback: bool = False,
    ):
        self.raw_target_url = target_url.strip()
        self.normalized_root_url = normalize_url(self.raw_target_url)
        self.base_domain = urlparse(self.normalized_root_url).hostname or ""
        
        if max_pages is not None:
            self.max_pages = min(max(max_pages, 1), 20)
        else:
            self.max_pages = settings.CRAWLER_MAX_PAGES

        if max_depth is not None:
            self.max_depth = min(max(max_depth, 0), 3)
        else:
            self.max_depth = settings.CRAWLER_MAX_DEPTH

        self.allow_loopback = allow_loopback and settings.can_allow_loopback

        self.visited_urls: set[str] = set()
        self.discovered_results: list[dict[str, Any]] = []

    async def check_robots_txt(self, base_url: str) -> Optional[urllib.robotparser.RobotFileParser]:
        """Attempt to fetch and parse robots.txt gracefully."""
        try:
            parsed = urlparse(base_url)
            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(robots_url)
            # Read robots.txt in a non-blocking executor
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, rp.read)
            return rp
        except Exception:
            return None

    async def crawl(self, scan_id: str) -> dict[str, Any]:
        """Run the crawl; if the task is cancelled at ANY point the scan is marked failed (never stuck)."""
        try:
            return await self._crawl_impl(scan_id)
        except asyncio.CancelledError:
            db = SessionLocal()
            try:
                scan = db.query(UrlScan).filter(UrlScan.id == scan_id).first()
                if scan is not None and scan.status == "crawling":
                    scan.status = "failed"
                    scan.error_message = "Crawl cancelled before completion."
                    scan.completed_at = datetime.now(timezone.utc)
                    db.commit()
            except Exception:
                db.rollback()
            finally:
                db.close()
            raise

    async def _crawl_impl(self, scan_id: str) -> dict[str, Any]:
        """
        Execute the crawler workflow and persist results to DB.
        """
        start_time = time.perf_counter()
        db = SessionLocal()

        # 1. Retrieve or verify UrlScan record
        scan = db.query(UrlScan).filter(UrlScan.id == scan_id).first()
        if not scan:
            scan = UrlScan(
                id=scan_id,
                submitted_url=self.raw_target_url,
                domain=self.base_domain,
                status="crawling",
            )
            db.add(scan)
            db.commit()
        else:
            scan.status = "crawling"
            db.commit()

        # 2. SSRF & Authorization Pre-check
        allowed, reason = SecurityGuard.validate_target_url(
            self.normalized_root_url,
            enforce_live_scan=True,
            allow_loopback=self.allow_loopback,
        )
        if not allowed:
            duration_ms = (time.perf_counter() - start_time) * 1000
            scan.status = "failed"
            scan.error_message = f"Security restriction: {reason}"
            scan.crawl_duration_ms = duration_ms
            scan.completed_at = datetime.now(timezone.utc)
            db.commit()
            db.close()
            return {
                "success": False,
                "scan_id": scan_id,
                "status": "failed",
                "error": scan.error_message,
                "pages_crawled": 0,
                "results": [],
            }

        # 3. Setup Evidence Directory
        scan_evidence_dir = settings.SCANS_EVIDENCE_DIR / scan_id
        scan_evidence_dir.mkdir(parents=True, exist_ok=True)

        # 4. Robots.txt parser
        rp = await self.check_robots_txt(self.normalized_root_url)

        # 5. Initialize crawl queue
        # Queue contains CrawlCandidate objects
        queue: list[CrawlCandidate] = [
            CrawlCandidate(url=self.normalized_root_url, depth=0, anchor_text="Homepage", priority=100)
        ]

        # All crawler egress (navigations, redirects, subresources) is routed through the
        # shared DNS-pinned SSRF guard. TLS certificate validation stays enabled.
        net_guard = NetworkGuard(allow_loopback=self.allow_loopback, label=f"crawl:{scan_id[:8]}")
        try:
            browser = await get_shared_browser()
            context = await new_guarded_context(
                browser,
                net_guard,
                user_agent=settings.CRAWLER_USER_AGENT,
                viewport={"width": 1280, "height": 800},
            )
        except Exception as launch_err:
            # Chromium missing/crashed: record a failed scan instead of leaving it "crawling" forever
            await net_guard.close()
            launch_msg = f"Browser could not be started: {type(launch_err).__name__}"
            scan.status = "failed"
            scan.error_message = launch_msg
            scan.crawl_duration_ms = (time.perf_counter() - start_time) * 1000
            scan.completed_at = datetime.now(timezone.utc)
            db.commit()
            db.close()
            return {
                "success": False,
                "scan_id": scan_id,
                "status": "failed",
                "error": launch_msg,
                "pages_crawled": 0,
                "results": [],
            }

        all_detected_providers: set[str] = set()
        contact_pages_count = 0

        try:
            page = await context.new_page()
            page.set_default_navigation_timeout(settings.CRAWLER_PAGE_TIMEOUT_MS)


            while queue and len(self.visited_urls) < self.max_pages:
                # Sort queue so highest priority candidate runs next
                queue.sort(key=lambda c: (-c.priority, c.depth))
                candidate = queue.pop(0)

                current_url = candidate.url
                if current_url in self.visited_urls:
                    continue

                # Depth check
                if candidate.depth > self.max_depth:
                    continue

                # Robots.txt adherence
                if rp:
                    try:
                        can_fetch = rp.can_fetch(settings.CRAWLER_USER_AGENT, current_url)
                        if not can_fetch:
                            logger.info(f"Skipping {current_url}: blocked by robots.txt")
                            continue
                    except Exception:
                        pass

                self.visited_urls.add(current_url)
                page_start_time = time.perf_counter()

                try:
                    # Navigate with Playwright
                    response = await page.goto(current_url, wait_until="domcontentloaded")
                    http_status = response.status if response else 200

                    # Validate final URL in case of HTTP redirects
                    # Redirects are followed (and validated) by the guard, not by Chromium.
                    final_url = net_guard.effective_url(page.url)
                    redir_allowed, redir_reason = SecurityGuard.validate_redirect_url(
                        final_url,
                        current_url,
                        enforce_live_scan=True,
                        allow_loopback=self.allow_loopback,
                        require_same_domain=True,
                    )
                    if not redir_allowed:
                        logger.warning(f"Aborting navigation on {final_url}: {redir_reason}")
                        continue

                    page_title = await page.title()
                    page_html = await page.content()

                    # Extract canonical URL if present
                    canonical_url = None
                    try:
                        canonical_el = await page.query_selector("link[rel='canonical']")
                        if canonical_el:
                            canonical_url = await canonical_el.get_attribute("href")
                            if canonical_url:
                                canonical_url = normalize_url(canonical_url, base_url=final_url)
                    except Exception:
                        pass

                    # Analyze forms in DOM
                    forms = await page.query_selector_all("form")
                    forms_count = len(forms)
                    has_inputs = False
                    has_textarea = False

                    if forms_count > 0:
                        inputs = await page.query_selector_all("input")
                        textareas = await page.query_selector_all("textarea")
                        has_inputs = len(inputs) > 0
                        has_textarea = len(textareas) > 0

                    # CAPTCHA detection
                    captcha_res = detect_captcha_in_html(page_html, page_title)
                    providers = captcha_res.get("detected_providers", [])
                    has_captcha = len(providers) > 0 or captcha_res.get("status") == "unsupported_challenge"
                    for prov in providers:
                        all_detected_providers.add(prov)

                    # Page classification & confidence score
                    classification, confidence, evidence = calculate_page_score(
                        url=final_url,
                        anchor_text=candidate.anchor_text,
                        page_title=page_title,
                        page_html=page_html,
                        forms_count=forms_count,
                        has_inputs=has_inputs,
                        has_textarea=has_textarea,
                        depth=candidate.depth,
                    )

                    if classification == "contact_page":
                        contact_pages_count += 1

                    # Screenshot evidence
                    slug = re.sub(r"[^a-zA-Z0-9_\-]", "_", urlparse(final_url).path).strip("_")
                    if not slug:
                        slug = "root"
                    page_idx = len(self.visited_urls)
                    screenshot_file = scan_evidence_dir / f"page_{page_idx}_{slug[:40]}.png"
                    try:
                        await page.screenshot(path=str(screenshot_file), full_page=False)
                        screenshot_rel_path = f"evidence/scans/{scan_id}/{screenshot_file.name}"
                    except Exception:
                        screenshot_rel_path = None

                    page_duration_ms = (time.perf_counter() - page_start_time) * 1000

                    # Persist DiscoveredPage to Database
                    discovered = DiscoveredPage(
                        scan_id=scan_id,
                        url=final_url,
                        depth=candidate.depth,
                        page_title=page_title,
                        canonical_url=canonical_url or final_url,
                        classification=classification,
                        confidence_score=confidence,
                        evidence=json.dumps(evidence),
                        contact_form_found=forms_count > 0,
                        forms_count=forms_count,
                        has_inputs=has_inputs,
                        has_textarea=has_textarea,
                        captcha_detected=has_captcha,
                        captcha_provider=", ".join(providers) if providers else None,
                        is_active_challenge=captcha_res.get("is_active_challenge", False),
                        human_review_required=captcha_res.get("human_review_required", False),
                        detection_method=captcha_res.get("detection_method", "dom_inspection"),
                        screenshot_path=screenshot_rel_path,
                        http_status=http_status,
                        crawl_duration_ms=page_duration_ms,
                    )
                    db.add(discovered)
                    db.commit()

                    # Phase 3 integration: Automatically enqueue HumanReviewRecord if CAPTCHA detected
                    if has_captcha and captcha_res.get("human_review_required"):
                        from app.models import HumanReviewRecord
                        from app.services.captcha_intelligence import classify_captcha
                        intel = classify_captcha(html=page_html, title=page_title)
                        review_entry = HumanReviewRecord(
                            scan_id=scan_id,
                            page_url=final_url,
                            captcha_provider=", ".join(providers) if providers else "unknown_challenge",
                            challenge_type=intel.get("challenge_type", "interactive_widget"),
                            reason_for_review=intel.get("explanation", "Third-party CAPTCHA challenge detected during crawl."),
                            review_status="pending",
                        )
                        db.add(review_entry)
                        db.commit()

                    self.discovered_results.append(discovered.to_dict())

                    # If depth allows, discover outgoing same-domain links
                    if candidate.depth < self.max_depth and len(self.visited_urls) < self.max_pages:
                        extracted_links = await page.eval_on_selector_all(
                            "a[href]",
                            "elements => elements.map(el => ({href: el.getAttribute('href'), text: el.innerText.trim()}))"
                        )

                        for link_obj in extracted_links:
                            raw_href = link_obj.get("href") or ""
                            link_text = link_obj.get("text") or ""
                            norm_href = normalize_url(raw_href, base_url=final_url)

                            if not norm_href or norm_href in self.visited_urls:
                                continue

                            # Skip static extensions
                            if norm_href.lower().endswith(STATIC_EXTENSIONS):
                                continue

                            # Same domain enforcement
                            if not is_same_domain(norm_href, self.normalized_root_url):
                                continue

                            # Calculate link candidate priority
                            link_path = urlparse(norm_href).path.lower()
                            link_text_lower = link_text.lower()
                            priority = 10

                            is_contact_link = any(kw in link_path for kw in CONTACT_PATH_KEYWORDS) or any(
                                kw in link_text_lower for kw in CONTACT_ANCHOR_KEYWORDS
                            )
                            is_support_link = any(kw in link_path for kw in SUPPORT_PATH_KEYWORDS) or any(
                                kw in link_text_lower for kw in SUPPORT_ANCHOR_KEYWORDS
                            )

                            if is_contact_link:
                                priority = 90
                            elif is_support_link:
                                priority = 70

                            # Avoid adding duplicate URLs to queue
                            if not any(c.url == norm_href for c in queue):
                                queue.append(
                                    CrawlCandidate(
                                        url=norm_href,
                                        depth=candidate.depth + 1,
                                        anchor_text=link_text,
                                        priority=priority,
                                    )
                                )

                except Exception as page_err:
                    logger.warning(f"Error crawling {current_url}: {str(page_err)}")
                    # Continue crawling remaining pages

            # Mark scan complete
            total_duration_ms = (time.perf_counter() - start_time) * 1000
            scan.status = "completed"
            scan.pages_crawled = len(self.visited_urls)
            scan.contact_pages_found = contact_pages_count
            scan.captcha_detected = len(all_detected_providers) > 0
            scan.captcha_providers = ", ".join(sorted(all_detected_providers)) if all_detected_providers else None
            scan.crawl_duration_ms = total_duration_ms
            scan.completed_at = datetime.now(timezone.utc)
            db.commit()

            return {
                "success": True,
                "scan_id": scan_id,
                "status": "completed",
                "submitted_url": self.raw_target_url,
                "domain": self.base_domain,
                "pages_crawled": len(self.visited_urls),
                "contact_pages_found": contact_pages_count,
                "captcha_detected": len(all_detected_providers) > 0,
                "captcha_providers": sorted(list(all_detected_providers)),
                "crawl_duration_ms": round(total_duration_ms, 2),
                "results": self.discovered_results,
            }

        except asyncio.CancelledError:
            # Job cancelled (shutdown / job manager): do not leave the scan stuck in "crawling"
            scan.status = "failed"
            scan.error_message = "Crawl cancelled before completion."
            scan.crawl_duration_ms = (time.perf_counter() - start_time) * 1000
            scan.completed_at = datetime.now(timezone.utc)
            try:
                db.commit()
            except Exception:
                db.rollback()
            raise

        except Exception as crawl_err:
            total_duration_ms = (time.perf_counter() - start_time) * 1000
            scan.status = "failed"
            scan.error_message = f"Crawling encountered an error: {str(crawl_err)}"
            scan.crawl_duration_ms = total_duration_ms
            scan.completed_at = datetime.now(timezone.utc)
            db.commit()
            return {
                "success": False,
                "scan_id": scan_id,
                "status": "failed",
                "error": scan.error_message,
                "pages_crawled": len(self.visited_urls),
                "results": self.discovered_results,
            }

        finally:
            await context.close()
            await net_guard.close()
            db.close()


async def inspect_url_pipeline(
    url: str,
    max_pages: Optional[int] = None,
    max_depth: Optional[int] = None,
    allow_loopback: bool = False,
) -> dict[str, Any]:
    """
    High-level entrypoint for URL inspection and smart crawling.
    """
    from app.models import generate_uuid
    scan_id = generate_uuid()

    crawler = SmartCrawler(
        target_url=url,
        max_pages=max_pages,
        max_depth=max_depth,
        allow_loopback=allow_loopback,
    )
    result = await crawler.crawl(scan_id=scan_id)
    return result
