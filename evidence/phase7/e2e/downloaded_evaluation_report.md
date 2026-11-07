# CAPTCHA Inspector - Evaluation Report

Generated (UTC): 2026-11-07T14:02:03.646259Z  |  Range: all time
Generated for: e2e_op7 (operator)

All figures come from persisted records; denominators are stated for every block.

## Inspections
- URL scans: 1 (by status: {'completed': 1})
- Batch inspections: 0
- Pages inspected: 2 (with CAPTCHA: 1, 50.0%)

## CAPTCHA types detected
_Denominator: 1 pages with a CAPTCHA detected_
- google_recaptcha: 1 (100.0%)

## OCR evaluation
_Denominator: OCR demo/handling evaluations with a KNOWN true label (unlabelled uploads are not counted)_
- Labelled evaluations: 2; exact match: 100.0%; mean character accuracy: 100.0%; mean latency: 52.1 ms

### Held-out benchmark (latest CLI run per engine)
- tesseract_legacy: n=300, exact 32.33%, char 78.88%, latency 327.29 ms, failures 4
- tesseract_tuned: n=300, exact 36.33%, char 81.0%, latency 246.67 ms, failures 4
- custom_mlp: n=300, exact 99.33%, char 99.73%, latency 4.52 ms, failures 0
- hybrid: n=300, exact 99.33%, char 99.8%, latency 5.74 ms, failures 0

## Verification outcomes
_Denominator: 4 recorded verification attempts_
- Confirmed by a provider: 1; simulated attempts: 1
- local_validation: rejected_missing_token=1
- provider_test_keys: rejected_timeout_or_duplicate=1, verified=1
- simulated: rejected_timeout_or_duplicate=1

## Failures
- Failed scans: 0 (0.0% of 1)

## Human review
- Cases: 1 (by status: {'pending': 1}); decisions recorded: 0
