# 5. OCR Laboratory (the only place CAPTCHAs are actually solved)

**Purpose:** demonstrate automated solving on **our own synthetic text CAPTCHAs**. It does not apply to reCAPTCHA, hCaptcha or Turnstile.

## How to use
1. Open `/ocr`.
2. **Run OCR Evaluation:** generates a distorted text image, runs the computer-vision pipeline and a text reader, shows the answer, correct/incorrect and timing.
3. **Randomize:** new random text.
4. **Engine / Split / Samples + Run Benchmark:** measures accuracy over many generated images.

## Note
The reported accuracy (about 99.3%) is a benchmark on our own generator. It is not a claim about real-world CAPTCHAs.
