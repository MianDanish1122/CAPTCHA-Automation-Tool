# Final Remaining Risks

1. **Real-world coverage is tiny.** 4 sites approved; 2 inspectable (2/2 agree), 2 blocked by bot protection. No statistical accuracy claim is possible. Re-running on a larger sample needs the owners' permission and a polite schedule.
2. **Access barriers are common.** Cloudflare challenges / 403s stop inspection by design. Roughly half the sample hit this; a larger CSV run should expect a similar not-accessible share.
3. **Breadtopia evidence predates the false-positive fix** (hCaptcha listed). Code is fixed and tested; the live file was not regenerated.
4. **Subtype detection is evidence-based, not exhaustive.** v3 versus invisible v2 cannot always be told apart from the page alone; the report separates provider agreement from subtype agreement.
5. **Widget "loaded" ≠ widget "working".** The provider's own POSTs are refused by the no-transmission policy, so we observe the embed, never a completed challenge.
6. **Verification is test-key level.** All three providers acquire tokens from official test widgets and are verified by the provider; no production keys were exercised, and a test key proves integration, not a production challenge.
7. **OCR accuracy (99.3 % held-out) is for the project's own synthetic generator.** No third-party CAPTCHA family was measured and none is solved.
8. **Scope conflict stays open.** The assignment text excludes contact-form automation; the employer message asks for Playwright interaction. Implemented: inspection plus non-submitting fill. Submission and CAPTCHA solving are out of scope without written authorisation.
9. **User-agent inconsistency** in the batch scanner (see FINAL_SECURITY_REVIEW).
10. **Operational:** single process, SQLite, background jobs lost on restart, no crash-recovery queue; deployment not performed.
11. **Human deliverable:** the 3–5 minute demo video is not recorded (script updated).
12. **Not browser-verified:** Settings, Audit, Users and OCR pages were exercised by the existing Phase 6B/7 suites and the demo rehearsal; this stage added browser coverage only for the Batch and Reports download flows.
