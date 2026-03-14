"""
Handwritten PDF → Markdown OCR Pipeline
========================================
Converts a handwritten PDF into structured Markdown using Google Gemini 2.5 Flash.

Gemini is a large multimodal model that reads handwriting with high accuracy —
far better than traditional OCR APIs. Free tier: 250 requests/day.

Usage:
    export GEMINI_API_KEY="your-api-key"
    python ocr_book.py

Dependencies:
    pip install google-genai pdf2image pillow tqdm python-dotenv
    brew install poppler
"""

import os
import sys
import time
import shutil
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image
from pdf2image import convert_from_path, pdfinfo_from_path
from tqdm import tqdm

load_dotenv()

try:
    from google import genai
except ImportError:
    print("Error: google-genai is not installed.")
    print("Install with: pip install -U google-genai")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PDF_PATH = Path("book.pdf")
OUTPUT_PATH = Path("output.md")
OCR_DPI = 300
PAGE_CHUNK_SIZE = 5
MODEL_NAME = "gemini-2.5-flash"
MAX_PAGES = 5                    # Set to None for all pages
REQUESTS_PER_MINUTE = 9         # Stay under free tier limit of 10 RPM


# ---------------------------------------------------------------------------
# OCR Prompt
# ---------------------------------------------------------------------------
OCR_PROMPT = """You are an expert OCR system specializing in handwritten documents about Indian public administration, civil services, ethics, and governance.

Extract ALL handwritten text from this image exactly as written.

DOMAIN CONTEXT (use this to resolve ambiguous handwriting):
This document covers: Ethics in Administration, Probity, Governance, Civil Services, Public Administration, Indian Administrative Service (IAS), Indian Police Service (IPS), Indian Forest Service (IFS), Accountability, Transparency, E-governance, RTI (Right to Information), Citizen Charters, Social Audit, Sevottam Model, KSRTC, NERCORMP, SHGs (Self Help Groups).

TRANSCRIPTION RULES:
- Read every word carefully. Do NOT guess or hallucinate — if a word is unclear, transcribe your best reading of it
- Do NOT duplicate words or phrases — each word should appear exactly once
- Preserve abbreviations as written (e.g., "CS" for Civil Services, "WF" for Way Forward, "PA" for Public Administration, "wc" for work culture)
- Indian proper names: read carefully — common names include Shenoy, Sabharwal, Pragyan Das, Narahari, Yadav, Shaikh
- Do NOT add words that aren't in the image

MARKDOWN FORMATTING:
- # for main headings/titles (text in boxes, large underlined text, ALL CAPS titles)
- ## for section headings (Roman numeral prefixed: I., II., III., IV., V., VI., VII.)
- Numbered lists (1. 2. 3.) for circled numbers ①②③ or numbered points
- Bullet lists (- ) for sub-points marked with circles, arrows, dashes, or dots
- Markdown tables (| col1 | col2 |) if tabular content is present
- Indented sub-items (2 spaces) under their parent item
- If text is crossed out, skip it
- If arrows point to inserted text, incorporate it in the logical reading position

OUTPUT: Only the extracted text in Markdown. No commentary, no explanation, no code fences."""


# ---------------------------------------------------------------------------
# Environment checks
# ---------------------------------------------------------------------------
def validate_environment() -> None:
    if not PDF_PATH.exists():
        print(f"Error: Input PDF not found: {PDF_PATH}")
        sys.exit(1)
    if shutil.which("pdfinfo") is None:
        print("Error: Poppler is not installed. Install with: brew install poppler")
        sys.exit(1)


def create_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY is not set.")
        print("Get a key from: https://aistudio.google.com/apikey")
        print('Then run: export GEMINI_API_KEY="your-key"')
        sys.exit(1)
    return genai.Client(api_key=api_key)


