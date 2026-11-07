"""
Custom glyph classifier: HOG features + a small fully-connected network implemented in NumPy.

No external model, no pretrained weights and no network call: the weights in
`app/ocr/model/glyph_mlp_v1.npz` are produced by `python -m scripts.ocr_train` from the project's
own synthetic TRAIN split (seeds 0..N). Architecture: 327 -> 256 (ReLU) -> 32 (softmax),
trained with Adam, L2 regularisation and mini-batches.
"""
import hashlib
import json
import time
from pathlib import Path
from typing import Optional

import numpy as np

from app.ocr.dataset import ALPHABET, iter_generated
from app.ocr.preprocess import decode_image
from app.ocr.segment import FEATURE_DIM, glyph_features, segment

MODEL_DIR = Path(__file__).resolve().parent / "model"
MODEL_PATH = MODEL_DIR / "glyph_mlp_v1.npz"
META_PATH = MODEL_DIR / "glyph_mlp_v1.json"


class GlyphMLP:
    def __init__(self, hidden: int = 256):
        self.hidden = hidden
        self.classes = list(ALPHABET)
        self.params: dict[str, np.ndarray] = {}
        self.mean = np.zeros(FEATURE_DIM, np.float32)
        self.std = np.ones(FEATURE_DIM, np.float32)

    # ---------------------------------------------------------------- inference
    def predict_proba(self, feats: np.ndarray) -> np.ndarray:
        x = (feats - self.mean) / self.std
        h = np.maximum(0, x @ self.params["W1"] + self.params["b1"])
        logits = h @ self.params["W2"] + self.params["b2"]
        logits -= logits.max(axis=1, keepdims=True)
        e = np.exp(logits)
        return e / e.sum(axis=1, keepdims=True)

    # ---------------------------------------------------------------- training
    def fit(self, X: np.ndarray, y: np.ndarray, epochs: int = 60, batch: int = 128,
            lr: float = 2e-3, l2: float = 1e-4, seed: int = 0, log=None) -> None:
        rng = np.random.default_rng(seed)
        self.mean, self.std = X.mean(0), X.std(0) + 1e-6
        Xn = ((X - self.mean) / self.std).astype(np.float32)
        n, d = Xn.shape
        k = len(self.classes)
        self.params = {
            "W1": (rng.standard_normal((d, self.hidden)) * np.sqrt(2.0 / d)).astype(np.float32),
            "b1": np.zeros(self.hidden, np.float32),
            "W2": (rng.standard_normal((self.hidden, k)) * np.sqrt(2.0 / self.hidden)).astype(np.float32),
            "b2": np.zeros(k, np.float32),
        }
        m = {p: np.zeros_like(v) for p, v in self.params.items()}
        v = {p: np.zeros_like(val) for p, val in self.params.items()}
        step = 0
        Y = np.eye(k, dtype=np.float32)[y]
        for epoch in range(epochs):
            order = rng.permutation(n)
            loss_sum = 0.0
            for s in range(0, n, batch):
                idx = order[s:s + batch]
                xb, yb = Xn[idx], Y[idx]
                h_pre = xb @ self.params["W1"] + self.params["b1"]
                h = np.maximum(0, h_pre)
                logits = h @ self.params["W2"] + self.params["b2"]
                logits -= logits.max(axis=1, keepdims=True)
                p = np.exp(logits)
                p /= p.sum(axis=1, keepdims=True)
                loss_sum += float(-(yb * np.log(p + 1e-9)).sum())
                dlog = (p - yb) / len(idx)
                grads = {
                    "W2": h.T @ dlog + l2 * self.params["W2"],
                    "b2": dlog.sum(0),
                }
                dh = dlog @ self.params["W2"].T
                dh[h_pre <= 0] = 0
                grads["W1"] = xb.T @ dh + l2 * self.params["W1"]
                grads["b1"] = dh.sum(0)
                step += 1
                for name, g in grads.items():  # Adam
                    m[name] = 0.9 * m[name] + 0.1 * g
                    v[name] = 0.999 * v[name] + 0.001 * g * g
                    mh = m[name] / (1 - 0.9 ** step)
                    vh = v[name] / (1 - 0.999 ** step)
                    self.params[name] -= (lr * mh / (np.sqrt(vh) + 1e-8)).astype(np.float32)
            if log and (epoch % 10 == 0 or epoch == epochs - 1):
                log(f"epoch {epoch + 1}/{epochs} loss={loss_sum / n:.4f}")

    # ---------------------------------------------------------------- persistence
    def save(self, path: Path = MODEL_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, mean=self.mean, std=self.std, **self.params)

    @classmethod
    def load(cls, path: Path = MODEL_PATH) -> "GlyphMLP":
        data = np.load(path)
        model = cls(hidden=int(data["W1"].shape[1]))
        model.mean, model.std = data["mean"], data["std"]
        model.params = {k: data[k] for k in ("W1", "b1", "W2", "b2")}
        return model


