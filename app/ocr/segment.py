"""Glyph segmentation and feature extraction for the custom character classifier."""
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from app.ocr.preprocess import ink_mask

GLYPH_SIZE = 32


def hog(img: np.ndarray, cell: int = 8, bins: int = 9) -> np.ndarray:
    """Histogram of Oriented Gradients, implemented here (OpenCV 5 no longer ships HOGDescriptor).
    32x32 input -> 4x4 cells -> 3x3 overlapping 2x2-cell blocks (L2-Hys normalised) -> 324 values."""
    f = img.astype(np.float32) / 255.0
    gx = cv2.Sobel(f, cv2.CV_32F, 1, 0, ksize=1)
    gy = cv2.Sobel(f, cv2.CV_32F, 0, 1, ksize=1)
    mag = np.sqrt(gx * gx + gy * gy)
    ang = (np.arctan2(gy, gx) * 180.0 / np.pi) % 180.0
    pos = ang / (180.0 / bins)
    lo = np.floor(pos).astype(int) % bins
    hi = (lo + 1) % bins
    w_hi = pos - np.floor(pos)
    h, w = f.shape
    ch, cw = h // cell, w // cell
    hist = np.zeros((ch, cw, bins), np.float32)
    for cy in range(ch):
        for cx in range(cw):
            sl = (slice(cy * cell, (cy + 1) * cell), slice(cx * cell, (cx + 1) * cell))
            m, l, hh, wh = mag[sl].ravel(), lo[sl].ravel(), hi[sl].ravel(), w_hi[sl].ravel()
            np.add.at(hist[cy, cx], l, m * (1 - wh))
            np.add.at(hist[cy, cx], hh, m * wh)
    out = []
    for by in range(ch - 1):
        for bx in range(cw - 1):
            block = hist[by:by + 2, bx:bx + 2].ravel()
            block = block / (np.linalg.norm(block) + 1e-6)
            block = np.minimum(block, 0.2)
            out.append(block / (np.linalg.norm(block) + 1e-6))
    return np.concatenate(out).astype(np.float32)
FEATURE_DIM = 324 + 3  # HOG(32x32) + width/height ratio + relative height + relative vertical centre


@dataclass
class Glyph:
    x: int
    y: int
    w: int
    h: int
    mask: np.ndarray  # white ink on black, cropped to the glyph's box


def _components(mask: np.ndarray, min_h: int) -> list[Glyph]:
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    boxes = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if h >= min_h and area >= 14:
            boxes.append([x, y, x + w, y + h])
    boxes.sort(key=lambda b: b[0])
    # merge boxes that overlap strongly in x (e.g. a glyph split in two by a noise line)
    merged: list[list[int]] = []
    for b in boxes:
        if merged:
            m = merged[-1]
            overlap = min(m[2], b[2]) - max(m[0], b[0])
            if overlap > 0.5 * min(m[2] - m[0], b[2] - b[0]):
                m[0], m[1], m[2], m[3] = min(m[0], b[0]), min(m[1], b[1]), max(m[2], b[2]), max(m[3], b[3])
                continue
        merged.append(b[:])
    return [Glyph(b[0], b[1], b[2] - b[0], b[3] - b[1], mask[b[1]:b[3], b[0]:b[2]].copy()) for b in merged]


def _cut(g: Glyph, mask: np.ndarray, parts: int) -> list[Glyph]:
    step = g.w / parts
    out = []
    for k in range(parts):
        x0, x1 = int(round(g.x + k * step)), int(round(g.x + (k + 1) * step))
        out.append(Glyph(x0, g.y, x1 - x0, g.h, mask[g.y:g.y + g.h, x0:x1].copy()))
    return out


def _split_wide(glyphs: list[Glyph], mask: np.ndarray, expected: Optional[int]) -> list[Glyph]:
    """
    Touching characters form one wide component.
      * expected count known  -> split only the widest components, only while fewer than `expected`
      * expected unknown      -> split components wider than 2.0 x the median width into
                                 round(w / median) parts. (v1 used 1.6 x, which wrongly cut genuinely
                                 wide letters - W, M - in two; found on the DEV split.)
    """
    if len(glyphs) < 2:
        return glyphs
    if expected is not None:
        out = list(glyphs)
        while len(out) < expected:
            widest = max(range(len(out)), key=lambda i: out[i].w)
            if out[widest].w < 12:
                break
            out[widest:widest + 1] = _cut(out[widest], mask, 2)
        return out
    median = sorted(g.w for g in glyphs)[len(glyphs) // 2]
    out = []
    for g in glyphs:
        parts = int(round(g.w / median)) if median else 1
        out.extend(_cut(g, mask, parts) if parts >= 2 and g.w > 2.0 * median else [g])
    return out


def segment(img: np.ndarray, expected: Optional[int] = None) -> tuple[list[Glyph], np.ndarray]:
    """Return glyphs ordered left→right and the cleaned ink mask they came from."""
    mask = ink_mask(img)
    h_img = img.shape[0]
    glyphs = _split_wide(_components(mask, min_h=max(10, int(0.2 * h_img))), mask, expected)
    if expected is not None and len(glyphs) > expected:
        # drop the smallest extras (stray specks that survived filtering)
        glyphs = sorted(sorted(glyphs, key=lambda g: g.w * g.h, reverse=True)[:expected], key=lambda g: g.x)
    return glyphs, mask


def glyph_features(g: Glyph, image_h: int) -> np.ndarray:
    side = max(g.w, g.h)
    canvas = np.zeros((side, side), np.uint8)
    oy, ox = (side - g.h) // 2, (side - g.w) // 2
    canvas[oy:oy + g.h, ox:ox + g.w] = g.mask
    canvas = cv2.copyMakeBorder(canvas, 3, 3, 3, 3, cv2.BORDER_CONSTANT, value=0)
    small = cv2.resize(canvas, (GLYPH_SIZE, GLYPH_SIZE), interpolation=cv2.INTER_AREA)
    hog_vec = hog(small)
    extra = np.array([g.w / max(g.h, 1), g.h / image_h, (g.y + g.h / 2) / image_h], dtype=np.float32)
    return np.concatenate([hog_vec, extra]).astype(np.float32)