# ---------------------------------------------------------------------------
# OCR a single page via Gemini
# ---------------------------------------------------------------------------
def ocr_page(client: genai.Client, image: Image.Image) -> str:
    """Send a page image to Gemini and get Markdown text back."""
    from google.genai import types

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[OCR_PROMPT, image],
        config=types.GenerateContentConfig(
            temperature=0,          # Deterministic — no creative guessing
        ),
    )

    text = response.text.strip()
    text = postprocess(text)
    return text


def postprocess(text: str) -> str:
    """Clean up common Gemini OCR artifacts."""
    import re

    # Strip code fences if the model wraps output in them
    text = re.sub(r'^```(?:markdown)?\s*\n', '', text)
    text = re.sub(r'\n```\s*$', '', text)

    # Remove duplicate consecutive lines (exact duplicates)
    lines = text.split('\n')
    deduped = [lines[0]] if lines else []
    for line in lines[1:]:
        if line.strip() != deduped[-1].strip():
            deduped.append(line)
    text = '\n'.join(deduped)

    return text


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
def rate_limit_delay(page_index: int, start_time: float) -> None:
    """
    Ensure we don't exceed the free tier RPM limit.
    Sleeps if we're sending requests too fast.
    """
    if page_index == 0:
        return
    elapsed = time.time() - start_time
    expected_elapsed = page_index * (60.0 / REQUESTS_PER_MINUTE)
    if elapsed < expected_elapsed:
        sleep_time = expected_elapsed - elapsed
        time.sleep(sleep_time)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def main() -> None:
    validate_environment()
    client = create_client()

    pdf_info = pdfinfo_from_path(str(PDF_PATH))
    total_pages = int(pdf_info["Pages"])
    if MAX_PAGES is not None:
        total_pages = min(total_pages, MAX_PAGES)
    print(f"PDF has {total_pages} page(s) to process.")
    print(f"Using model: {MODEL_NAME}")

    results = {}
    progress = tqdm(total=total_pages, desc="OCR pages", unit="page")
    global_page_index = 0
    start_time = time.time()

    for chunk_start in range(1, total_pages + 1, PAGE_CHUNK_SIZE):
        chunk_end = min(chunk_start + PAGE_CHUNK_SIZE - 1, total_pages)

        try:
            images = convert_from_path(
                str(PDF_PATH),
                dpi=OCR_DPI,
                first_page=chunk_start,
                last_page=chunk_end,
            )
        except Exception as e:
            print(f"\nError converting pages {chunk_start}-{chunk_end}: {e}")
            for pn in range(chunk_start, chunk_end + 1):
                results[pn] = f"*[PDF conversion error: {e}]*"
                progress.update(1)
                global_page_index += 1
            continue

        for offset, raw_image in enumerate(images):
            page_number = chunk_start + offset

            # Rate limiting to stay within free tier
            rate_limit_delay(global_page_index, start_time)

            try:
                text = ocr_page(client, raw_image)
                results[page_number] = text
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "RATE_LIMIT" in error_msg.upper():
                    # Hit rate limit — wait and retry once
                    print(f"\nRate limited on page {page_number}, waiting 60s...")
                    time.sleep(60)
                    try:
                        text = ocr_page(client, raw_image)
                        results[page_number] = text
                    except Exception as e2:
                        print(f"\nRetry failed on page {page_number}: {e2}")
                        results[page_number] = f"*[OCR error: {e2}]*"
                else:
                    print(f"\nError on page {page_number}: {e}")
                    results[page_number] = f"*[OCR error: {e}]*"

            progress.update(1)
            global_page_index += 1

        del images

    progress.close()

    # Write output
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for page_num in range(1, total_pages + 1):
            f.write(f"## Page {page_num}\n\n")
            text = results.get(page_num, "*[Missing]*")
            f.write(text.strip() + "\n\n")

    elapsed = time.time() - start_time
    print(f"\nDone. Output saved to {OUTPUT_PATH}")
    print(f"Total time: {elapsed:.0f}s ({elapsed/total_pages:.1f}s per page)")


if __name__ == "__main__":
    main()
