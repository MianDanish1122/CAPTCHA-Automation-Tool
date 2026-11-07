
import asyncio

from app.services.browser_scanner import inspect_local_demo


TEST_CASES = [
    {
        "name": "Google reCAPTCHA",
        "html": '<html><head><title>Google Test</title></head>'
                '<body><div data-src="google.com/recaptcha"></div></body></html>',
        "expected": ["google_recaptcha"],
    },
    {
        "name": "hCaptcha",
        "html": '<html><head><title>hCaptcha Test</title></head>'
                '<body><div data-src="hcaptcha.com"></div></body></html>',
        "expected": ["hcaptcha"],
    },
    {
        "name": "Cloudflare Turnstile",
        "html": '<html><head><title>Turnstile Test</title></head>'
                '<body><div data-src="challenges.cloudflare.com/turnstile"></div></body></html>',
        "expected": ["cloudflare_turnstile"],
    },
    {
        "name": "No CAPTCHA",
        "html": '<html><head><title>Normal Form</title></head>'
                '<body><form><input name="email"></form></body></html>',
        "expected": [],
    },
]


async def main():
    passed = 0

    print("\n========== PROVIDER DETECTION TESTS ==========")

    for test in TEST_CASES:
        result = await inspect_local_demo(test["html"])

        success = (
            result["success"]
            and result["detected_providers"] == test["expected"]
        )

        if success:
            passed += 1

        print(f"\nTest: {test['name']}")
        print("Detected:", result["detected_providers"])
        print("Expected:", test["expected"])
        print("Result:", "PASS" if success else "FAIL")

    print("\n==============================================")
    print(f"Tests passed: {passed}/{len(TEST_CASES)}")
    print("==============================================")


if __name__ == "__main__":
    asyncio.run(main())
