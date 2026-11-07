# Phase 7 — OCR Evaluation (Recognition / Solving Accuracy)

Everything below was produced by commands in this repository; raw outputs are in `evidence/phase7/ocr/`.
Scope: **owned, synthetic text CAPTCHAs only.** No third-party CAPTCHA image was collected, used for training or evaluated.

## 1. Baseline audit (what was wrong before)

| Problem found in the Phase 3–6 pipeline | Effect |
| :--- | :--- |
| Generator used the *global* `random`; the benchmark made fresh random images on every call | Numbers were not reproducible or comparable between runs |
| "Character accuracy" compared characters **by position** (`zip`) | One inserted/missed glyph zeroed the rest of the word |
| 20 random samples | Wide uncertainty (the reported 20 % exact had a 95 % interval of roughly 8–42 %) |
| Single fixed Tesseract configuration; no glyph-level logic; no stored results | Nothing to tune, nothing to prove |
| `evaluate-handling` stored OCR rows with `ground_truth="SYNTHETIC"`, `exact_match=False`, 0 % for uploaded images | Fabricated records (now excluded from statistics and no longer written) |

## 2. Dataset (`datasets/ocr_synthetic_v1`)

- Generator `synthetic-v1` (`app/ocr/dataset.py`): 5 symbols from a 32-symbol alphabet (`ABCDEFGHJKLMNPQRSTUVWXYZ23456789`; I, O, 0, 1 removed), 240×80 px, light random background, 3–5 noise lines, 100–180 noise dots, each glyph rotated ±18°, font Arial (Windows) — recorded in the manifest. Every image is a pure function of `(seed)` (`random.Random(seed)`, never the global RNG).
- **Disjoint seed ranges** guarantee no image is shared between splits (tested):

| Split | Seeds | Samples | Used for |
| :--- | :--- | :---: | :--- |
| train | 0 … 99 999 (first 3 000 used) | generated on demand | training the custom model only (⅔ Arial, ⅓ Pillow default font) |
| dev | 100 000 … | 200 (materialised) | experiments and configuration selection |
| test | 900 000 … | 300 (materialised) | held-out; **its first results were inspected** (see §6) |
| test2 | 950 000 … | 300 (materialised) | held-out, **never inspected before the configuration was frozen: final numbers** |

- Originals and ground truth are preserved: PNG files + `labels_<split>.csv` (file, label, seed, SHA-256) + `manifest.json`. `python -m scripts.ocr_benchmark verify-dataset` re-checks every hash; loading a tampered file raises (tested).
- Environment: Python 3.12, Pillow 13.0.0, OpenCV 5.0.0, NumPy 2.5.4, Tesseract 5.5.0 (recorded in every output JSON).

## 3. Methods compared

| Engine | Description |
| :--- | :--- |
| `tesseract_legacy` | The Phase 3–6 pipeline, unchanged: grayscale → bilateral filter → Otsu → 2×2 opening → Tesseract `--psm 7` (kept so before/after use the same code) |
| `tesseract_tuned` | Best configuration from the dev grid (below) |
| `custom_mlp` | **New, custom:** ink mask (dark-pixel threshold + small-component filter) → connected-component segmentation (overlap merging, width-based splitting) → 32×32 glyph normalisation → HOG (own NumPy implementation; OpenCV 5 dropped `HOGDescriptor`) + 3 geometry features → 327→256→32 network written in NumPy, trained with Adam on the project's own synthetic train split (14 910 glyphs from 2 982 images) |
| `hybrid` | `custom_mlp` first; falls back to `tesseract_tuned` when segmentation is implausible (not 3–12 glyphs, or ≠ expected length) or the weakest glyph probability < 0.55 |

### Experiments (DEV split only — `experiments_dev.json`)

Tesseract grid on the first 100 dev samples (exact match % / character accuracy %):

