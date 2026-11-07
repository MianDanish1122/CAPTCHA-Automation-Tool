"""
Reproducible OCR benchmark for the project's OWN synthetic CAPTCHAs.

    python -m scripts.ocr_benchmark build-dataset            # materialise dev+test splits (+ manifest)
    python -m scripts.ocr_benchmark train                    # train the custom glyph model on the TRAIN split
    python -m scripts.ocr_benchmark experiments              # configuration search on the DEV split only
    python -m scripts.ocr_benchmark evaluate --engines ...   # evaluate on the HELD-OUT test split
    python -m scripts.ocr_benchmark verify-dataset           # check files against recorded hashes

Protocol: configurations are compared and selected on `dev`; the held-out `test` split is used only
by `evaluate` (and never to choose anything). All outputs are machine-readable JSON under
evidence/phase7/ocr/. Nothing here touches third-party CAPTCHA images.
"""
import argparse
import json
import platform
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import PIL  # noqa: E402
import pytesseract  # noqa: E402

from app.ocr import dataset as ds  # noqa: E402
from app.ocr import engines, model as glyph_model  # noqa: E402
from app.ocr.metrics import summarize  # noqa: E402

DATASET_DIR = ROOT / "datasets" / "ocr_synthetic_v1"
OUT_DIR = ROOT / "evidence" / "phase7" / "ocr"
DEV_N, TEST_N = 200, 300
TUNED_FILE = engines.TUNED_FILE


def environment() -> dict:
    try:
        tess = str(pytesseract.get_tesseract_version())
    except Exception:
        tess = "unavailable"
    return {
        "python": platform.python_version(), "platform": platform.platform(),
        "numpy": np.__version__, "opencv": cv2.__version__, "pillow": PIL.__version__,
        "tesseract": tess, "font_used": ds.load_font(34, "auto")[1],
        "generator": ds.GENERATOR_VERSION, "utc": datetime.now(timezone.utc).isoformat(),
    }


