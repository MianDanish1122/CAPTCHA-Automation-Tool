"""Phase 7 OCR tests: reproducibility, split hygiene, metrics, engines' failure behaviour, API honesty."""
import csv
import hashlib
import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import OcrBenchmarkRun, OcrEvaluationRecord
from app.ocr import dataset as ds
from app.ocr import engines
from app.ocr.metrics import char_accuracy, levenshtein, position_accuracy, summarize
from app.services.ocr_service import generate_synthetic_captcha

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "datasets" / "ocr_synthetic_v1"


# ------------------------------------------------------------------ determinism & split hygiene
def test_same_seed_same_image_and_label():
    a, la = ds.sample_from_seed(123456)
    b, lb = ds.sample_from_seed(123456)
    assert a == b and la == lb
    c, lc = ds.sample_from_seed(123457)
    assert c != a


def test_generator_does_not_touch_global_random_state():
    import random
    random.seed(99)
    before = random.random()
    random.seed(99)
    ds.sample_from_seed(5)
    assert random.random() == before


def test_app_generator_is_reproducible_with_seed_and_random_without():
    assert generate_synthetic_captcha(seed=7) == generate_synthetic_captcha(seed=7)
    assert generate_synthetic_captcha()[0] != generate_synthetic_captcha()[0]
    assert generate_synthetic_captcha(text="ABC12", seed=1)[1] == "ABC12"


def test_splits_use_disjoint_seed_ranges():
    ranges = {k: (v, v + ds.SPLIT_SEED_SPAN[k]) for k, v in ds.SPLIT_SEED_BASE.items()}
    names = sorted(ranges, key=lambda k: ranges[k][0])
    for a, b in zip(names, names[1:]):
        assert ranges[a][1] <= ranges[b][0], f"{a} overlaps {b}"
    assert not set(ds.split_seeds("train", 3000)) & set(ds.split_seeds("dev", 200))
    assert not set(ds.split_seeds("dev", 200)) & set(ds.split_seeds("test", 300))


def test_committed_dataset_has_no_cross_split_duplicates_and_hashes_verify():
    seen = {}
    for split in ("dev", "test", "test2"):
        items = ds.load_split(DATASET, split)  # raises if any file no longer matches its recorded SHA-256
        assert len(items) >= 200
        for it in items:
            digest = hashlib.sha256(it["png"]).hexdigest()
            assert digest not in seen, f"{it['file']} duplicates {seen[digest]}"
            seen[digest] = it["file"]
            assert len(it["label"]) == 5 and set(it["label"]) <= set(ds.ALPHABET)


def test_dataset_labels_match_regenerated_images():
    """Ground truth + original images are preserved AND regenerable from the recorded seed."""
    rows = list(csv.DictReader(open(DATASET / "labels_test2.csv", encoding="utf-8")))[:5]
    for row in rows:
        png, label = ds.sample_from_seed(int(row["seed"]))
        assert label == row["label"]
        assert hashlib.sha256(png).hexdigest() == row["sha256"]


def test_tampered_dataset_file_is_detected(tmp_path):
    ds.build_split(tmp_path, "dev", 3)
    victim = next((tmp_path / "dev").glob("*.png"))
    victim.write_bytes(victim.read_bytes() + b"x")
    with pytest.raises(ValueError, match="modified"):
        ds.load_split(tmp_path, "dev")


def test_manifest_documents_splits_and_protocol():
    m = json.loads((DATASET / "manifest.json").read_text())
    assert set(m["splits"]) == {"train", "dev", "test", "test2"}
    assert m["splits"]["train"]["materialised"] is False
    assert "HELD OUT" in m["splits"]["test2"]["use"]


# ------------------------------------------------------------------ metrics
@pytest.mark.parametrize("a,b,d", [("", "", 0), ("abc", "abc", 0), ("abc", "abd", 1), ("abc", "", 3),
                                   ("kitten", "sitting", 3), ("ABCDE", "ABXCDE", 1)])
def test_levenshtein(a, b, d):
    assert levenshtein(a, b) == d


def test_char_accuracy_is_robust_to_insertions_unlike_positional_metric():
    truth, pred = "ABCDE", "XABCDE"  # one inserted char: positional metric collapses
    assert char_accuracy(pred, truth) > 0.8
    assert position_accuracy(pred, truth) == 0.0
    assert char_accuracy("", "") == 1.0 and char_accuracy("", "ABC") == 0.0