_cached: Optional[GlyphMLP] = None


def get_model() -> Optional[GlyphMLP]:
    """Load the trained model once; None if no model file exists (engine then reports unavailable)."""
    global _cached
    if _cached is None and MODEL_PATH.exists():
        _cached = GlyphMLP.load()
    return _cached


def model_fingerprint() -> Optional[str]:
    return hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest()[:16] if MODEL_PATH.exists() else None


# ------------------------------------------------------------------- data for training
def font_for_seed(seed: int) -> str:
    """Training mixes the OS font and Pillow's bundled font so the model is not tied to one typeface."""
    return "pillow-default" if seed % 3 == 0 else "auto"


def collect_glyphs(split: str, n_images: int, log=None) -> tuple[np.ndarray, np.ndarray, dict]:
    """
    Segment generated images and keep glyphs only from images whose segmentation found exactly
    len(label) glyphs (so each glyph's label is known without manual annotation).
    """
    X, y = [], []
    kept = skipped = 0
    for item in (_it for _it in _gen_mixed(split, n_images)):
        img = decode_image(item["png"])
        glyphs, _ = segment(img, expected=None)
        if len(glyphs) != len(item["label"]):
            skipped += 1
            continue
        kept += 1
        for g, ch in zip(glyphs, item["label"]):
            X.append(glyph_features(g, img.shape[0]))
            y.append(ALPHABET.index(ch))
    stats = {"images": n_images, "images_used": kept, "images_skipped_bad_segmentation": skipped, "glyphs": len(y)}
    if log:
        log(f"{split}: {stats}")
    return np.array(X, np.float32), np.array(y, np.int64), stats


def _gen_mixed(split: str, n: int):
    from app.ocr.dataset import sample_from_seed, split_seeds
    for seed in split_seeds(split, n):
        png, label = sample_from_seed(seed, font=font_for_seed(seed) if split == "train" else "auto")
        yield {"png": png, "label": label, "seed": seed}


def train(n_train_images: int = 3000, epochs: int = 60, hidden: int = 256, log=print) -> dict:
    t0 = time.time()
    X, y, train_stats = collect_glyphs("train", n_train_images, log)
    model = GlyphMLP(hidden=hidden)
    model.fit(X, y, epochs=epochs, log=log)
    probs = model.predict_proba(X)
    train_glyph_acc = float((probs.argmax(1) == y).mean())
    Xd, yd, dev_stats = collect_glyphs("dev", 400, log)
    dev_glyph_acc = float((model.predict_proba(Xd).argmax(1) == yd).mean())
    model.save()
    meta = {
        "model": "glyph_mlp_v1",
        "architecture": f"HOG(32x32, 324) + 3 geometry features -> {hidden} ReLU -> 32 softmax",
        "framework": "NumPy (implemented from scratch)",
        "train_split": "train (seeds 0..%d), fonts: arial (2/3) + pillow-default (1/3)" % (n_train_images - 1),
        "train_stats": train_stats,
        "epochs": epochs,
        "train_glyph_accuracy_pct": round(100 * train_glyph_acc, 2),
        "dev_glyph_accuracy_pct": round(100 * dev_glyph_acc, 2),
        "dev_stats": dev_stats,
        "weights_sha256_16": model_fingerprint(),
        "train_seconds": round(time.time() - t0, 1),
        "note": "dev accuracy is on perfectly-segmented dev images only; end-to-end results are in the benchmark",
    }
    META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta
