"""
Deterministic synthetic CAPTCHA generator and dataset splits.

Every image is a pure function of (seed, parameters): `random.Random(seed)` is used, never the
global RNG, so the same seed reproduces the same image and label on the same Pillow version/font.
The generator is the project's own "owned" CAPTCHA; nothing is scraped from third parties.

Splits (disjoint seed ranges, so train/dev/test can never share an image):
    train :        0 ..  99_999   (used only to TRAIN the custom glyph model)
    dev   :  100_000 .. 199_999   (used for experiments / configuration selection)
    test  :  900_000 .. 949_999   (HELD OUT; its first results were inspected before the v2 segmentation fix)
    test2 :  950_000 .. 999_999   (HELD OUT, never inspected: final reported results)
"""
import csv
import hashlib
import io
import json
import random
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 32 symbols (I, O, 0, 1 removed: ambiguous)
GENERATOR_VERSION = "synthetic-v1"
SPLIT_SEED_BASE = {"train": 0, "dev": 100_000, "test": 900_000, "test2": 950_000}
SPLIT_SEED_SPAN = {"train": 100_000, "dev": 100_000, "test": 50_000, "test2": 50_000}

_ARIAL = Path(r"C:\Windows\Fonts\arial.ttf")


def load_font(size: int = 34, font: str = "auto") -> tuple[ImageFont.FreeTypeFont, str]:
    """Return (font, name). 'auto' = Arial when installed, otherwise Pillow's bundled default."""
    if font in ("auto", "arial") and _ARIAL.exists():
        try:
            return ImageFont.truetype(str(_ARIAL), size), "arial"
        except Exception:
            pass
    return ImageFont.load_default(size=size), "pillow-default"


def render_captcha(
    text: str,
    rng: random.Random,
    width: int = 240,
    height: int = 80,
    font: str = "auto",
) -> bytes:
    """Render one distorted text CAPTCHA (same visual distribution as the Phase 3-6 demo generator)."""
    fnt, _ = load_font(34, font)
    bg = (rng.randint(235, 255), rng.randint(235, 255), rng.randint(235, 255))
    image = Image.new("RGB", (width, height), color=bg)
    draw = ImageDraw.Draw(image)

    for _ in range(rng.randint(3, 5)):  # background noise lines
        color = (rng.randint(140, 200), rng.randint(140, 200), rng.randint(140, 200))
        draw.line(
            [(rng.randint(0, width), rng.randint(0, height)), (rng.randint(0, width), rng.randint(0, height))],
            fill=color, width=rng.randint(1, 2),
        )

    spacing = max(1, (width - 40) // max(1, len(text)))
    for i, ch in enumerate(text):  # rotated characters
        glyph = Image.new("RGBA", (50, 60), (255, 255, 255, 0))
        gd = ImageDraw.Draw(glyph)
        fill = (rng.randint(20, 90), rng.randint(20, 90), rng.randint(20, 90), 255)
        gd.text((8, 6), ch, font=fnt, fill=fill)
        rotated = glyph.rotate(rng.randint(-18, 18), expand=True, resample=Image.Resampling.BILINEAR)
        x = 15 + i * spacing + rng.randint(-2, 2)
        y = rng.randint(8, 18)
        image.paste(rotated, (x, y), rotated)

    for _ in range(rng.randint(100, 180)):  # salt-and-pepper dots
        color = (rng.randint(80, 180), rng.randint(80, 180), rng.randint(80, 180))
        draw.point((rng.randint(0, width - 1), rng.randint(0, height - 1)), fill=color)

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def sample_from_seed(seed: int, length: int = 5, font: str = "auto") -> tuple[bytes, str]:
    """(png_bytes, label) as a pure function of the seed."""
    rng = random.Random(seed)
    label = "".join(rng.choice(ALPHABET) for _ in range(length))
    return render_captcha(label, rng, font=font), label


def split_seeds(split: str, n: int) -> list[int]:
    if split not in SPLIT_SEED_BASE:
        raise ValueError(f"unknown split {split!r}")
    if n > SPLIT_SEED_SPAN[split]:
        raise ValueError("requested more samples than the split's seed range")
    base = SPLIT_SEED_BASE[split]
    return [base + i for i in range(n)]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_split(out_dir: Path, split: str, n: int, font: str = "auto") -> dict:
    """Materialise a split as PNG files + labels.csv (originals and ground truth are preserved)."""
    split_dir = out_dir / split
    split_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for seed in split_seeds(split, n):
        png, label = sample_from_seed(seed, font=font)
        name = f"{split}_{seed:06d}.png"
        (split_dir / name).write_bytes(png)
        rows.append({"file": f"{split}/{name}", "label": label, "seed": seed, "sha256": sha256(png)})
    with open(out_dir / f"labels_{split}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "label", "seed", "sha256"])
        w.writeheader()
        w.writerows(rows)
    return {"split": split, "samples": n, "seed_range": [rows[0]["seed"], rows[-1]["seed"]]}


def load_split(dataset_dir: Path, split: str) -> list[dict]:
    """Read a materialised split (image bytes + label); verifies each file against its recorded hash."""
    items = []
    with open(dataset_dir / f"labels_{split}.csv", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            data = (dataset_dir / row["file"]).read_bytes()
            if sha256(data) != row["sha256"]:
                raise ValueError(f"dataset file modified: {row['file']}")
            items.append({"file": row["file"], "label": row["label"], "seed": int(row["seed"]), "png": data})
    return items


def iter_generated(split: str, n: int, font: str = "auto"):
    """Generate a split on the fly (no files); identical content to build_split for the same font."""
    for seed in split_seeds(split, n):
        png, label = sample_from_seed(seed, font=font)
        yield {"file": f"{split}/{split}_{seed:06d}.png", "label": label, "seed": seed, "png": png}