def test_summarize_counts_failures_in_every_denominator():
    rows = [
        {"truth": "AAAAA", "pred": "AAAAA", "latency_ms": 10, "failed": False},
        {"truth": "BBBBB", "pred": "BBBBX", "latency_ms": 20, "failed": False},
        {"truth": "CCCCC", "pred": "", "latency_ms": 30, "failed": True},
        {"truth": "DDDDD", "pred": "DDDDD", "latency_ms": 40, "failed": False},
    ]
    s = summarize(rows)
    assert s["samples"] == 4 and s["exact_matches"] == 2 and s["exact_match_pct"] == 50.0
    assert s["failures"] == 1 and s["failure_rate_pct"] == 25.0
    assert s["char_accuracy_pct"] == round(100 * (1 + 0.8 + 0 + 1) / 4, 2)
    assert s["latency_ms_mean"] == 25.0 and s["latency_ms_p50"] == 25.0
    lo, hi = s["exact_match_ci95_pct"]
    assert lo < 50.0 < hi


def test_summarize_empty_does_not_invent_numbers():
    assert summarize([]) == {"samples": 0}


# ------------------------------------------------------------------ engines
def test_every_engine_reports_instead_of_raising_on_garbage_input():
    for name in engines.ENGINES:
        r = engines.recognize(b"definitely not an image", name)
        assert r["failed"] is True and r["pred"] == "" and r["engine"] == name


def test_unknown_engine_rejected():
    with pytest.raises(ValueError):
        engines.recognize(b"x", "magic")


def test_custom_engine_reports_missing_model(monkeypatch):
    import app.ocr.model as m
    monkeypatch.setattr(m, "_cached", None)
    monkeypatch.setattr(m, "MODEL_PATH", Path("does-not-exist.npz"))
    png, _ = ds.sample_from_seed(1)
    r = engines.run_custom(png)
    assert r["failed"] is True and "model file not found" in r["error"]


def test_tesseract_failure_is_reported_not_raised(monkeypatch):
    import pytesseract
    monkeypatch.setattr(pytesseract, "image_to_data", lambda *a, **k: (_ for _ in ()).throw(
        pytesseract.TesseractNotFoundError()))
    png, _ = ds.sample_from_seed(1)
    r = engines.run_tesseract(png, "legacy")
    assert r["failed"] is True and "Tesseract" in r["error"]


def test_hybrid_falls_back_to_tesseract_when_custom_unavailable(monkeypatch):
    monkeypatch.setattr(engines, "run_custom", lambda *a, **k: engines._result("hybrid", "", 0.0, 0.0, failed=True,
                                                                              error="forced failure"))
    png, label = ds.sample_from_seed(2)
    r = engines.recognize(png, "hybrid")
    assert r["route"].startswith("tesseract_tuned") and r["fallback_reason"] == "forced failure"


def test_hybrid_uses_custom_when_confident():
    png, _ = ds.sample_from_seed(3)
    r = engines.recognize(png, "hybrid")
    assert r["route"] == "custom_mlp" and r["failed"] is False


def test_tuned_tesseract_config_comes_from_the_dev_experiment_file():
    saved = json.loads(engines.TUNED_FILE.read_text())
    assert saved["selected_on"] == "dev"
    assert {k: saved[k] for k in ("preprocess", "psm", "oem", "whitelist")} == engines.tuned_config()


# ------------------------------------------------------------------ accuracy regression (dev split, fixed samples)
def test_custom_model_accuracy_floor_on_dev_split():
    items = ds.load_split(DATASET, "dev")[:80]
    ok = sum(engines.run_custom(i["png"])["pred"] == i["label"] for i in items)
    assert ok / len(items) >= 0.90, f"custom model dropped to {ok}/{len(items)}"


def test_custom_model_beats_legacy_pipeline_on_same_samples():
    items = ds.load_split(DATASET, "dev")[:25]
    custom = sum(engines.recognize(i["png"], "custom_mlp")["pred"] == i["label"] for i in items)
    legacy = sum(engines.recognize(i["png"], "tesseract_legacy")["pred"] == i["label"] for i in items)
    assert custom > legacy


def test_model_metadata_discloses_training_split_and_hash():
    meta = json.loads((ROOT / "app" / "ocr" / "model" / "glyph_mlp_v1.json").read_text())
    assert "train (seeds 0.." in meta["train_split"] and meta["framework"].startswith("NumPy")
    from app.ocr.model import model_fingerprint
    assert meta["weights_sha256_16"] == model_fingerprint()


# ------------------------------------------------------------------ API
@pytest.fixture
def api():
    return TestClient(app)