def write_json(name: str, payload: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / name
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_items(split: str, n: int) -> list[dict]:
    if (DATASET_DIR / f"labels_{split}.csv").exists():
        items = ds.load_split(DATASET_DIR, split)  # hash-verified committed files
        return items[:n]
    return list(ds.iter_generated(split, n))


def evaluate_engine(items: list[dict], recognize, workers: int = 1) -> tuple[dict, list[dict]]:
    def one(item):
        r = recognize(item["png"])
        return {"file": item["file"], "truth": item["label"], "pred": r["pred"], "latency_ms": r["latency_ms"],
                "failed": r["failed"], "confidence": r["confidence"], "error": r.get("error"),
                "route": r.get("route")}
    if workers > 1:
        with ThreadPoolExecutor(workers) as ex:
            rows = list(ex.map(one, items))
    else:
        rows = [one(i) for i in items]
    return summarize(rows), rows


# ------------------------------------------------------------------ commands
def cmd_build_dataset(_):
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    info = [ds.build_split(DATASET_DIR, "dev", DEV_N), ds.build_split(DATASET_DIR, "test", TEST_N),
            ds.build_split(DATASET_DIR, "test2", TEST_N)]
    manifest = {
        "name": "ocr_synthetic_v1",
        "generator": ds.GENERATOR_VERSION,
        "description": "Owned synthetic text CAPTCHAs: 5 symbols from a 32-symbol alphabet, 240x80, rotated "
                       "glyphs (+-18 deg), 3-5 noise lines, 100-180 noise dots, light random background.",
        "alphabet": ds.ALPHABET, "label_length": 5,
        "splits": {
            "train": {"seeds": f"{ds.SPLIT_SEED_BASE['train']}..", "materialised": False,
                      "note": "generated on demand (deterministic); used only to train the custom model"},
            "dev": {"seeds": f"{ds.SPLIT_SEED_BASE['dev']}..{ds.SPLIT_SEED_BASE['dev'] + DEV_N - 1}",
                    "samples": DEV_N, "materialised": True, "use": "experiments / configuration selection"},
            "test": {"seeds": f"{ds.SPLIT_SEED_BASE['test']}..{ds.SPLIT_SEED_BASE['test'] + TEST_N - 1}",
                     "samples": TEST_N, "materialised": True,
                     "use": "HELD OUT. Evaluated by the v1 pipeline; its error list was then inspected, so it is "
                            "reported but not used for the final claim"},
            "test2": {"seeds": f"{ds.SPLIT_SEED_BASE['test2']}..{ds.SPLIT_SEED_BASE['test2'] + TEST_N - 1}",
                      "samples": TEST_N, "materialised": True,
                      "use": "HELD OUT, never inspected before the final configuration was frozen: final results"},
        },
        "environment": environment(),
        "files": info,
    }
    (DATASET_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"dataset written to {DATASET_DIR}")


def cmd_verify_dataset(_):
    for split in ("dev", "test", "test2"):
        n = len(ds.load_split(DATASET_DIR, split))
        print(f"{split}: {n} files match their recorded SHA-256")


def cmd_train(args):
    meta = glyph_model.train(n_train_images=args.images, epochs=args.epochs)
    print(json.dumps(meta, indent=2))
    write_json("model_training.json", meta)


def cmd_experiments(args):
    """Search configurations on DEV only."""
    dev = load_items("dev", DEV_N)
    tess_items = dev[:args.tesseract_samples]
    results = []
    t0 = time.time()
    for pre in engines.PREPROCESSORS:
        for psm in (7, 8, 13):
            summary, _ = evaluate_engine(
                tess_items, lambda png, p=pre, s=psm: engines.run_tesseract(png, p, psm=s), workers=4)
            results.append({"engine": "tesseract", "preprocess": pre, "psm": psm, "oem": 3,
                            "whitelist": False, "split": "dev", **summary})
            print(f"tesseract {pre:15s} psm={psm:2d} exact={summary['exact_match_pct']:5.1f}% char={summary['char_accuracy_pct']:5.1f}%")
    ranked = sorted((r for r in results if r["engine"] == "tesseract"),
                    key=lambda r: (r["exact_match_pct"], r["char_accuracy_pct"]), reverse=True)
    for top in ranked[:3]:  # does a character whitelist / legacy engine help the best configs?
        for oem in (1, 3):
            summary, _ = evaluate_engine(
                tess_items, lambda png, t=top, o=oem: engines.run_tesseract(
                    png, t["preprocess"], psm=t["psm"], oem=o, whitelist=True), workers=4)
            results.append({"engine": "tesseract", "preprocess": top["preprocess"], "psm": top["psm"],
                            "oem": oem, "whitelist": True, "split": "dev", **summary})
            print(f"tesseract {top['preprocess']:15s} psm={top['psm']:2d} oem={oem} whitelist exact={summary['exact_match_pct']:5.1f}%")

    tess_only = [r for r in results if r["engine"] == "tesseract"]
    best = max(tess_only, key=lambda r: (r["exact_match_pct"], r["char_accuracy_pct"]))
    tuned = {"preprocess": best["preprocess"], "psm": best["psm"], "oem": best["oem"], "whitelist": best["whitelist"]}
    TUNED_FILE.parent.mkdir(parents=True, exist_ok=True)
    TUNED_FILE.write_text(json.dumps({**tuned, "selected_on": "dev", "dev_samples": len(tess_items),
                                      "dev_exact_match_pct": best["exact_match_pct"]}, indent=2), encoding="utf-8")
    engines.reload_tuned()

    for name in ("tesseract_legacy", "custom_mlp", "hybrid", "tesseract_tuned"):
        summary, _ = evaluate_engine(dev, lambda png, n=name: engines.recognize(png, n), workers=1)
        results.append({"engine": name, "split": "dev", **summary})
        print(f"{name:18s} (dev n={len(dev)}) exact={summary['exact_match_pct']}% char={summary['char_accuracy_pct']}%")

    out = write_json("experiments_dev.json", {
        "split": "dev", "purpose": "configuration search; NOT a final result", "tesseract_grid_samples": len(tess_items),
        "selected_tesseract_config": tuned, "elapsed_seconds": round(time.time() - t0, 1),
        "environment": environment(), "results": results})
    print("wrote", out)


def cmd_evaluate(args):
    test = load_items(args.split, TEST_N)
    report = {"split": args.split, "samples": len(test), "environment": environment(),
              "model": json.loads(glyph_model.META_PATH.read_text()) if glyph_model.META_PATH.exists() else None,
              "tesseract_tuned_config": engines.tuned_config(), "engines": {}}
    per_sample = {}
    for name in args.engines:
        summary, rows = evaluate_engine(test, lambda png, n=name: engines.recognize(png, n), workers=1)
        report["engines"][name] = summary
        per_sample[name] = rows
        print(f"{name:18s} n={summary['samples']} exact={summary['exact_match_pct']}% "
              f"(95% CI {summary['exact_match_ci95_pct']}) char={summary['char_accuracy_pct']}% "
              f"latency mean={summary['latency_ms_mean']}ms failures={summary['failures']}")
    write_json(args.out, report)
    write_json(args.out.replace(".json", "_samples.json"), per_sample)
    print("wrote", OUT_DIR / args.out)


def cmd_import_results(args):
    """Store a measured evaluation (JSON from `evaluate`) in the database so the dashboard can show it."""
    import hashlib
    from app.database import SessionLocal, init_db
    from app.models import OcrBenchmarkRun
    path = OUT_DIR / args.file
    raw = path.read_bytes()
    report = json.loads(raw)
    digest = hashlib.sha256(raw).hexdigest()[:16]
    init_db()
    db = SessionLocal()
    try:
        added = 0
        for engine, s in report["engines"].items():
            exists = [r for r in db.query(OcrBenchmarkRun).filter_by(source="cli_heldout", engine=engine).all()
                      if (json.loads(r.details or "{}").get("report_sha256_16") == digest)]
            if exists:
                continue
            db.add(OcrBenchmarkRun(
                source="cli_heldout" if report["split"] in ("test", "test2") else "cli_dev",
                dataset="ocr_synthetic_v1", split=report["split"], engine=engine,
                samples=s["samples"], exact_matches=s["exact_matches"], exact_match_pct=s["exact_match_pct"],
                char_accuracy_pct=s["char_accuracy_pct"], latency_ms_mean=s["latency_ms_mean"],
                latency_ms_p95=s["latency_ms_p95"], failures=s["failures"],
                details=json.dumps({"summary": s, "report_file": args.file, "report_sha256_16": digest,
                                    "environment": report.get("environment"),
                                    "tesseract_tuned_config": report.get("tesseract_tuned_config")}),
            ))
            added += 1
        db.commit()
        print(f"imported {added} run(s) from {args.file}")
    finally:
        db.close()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build-dataset").set_defaults(fn=cmd_build_dataset)
    sub.add_parser("verify-dataset").set_defaults(fn=cmd_verify_dataset)
    t = sub.add_parser("train")
    t.add_argument("--images", type=int, default=3000)
    t.add_argument("--epochs", type=int, default=60)
    t.set_defaults(fn=cmd_train)
    e = sub.add_parser("experiments")
    e.add_argument("--tesseract-samples", type=int, default=100)
    e.set_defaults(fn=cmd_experiments)
    i = sub.add_parser("import-results")
    i.add_argument("--file", default="evaluation_test2.json")
    i.set_defaults(fn=cmd_import_results)
    v = sub.add_parser("evaluate")
    v.add_argument("--engines", nargs="+", default=list(engines.ENGINES))
    v.add_argument("--split", default="test2", choices=["dev", "test", "test2"])
    v.add_argument("--out", default="evaluation_test2.json")
    v.set_defaults(fn=cmd_evaluate)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
