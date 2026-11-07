import io
import os
import random
import string
import time
from typing import Optional, Any
from pathlib import Path

import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont
import pytesseract

from app.config import settings

# Configure Tesseract binary path
if Path(settings.TESSERACT_CMD).exists():
    pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD


def _get_captcha_font(size: int = 34) -> ImageFont.ImageFont:
    """Load standard system TTF font with fallback."""
    windows_font = Path(r"C:\Windows\Fonts\arial.ttf")
    if windows_font.exists():
        try:
            return ImageFont.truetype(str(windows_font), size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


def generate_synthetic_captcha(
    text: Optional[str] = None,
    length: int = 5,
    width: int = 240,
    height: int = 80
) -> tuple[bytes, str]:
    """
    Generate a synthetic text CAPTCHA image with geometric noise, lines, and distortion.
    Returns (png_bytes, ground_truth_text).
    """
    if not text:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        text = "".join(random.choice(alphabet) for _ in range(length))

    font = _get_captcha_font(size=34)

    # Light background
    bg_color = (random.randint(235, 255), random.randint(235, 255), random.randint(235, 255))
    image = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(image)

    # 1. Background noise lines
    for _ in range(random.randint(3, 5)):
        line_color = (random.randint(140, 200), random.randint(140, 200), random.randint(140, 200))
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(0, width)
        y2 = random.randint(0, height)
        draw.line([(x1, y1), (x2, y2)], fill=line_color, width=random.randint(1, 2))

    # 2. Render characters with rotation
    char_spacing = (width - 40) // len(text)
    for i, char in enumerate(text):
        char_img = Image.new("RGBA", (50, 60), (255, 255, 255, 0))
        char_draw = ImageDraw.Draw(char_img)
        char_color = (random.randint(20, 90), random.randint(20, 90), random.randint(20, 90), 255)

        char_draw.text((8, 6), char, font=font, fill=char_color)

        angle = random.randint(-18, 18)
        rotated_char = char_img.rotate(angle, expand=True, resample=Image.Resampling.BILINEAR)

        x_pos = 15 + i * char_spacing + random.randint(-2, 2)
        y_pos = random.randint(8, 18)
        image.paste(rotated_char, (x_pos, y_pos), rotated_char)

    # 3. Add salt-and-pepper noise dots
    for _ in range(random.randint(100, 180)):
        dot_color = (random.randint(80, 180), random.randint(80, 180), random.randint(80, 180))
        dx = random.randint(0, width - 1)
        dy = random.randint(0, height - 1)
        draw.point((dx, dy), fill=dot_color)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue(), text


def preprocess_captcha_image(image_bytes: bytes) -> tuple[np.ndarray, bytes]:
    """
    OpenCV preprocessing pipeline:
    Grayscale -> Bilateral Filter -> Otsu Adaptive Thresholding -> Morphological Noise Removal
    """
    np_arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    denoised = cv2.bilateralFilter(gray, d=5, sigmaColor=50, sigmaSpace=50)
    _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    opened = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
    clean = cv2.bitwise_not(opened)

    _, buffer = cv2.imencode(".png", clean)
    return clean, buffer.tobytes()


def run_ocr(clean_image: np.ndarray) -> dict[str, Any]:
    """Run Tesseract OCR on preprocessed image."""
    start_time = time.perf_counter()
    custom_config = r'--oem 3 --psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

    try:
        raw_text = pytesseract.image_to_string(clean_image, config=custom_config)
        cleaned_text = "".join(c for c in raw_text if c.isalnum()).upper()

        data = pytesseract.image_to_data(clean_image, config=custom_config, output_type=pytesseract.Output.DICT)
        confs = [int(c) for c in data.get("conf", []) if str(c).isdigit() and int(c) >= 0]
        avg_confidence = round(sum(confs) / len(confs), 1) if confs else 0.0

        duration_ms = (time.perf_counter() - start_time) * 1000

        return {
            "success": True,
            "predicted_text": cleaned_text,
            "confidence": avg_confidence,
            "ocr_duration_ms": round(duration_ms, 2),
            "ocr_engine": "Tesseract OCR v5.5.0",
        }
    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        return {
            "success": False,
            "predicted_text": "",
            "confidence": 0.0,
            "ocr_duration_ms": round(duration_ms, 2),
            "error": str(e),
            "ocr_engine": "Tesseract OCR v5.5.0",
        }


def benchmark_synthetic_ocr(samples: int = 5) -> dict[str, Any]:
    """
    Evaluate OCR accuracy against a controlled synthetic dataset.
    Returns per-sample results, overall accuracy, and limitation analysis.
    """
    results = []
    exact_matches = 0
    total_chars = 0
    correct_chars = 0
    total_time = 0.0

    for i in range(samples):
        img_bytes, ground_truth = generate_synthetic_captcha(length=5)
        clean_img, _ = preprocess_captcha_image(img_bytes)
        ocr_result = run_ocr(clean_img)

        pred = ocr_result.get("predicted_text", "")
        is_exact = (pred == ground_truth)
        if is_exact:
            exact_matches += 1

        min_len = min(len(pred), len(ground_truth))
        sample_correct_chars = sum(1 for c1, c2 in zip(pred[:min_len], ground_truth[:min_len]) if c1 == c2)
        correct_chars += sample_correct_chars
        total_chars += max(len(pred), len(ground_truth))

        duration = ocr_result.get("ocr_duration_ms", 0.0)
        total_time += duration

        results.append({
            "sample_index": i + 1,
            "ground_truth": ground_truth,
            "predicted_text": pred,
            "exact_match": is_exact,
            "confidence": ocr_result.get("confidence", 0.0),
            "duration_ms": duration,
        })

    char_accuracy = round((correct_chars / total_chars * 100), 1) if total_chars > 0 else 0.0
    exact_rate = round((exact_matches / samples * 100), 1) if samples > 0 else 0.0

    return {
        "total_samples": samples,
        "exact_match_rate_pct": exact_rate,
        "character_accuracy_pct": char_accuracy,
        "average_duration_ms": round(total_time / samples, 2) if samples > 0 else 0.0,
        "sample_evaluations": results,
        "limitations_analysis": (
            "1. Modern CAPTCHAs (reCAPTCHA v2/v3, Turnstile, hCaptcha) do not rely on static distorted text; "
            "they employ behavioral biometric telemetry, hardware fingerprinting, proof-of-work challenges, "
            "and interactive 3x3 semantic classification puzzles that standard OCR cannot solve.\n"
            "2. Traditional OCR engines degrade sharply with font shearing, overlapping glyphs, and high-frequency "
            "background noise lines.\n"
            "3. Synthetic OCR is strictly demonstrated here for legacy distortion benchmark analysis."
        ),
    }