def test_ocr_demo_records_real_ground_truth_and_edit_distance(api):
    res = api.post("/api/captcha/ocr-demo", json={"custom_text": "ABC23", "engine": "custom_mlp"})
    body = res.json()
    assert res.status_code == 200 and body["ground_truth"] == "ABC23"
    db = SessionLocal()
    try:
        rec = db.query(OcrEvaluationRecord).filter_by(id=body["evaluation_id"]).one()
        assert rec.ground_truth == "ABC23" and rec.ground_truth != "SYNTHETIC"
        assert rec.exact_match == (body["ocr_prediction"] == "ABC23")
        assert rec.character_accuracy == pytest.approx(100 * char_accuracy(body["ocr_prediction"], "ABC23"))
    finally:
        db.close()


def test_ocr_demo_rejects_unknown_engine_and_bad_text(api):
    assert api.post("/api/captcha/ocr-demo", json={"engine": "magic"}).status_code == 422
    assert api.post("/api/captcha/ocr-demo", json={"custom_text": "A B!"}).status_code == 422


def test_benchmark_api_is_deterministic_persisted_and_honest(api):
    payload = {"samples": 10, "engine": "custom_mlp", "split": "dev"}
    first = api.post("/api/captcha/ocr-benchmark", json=payload).json()
    second = api.post("/api/captcha/ocr-benchmark", json=payload).json()
    assert [r["ground_truth"] for r in first["results"]] == [r["ground_truth"] for r in second["results"]]
    assert [r["predicted_text"] for r in first["results"]] == [r["predicted_text"] for r in second["results"]]
    assert first["total_samples"] == 10 and first["dataset"] == "ocr_synthetic_v1"
    assert first["exact_matches"] == sum(r["exact_match"] for r in first["results"])
    db = SessionLocal()
    try:
        run = db.query(OcrBenchmarkRun).filter_by(id=first["run_id"]).one()
        assert run.engine == "custom_mlp" and run.samples == 10 and run.source == "api"
        assert run.exact_matches == first["exact_matches"]
    finally:
        db.close()
    listing = api.get("/api/captcha/ocr-benchmark/runs").json()
    assert listing["total"] >= 2 and listing["runs"][0]["samples"] >= 1


def test_benchmark_api_limits_inputs(api):
    assert api.post("/api/captcha/ocr-benchmark", json={"samples": 101}).status_code == 422
    assert api.post("/api/captcha/ocr-benchmark", json={"split": "train"}).status_code == 422
    assert api.post("/api/captcha/ocr-benchmark", json={"engine": "x"}).status_code == 422


def test_unlabelled_upload_creates_no_fake_accuracy_record(api):
    """An uploaded image has no ground truth: handling must not store invented accuracy."""
    import base64
    png, _ = ds.sample_from_seed(42)
    db = SessionLocal()
    before = db.query(OcrEvaluationRecord).count()
    before_fake = db.query(OcrEvaluationRecord).filter_by(ground_truth="SYNTHETIC").count()
    db.close()
    body = api.post("/api/captcha/evaluate-handling", json={
        "image_base64": base64.b64encode(png).decode(), "is_synthetic": True}).json()
    assert body["strategy_applied"] == "ocr_inference"
    assert body["ocr_result"]["ground_truth_known"] is False and body["ocr_result"]["predicted_text"]
    db = SessionLocal()
    try:
        assert db.query(OcrEvaluationRecord).count() == before
        assert db.query(OcrEvaluationRecord).filter_by(ground_truth="SYNTHETIC").count() == before_fake
    finally:
        db.close()


@pytest.mark.anyio
async def test_internal_handling_without_image_generates_labelled_sample_and_records_truth():
    from app.services.captcha_intelligence import execute_handling_strategy
    db = SessionLocal()
    try:
        before = db.query(OcrEvaluationRecord).count()
        res = await execute_handling_strategy(
            {"handling_strategy": "ocr_inference", "classification": "synthetic_text_captcha",
             "provider": "synthetic_ocr", "challenge_type": "synthetic_distortion_image"}, db=db)
        assert res["ocr_result"]["ground_truth_known"] is True
        rec = db.query(OcrEvaluationRecord).order_by(OcrEvaluationRecord.created_at.desc()).first()
        assert db.query(OcrEvaluationRecord).count() == before + 1
        assert len(rec.ground_truth) == 5 and rec.ground_truth != "SYNTHETIC"
        assert rec.exact_match == (rec.predicted_text == rec.ground_truth)
    finally:
        db.close()