| Preprocessing | psm 7 | psm 8 | psm 13 |
| :--- | :---: | :---: | :---: |
| legacy (bilateral+Otsu+open) | 20 / 75.0 | 11 / 64.7 | 11 / 64.7 |
| Otsu, ×3 upscale | 7 / 26.8 | 4 / 57.4 | 4 / 57.4 |
| median + Otsu + component filter | 17 / 72.4 | 2 / 50.8 | 2 / 50.8 |
| adaptive threshold + component filter | 7 / 48.9 | 1 / 32.5 | 1 / 32.5 |
| dark-ink mask + upscale | 18 / 72.2 | 6 / 59.6 | 6 / 59.6 |
| dark-ink + closing | 23 / 74.4 | 6 / 58.3 | 6 / 58.3 |

Character whitelist added to the top three: legacy 33 / 78.7, dark-ink+closing 32 / 78.5, dark-ink 24 / 77.7 (`--oem 1` and `--oem 3` identical). **Selected on dev: legacy preprocessing + psm 7 + whitelist** (`app/ocr/model/tesseract_tuned.json`, written by the benchmark, not by hand). Conclusion: tuning Tesseract helps only a little; the problem is structural (see §5).

## 4. Final results — held-out `test2` (n = 300, never inspected) — **the numbers to quote**

| Engine | Exact match | 95 % CI | Character accuracy | Position accuracy | Failures* | Latency mean / p50 / p95 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `tesseract_legacy` (baseline) | 97/300 = **32.3 %** | 27.3–37.8 | 78.9 % | 72.3 % | 4 | 327 / 263 / 674 ms |
| `tesseract_tuned` | 109/300 = **36.3 %** | 31.1–41.9 | 81.0 % | 70.5 % | 4 | 247 / 217 / 409 ms |
| `custom_mlp` | 298/300 = **99.3 %** | 97.6–99.8 | 99.73 % | 99.73 % | 0 | 4.5 / 3.6 / 5.7 ms |
| `hybrid` (application default) | 298/300 = **99.3 %** | 97.6–99.8 | 99.80 % | 99.80 % | 0 | 5.7 / 4.3 / 8.3 ms |

\*Failure = engine error **or empty prediction**; failed samples count as wrong in every rate.
Character accuracy = 1 − Levenshtein/max(len) averaged over samples. Latency is wall-clock per image including preprocessing, measured sequentially on this machine.

**Improvement, measured on the same held-out set and the same metric code:** exact match 32.3 % → 99.3 % (legacy → custom/hybrid), character accuracy 78.9 % → 99.7–99.8 %, latency ≈ 327 ms → ≈ 5 ms.

### Other held-out evidence

| Set | Engine | Exact | Character | Note |
| :--- | :--- | :---: | :---: | :--- |
| `test` (v1 pipeline, first look) | tesseract_legacy | 24.0 % (72/300) | 74.8 % | |
| | tesseract_tuned | 30.3 % | 77.4 % | |
| | custom_mlp / hybrid (v1) | 97.0 % (291/300) | 99.0 % | before the segmentation fix |
| `test` (v2 pipeline) | custom_mlp | 99.0 % (297/300) | 99.71 % | same set, after the fix |
| `dev` (v2) | custom_mlp | 99.5 % (199/200) | 99.9 % | the fix was designed on dev errors |

The earlier "20 %" (20 random samples) is consistent with the legacy results above (24 % and 32 % on two 300-sample sets); the difference between those two sets shows the sampling noise a 20-sample benchmark cannot resolve.

## 5. Error analysis

