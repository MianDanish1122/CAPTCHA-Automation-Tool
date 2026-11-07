"""
OCR engines for owned/synthetic text CAPTCHAs.

    tesseract_legacy   Phase 3-6 pipeline (kept so before/after numbers use identical code)
    tesseract_tuned    best Tesseract configuration found on the DEV split (see benchmark)
    custom_mlp         segmentation + HOG/MLP glyph classifier trained on the project's own data
    hybrid             custom_mlp first; falls back to tesseract_tuned when segmentation looks
                       implausible or the classifier is not confident
Every engine returns the same dict and never raises: failures are reported, not hidden.
"""
import json
import time
from pathlib import Path
from typing import Optional

import numpy as np
import pytesseract

from app.config import settings
from app.ocr.preprocess import PREPROCESSORS, decode_image
from app.ocr.segment import glyph_features, segment

if Path(settings.TESSERACT_CMD).exists():
    pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD

# The tuned Tesseract configuration is WRITTEN BY the benchmark (`experiments`, DEV split only) to
# TUNED_FILE; the default below is used until that file exists. Never edit by hand.
TUNED_FILE = Path(__file__).resolve().parent / "model" / "tesseract_tuned.json"
_DEFAULT_TUNED = {"preprocess": "dark_ink", "psm": 8, "oem": 3, "whitelist": False}
TUNED_TESSERACT = dict(_DEFAULT_TUNED)


def reload_tuned() -> dict:
    global TUNED_TESSERACT
    cfg = dict(_DEFAULT_TUNED)
    if TUNED_FILE.exists():
        saved = json.loads(TUNED_FILE.read_text(encoding="utf-8"))
        cfg.update({k: saved[k] for k in ("preprocess", "psm", "oem", "whitelist") if k in saved})
    TUNED_TESSERACT = cfg
    return cfg


def tuned_config() -> dict:
    return dict(TUNED_TESSERACT)


reload_tuned()
HYBRID_MIN_GLYPH_PROB = 0.55
ENGINES = ("tesseract_legacy", "tesseract_tuned", "custom_mlp", "hybrid")


def _result(engine, pred="", conf=0.0, t0=0.0, failed=False, error=None, **extra) -> dict:
    return {
        "engine": engine,
        "pred": pred,
        "confidence": round(float(conf), 2),
        "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
        "failed": bool(failed or not pred),
        "error": error,
        **extra,
    }


def run_tesseract(png: bytes, preprocess: str, psm: int = 7, oem: int = 3, whitelist: bool = False,
                  engine: str = "tesseract") -> dict:
    t0 = time.perf_counter()
    try:
        img = PREPROCESSORS[preprocess](decode_image(png))
        config = f"--oem {oem} --psm {psm}"
        if whitelist:
            config += " -c tessedit_char_whitelist=ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        data = pytesseract.image_to_data(img, config=config, output_type=pytesseract.Output.DICT)
        words = [(str(t), float(c)) for t, c in zip(data["text"], data["conf"]) if str(t).strip()]
        text = "".join(c for w, _ in words for c in w if c.isalnum()).upper()
        confs = [c for _, c in words if c >= 0]
        conf = sum(confs) / len(confs) if confs else 0.0
        return _result(engine, text, conf, t0, preprocess=preprocess, psm=psm)
    except Exception as exc:  # engine/binary/image failure -> reported, not raised
        return _result(engine, "", 0.0, t0, failed=True, error=f"{type(exc).__name__}: {exc}"[:200])


def run_custom(png: bytes, expected_length: Optional[int] = None, engine: str = "custom_mlp") -> dict:
    from app.ocr.model import get_model
    t0 = time.perf_counter()
    model = get_model()
    if model is None:
        return _result(engine, "", 0.0, t0, failed=True, error="glyph model file not found (run scripts/ocr_train)")
    try:
        img = decode_image(png)
        glyphs, _ = segment(img, expected=expected_length)
        if not glyphs:
            return _result(engine, "", 0.0, t0, failed=True, error="no glyphs found", glyphs=0)
        feats = np.stack([glyph_features(g, img.shape[0]) for g in glyphs])
        probs = model.predict_proba(feats)
        idx = probs.argmax(1)
        top = probs[np.arange(len(idx)), idx]
        text = "".join(model.classes[i] for i in idx)
        # confidence = mean per-glyph softmax probability (a model output, not a calibrated probability)
        return _result(engine, text, 100.0 * float(top.mean()), t0, glyphs=len(glyphs),
                       min_glyph_prob=round(float(top.min()), 4))
    except Exception as exc:
        return _result(engine, "", 0.0, t0, failed=True, error=f"{type(exc).__name__}: {exc}"[:200])


def recognize(png: bytes, engine: str = "hybrid", expected_length: Optional[int] = None) -> dict:
    if engine == "tesseract_legacy":
        return run_tesseract(png, "legacy", psm=7, oem=3, engine=engine)
    if engine == "tesseract_tuned":
        return run_tesseract(png, **TUNED_TESSERACT, engine=engine)
    if engine == "custom_mlp":
        return run_custom(png, expected_length, engine=engine)
    if engine == "hybrid":
        t0 = time.perf_counter()
        first = run_custom(png, expected_length, engine="hybrid")
        plausible = (not first["failed"] and 3 <= first.get("glyphs", 0) <= 12
                     and first.get("min_glyph_prob", 0) >= HYBRID_MIN_GLYPH_PROB
                     and (expected_length is None or first["glyphs"] == expected_length))
        if plausible:
            first["route"] = "custom_mlp"
            first["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            return first
        second = run_tesseract(png, **TUNED_TESSERACT, engine="hybrid")
        second["route"] = "tesseract_tuned (fallback)"
        second["fallback_reason"] = first.get("error") or "low confidence / implausible segmentation"
        second["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return second
    raise ValueError(f"unknown engine {engine!r}")
