"""
Image preprocessing variants (all operate on OWNED/synthetic CAPTCHA images).

Every variant returns an 8-bit single-channel image with DARK text on a WHITE background and a
white margin (Tesseract performs poorly when glyphs touch the image border).
"""
from typing import Callable

import cv2
import numpy as np

PAD = 20


def decode_image(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("not a decodable image")
    return img


def _pad(binary_text_on_white: np.ndarray) -> np.ndarray:
    return cv2.copyMakeBorder(binary_text_on_white, PAD, PAD, PAD, PAD, cv2.BORDER_CONSTANT, value=255)


def remove_small_components(mask: np.ndarray, min_area: int) -> np.ndarray:
    """mask: white(255)=ink. Drops connected components smaller than min_area pixels."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    keep = np.zeros_like(mask)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            keep[labels == i] = 255
    return keep


def ink_mask(img: np.ndarray, thr: int = 115, min_area: int = 14) -> np.ndarray:
    """
    Ink = dark pixels. In the project's synthetic CAPTCHAs glyphs are dark (RGB < ~90) while noise
    lines and dots are lighter or single pixels, so a dark-pixel threshold plus a small-component
    filter isolates the characters. (Domain prior for our own generator; documented as such.)
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    mask = (gray < thr).astype(np.uint8) * 255
    return remove_small_components(mask, min_area)


# ---------------------------------------------------------------- variants
def legacy(img: np.ndarray) -> np.ndarray:
    """The Phase 3-6 pipeline, unchanged: gray -> bilateral -> Otsu(inv) -> open 2x2 -> invert."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    den = cv2.bilateralFilter(gray, d=5, sigmaColor=50, sigmaSpace=50)
    _, th = cv2.threshold(den, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    opened = cv2.morphologyEx(th, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2)))
    return cv2.bitwise_not(opened)


def otsu_upscaled(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    big = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    big = cv2.GaussianBlur(big, (5, 5), 0)
    _, th = cv2.threshold(big, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return _pad(th)


def median_otsu_cc(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    med = cv2.medianBlur(gray, 3)
    _, th = cv2.threshold(med, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    th = remove_small_components(th, 25)
    th = cv2.resize(th, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
    return _pad(cv2.bitwise_not(th))


def adaptive_cc(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 12)
    th = remove_small_components(th, 25)
    th = cv2.resize(th, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
    return _pad(cv2.bitwise_not(th))


def dark_ink(img: np.ndarray) -> np.ndarray:
    """Dark-pixel mask + component filter, upscaled and smoothed so Tesseract sees clean strokes."""
    mask = ink_mask(img)
    mask = cv2.resize(mask, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    mask = cv2.GaussianBlur(mask, (5, 5), 0)
    _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    return _pad(cv2.bitwise_not(mask))


def dark_ink_close(img: np.ndarray) -> np.ndarray:
    """dark_ink + a small closing to reconnect thin strokes broken by the noise-line removal."""
    mask = ink_mask(img, thr=125)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    mask = cv2.resize(mask, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    mask = cv2.GaussianBlur(mask, (5, 5), 0)
    _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    return _pad(cv2.bitwise_not(mask))


PREPROCESSORS: dict[str, Callable[[np.ndarray], np.ndarray]] = {
    "legacy": legacy,
    "otsu_upscaled": otsu_upscaled,
    "median_otsu_cc": median_otsu_cc,
    "adaptive_cc": adaptive_cc,
    "dark_ink": dark_ink,
    "dark_ink_close": dark_ink_close,
}
