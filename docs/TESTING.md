# Testing Strategy, Test Fixtures & QA Procedures

## 1. Testing Philosophy

The test suite provides multi-layered verification:
1. **Unit Testing**: Isolated verification of CSV parsing, SSRF filters, OCR preprocessing, and token verifier mocks.
2. **Local Fixture Testing**: Headless browser verification using offline, deterministic HTML fixtures rather than live external networks.
3. **Integration Testing**: FastAPI test client exercising full request/response lifecycles, database persistence, and batch status queries.
4. **End-to-End Verification**: Complete batch upload, processing, database validation, and report export.

---

## 2. Test Fixtures Catalog (`tests/fixtures/`)

| Fixture File | Description | Expected Classification | Expected Provider |
| :--- | :--- | :--- | :--- |
| `normal_contact_form.html` | Clean contact form with name, email, subject, message, submit button | `no_known_captcha_detected` | `None` |
| `google_recaptcha.html` | Form containing active Google reCAPTCHA v2 checkbox container | `captcha_detected` | `google_recaptcha` |
| `invisible_recaptcha.html` | Form with invisible reCAPTCHA button and badge script | `captcha_detected` | `google_recaptcha_invisible` |
| `hcaptcha.html` | Form containing active hCaptcha widget and vendor script | `captcha_detected` | `hcaptcha` |
| `cloudflare_turnstile.html` | Form containing active Cloudflare Turnstile challenge widget | `captcha_detected` | `cloudflare_turnstile` |
| `unknown_challenge.html` | Simulates anti-bot challenge interstitial (Cloudflare 5s / Datadome) | `unsupported_challenge` | `unknown_challenge` |

---

## 3. Running Automated Tests

### 3.1 Run Pytest Suite
```powershell
# Run all automated tests
.\venv\Scripts\python.exe -m pytest tests/ -v

# Run with coverage report
.\venv\Scripts\python.exe -m pytest tests/ -v --tb=short
```

### 3.2 Run Legacy Verification Scripts
To ensure backward compatibility:
```powershell
.\venv\Scripts\python.exe test_csv_importer.py
.\venv\Scripts\python.exe test_browser_scanner.py
```

### 3.3 Test Evidence Generation
The automated test runner logs results to:
`evidence/test-results/pytest-output.txt`
and updates:
`evidence/TEST_EVIDENCE.md`