- **Legacy Tesseract** (test2, 203 wrong of 300): 115 right length but wrong characters (D→O ×8, J→S ×5, 7→T ×5, 8→E ×4, B→8 ×4, V→Y ×4), **66 predictions too long** (noise lines/dots read as characters or glyphs split), 22 too short, 4 empty. Rotated glyphs with overlapping noise strokes are outside what a general line-text LSTM is trained for; psm/preprocessing changes move the error around (tuned: 80 too short, 32 too long) without removing it.
- **Custom model** (test2): 2 errors, both *too short* — `YEQWF→YEQK` and `W8QWW→W8QH`: two adjacent wide letters merged into one component and recognised as one glyph. Segmentation, not classification, is the residual error source (glyph-level accuracy on perfectly segmented dev images: 99.95 %, n = 2 000).
- **Defect found and fixed during Phase 7:** the first segmentation (v1) split any component wider than 1.6× the median into two, cutting genuinely wide letters (W, M) into "VV"/"LJ". Dev errors showed this (3 of 4); the rule was changed (split only above 2.0× median, or only as needed to reach the expected length), the model was retrained on the corrected glyphs, and held-out `test` improved 97.0 % → 99.0 %.

## 6. Protocol integrity (what this evidence does and does not show)

1. Configuration choices (Tesseract preprocessing/psm/whitelist, hybrid threshold, segmentation rule) were made on **dev**.
2. `test` was evaluated once with the v1 pipeline; its error list was then inspected, so **it is no longer a clean blind set**. The v1→v2 improvement on `test` is reported but not used for the headline claim.
3. `test2` was generated and first evaluated only after the final configuration and weights were frozen. All four engines were run on it once. Those are the headline numbers.
4. The v1 weights are kept in `evidence/phase7/glyph_mlp_v1_weights_before_segmentation_fix.npz` with their training metadata (`model_training_v1.json`). Current weights: `app/ocr/model/glyph_mlp_v1.npz`, sha256 prefix `e830723ec64c3ec2`.

## 7. Limitations — read before quoting the numbers

- **In-distribution result.** The custom model is trained on, and evaluated against, the *same generator*. 99.3 % means "the model solves this project's own synthetic CAPTCHA", **not** "it solves text CAPTCHAs in general". Different fonts, heavier warping, overlapping glyphs, colour tricks or longer strings are untested. The dark-ink mask exploits a property of our generator (dark glyphs, lighter noise).
- Font: dataset images use Arial where installed. The training split mixes Arial and Pillow's default font, but only Arial-rendered held-out images were measured.
- The tuned-Tesseract grid used 100 dev samples; differences of a few points between Tesseract configurations are within sampling noise (95 % CI about ±5 points).
- `confidence` for the custom engine is the mean per-glyph softmax probability — a model output, **not** a calibrated probability of being correct. Tesseract's confidence is its own word confidence.
- Latency is single-machine, single-thread wall-clock; the hybrid fell back to Tesseract on 1 of 300 held-out samples (see `route` in `evaluation_test2_samples.json`).
- Real third-party CAPTCHAs (reCAPTCHA, hCaptcha, Turnstile) are never attempted: they are detected and sent to human review.

## 8. Reproduce

```powershell
.\venv\Scripts\python.exe -m scripts.ocr_benchmark build-dataset      # deterministic; same hashes
.\venv\Scripts\python.exe -m scripts.ocr_benchmark verify-dataset
.\venv\Scripts\python.exe -m scripts.ocr_benchmark train               # ~1 min, writes app/ocr/model/
.\venv\Scripts\python.exe -m scripts.ocr_benchmark experiments         # dev only, ~10 min (Tesseract grid)
.\venv\Scripts\python.exe -m scripts.ocr_benchmark evaluate --split test2 --out evaluation_test2.json   # ~6 min
.\venv\Scripts\python.exe -m scripts.ocr_benchmark import-results --file evaluation_test2.json         # show in dashboard
```

Machine-readable outputs: `evaluation_test2.json` (+ `_samples.json` per-sample predictions), `evaluation_test_v1.json`, `evaluation_test_v2.json`, `evaluation_dev_v2.json`, `experiments_dev.json`, `model_training.json`, `model_training_v1.json`. Screenshots of the evaluation in the application: `evidence/phase7/e2e/06_ocr_evaluation.png`, `10_evaluation_dashboard.png`.
