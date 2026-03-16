"""
Handwritten PDF → Markdown OCR Pipeline (Dual OCR + Disagreement Resolution)
==============================================================================
Converts a handwritten PDF into structured Markdown using Google Gemini 2.5 Flash.

Two independent OCR passes with different prompts are run on each page.
A disagreement resolver compares both results against the original image
to produce the most accurate transcription.

Gemini is a large multimodal model that reads handwriting with high accuracy —
far better than traditional OCR APIs. Free tier: 250 requests/day.

Usage:
    export GEMINI_API_KEY="your-api-key"
    python ocr_book.py

Dependencies:
    pip install google-genai pdf2image pillow tqdm python-dotenv opencv-python-headless
    brew install poppler
"""

import os
import sys
import time
import shutil
from pathlib import Path

import cv2
import numpy as np
from dotenv import load_dotenv
from PIL import Image
from pdf2image import convert_from_path, pdfinfo_from_path
from tqdm import tqdm

load_dotenv()

try:
    from google import genai
    from google.genai import types
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
MAX_PAGES = None                   # Set to None for all pages
REQUESTS_PER_MINUTE = 9         # Stay under free tier limit of 10 RPM
ENABLE_DUAL_OCR = True           # Set to False to use single-pass OCR (faster)
ENABLE_PREPROCESSING = True      # Set to False to skip image preprocessing


# ---------------------------------------------------------------------------
# Named Entity Dictionary
# ---------------------------------------------------------------------------
ENTITY_CORRECTIONS = {
    # Proper names
    "Sabharval": "Sabharwal", "Sabhrawal": "Sabharwal", "Sabharawal": "Sabharwal",
    "Shenay": "Shenoy", "Shenoi": "Shenoy",
    "Pragyan": "Pragyan", "Narahari": "Narahari",
    # Domain terms
    "Sevottom": "Sevottam", "Sevottm": "Sevottam",
    "NERCORMP": "NERCORMP", "NERCOMP": "NERCORMP",
    "gavernance": "governance", "Gavernance": "Governance",
    "goverance": "governance", "Goverance": "Governance",
    "adminstration": "administration", "Adminstration": "Administration",
    "adminsitration": "administration", "Adminsitration": "Administration",
    "accountablity": "accountability", "Accountablity": "Accountability",
    "transparancy": "transparency", "Transparancy": "Transparency",
    "bureacracy": "bureaucracy", "Bureacracy": "Bureaucracy",
    "bureauracy": "bureaucracy", "Bureauracy": "Bureaucracy",
    "probity": "probity", "Probily": "Probity",
    "citizan": "citizen", "Citizan": "Citizen",
    "e-goverance": "e-governance", "E-goverance": "E-governance",
    "e-governace": "e-governance", "E-governace": "E-governance",
}


# ---------------------------------------------------------------------------
# OCR Prompts (Dual OCR Strategy)
# ---------------------------------------------------------------------------
OCR_PROMPT_A = """You are an expert OCR system specializing in handwritten documents about Indian public administration, civil services, ethics, and governance.

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
- Numbered lists (1. 2. 3.) for circled numbers or numbered points
- Bullet lists (- ) for sub-points marked with circles, arrows, dashes, or dots
- Markdown tables (| col1 | col2 |) if tabular content is present
- Indented sub-items (2 spaces) under their parent item
- If text is crossed out, skip it
- If arrows point to inserted text, incorporate it in the logical reading position

OUTPUT: Only the extracted text in Markdown. No commentary, no explanation, no code fences."""


OCR_PROMPT_B = """Carefully read the handwriting in this image and extract the complete text.

This is a handwritten document about Indian civil services, ethics, public administration, governance, and probity.

RULES:
- Focus on exact letter recognition — read each word character by character
- Preserve capitalization exactly as written
- Preserve all punctuation marks
- Preserve the document structure: headings, numbered lists, bullet points, tables
- Do NOT paraphrase or reword anything — transcribe exactly what is written
- Do NOT add any text that is not visible in the image
- Do NOT duplicate any content

KNOWN TERMS (use to disambiguate unclear handwriting):
Sabharwal, Shenoy, Pragyan Das, Narahari, Sevottam Model, NERCORMP, KSRTC, SHGs, RTI, IAS, IPS, IFS, E-governance, Citizen Charters, Social Audit, Accountability, Transparency, Probity, Governance

FORMAT:
- Use # for main titles and ## for section headings
- Use numbered lists (1. 2. 3.) for numbered points
- Use bullet lists (- ) for sub-points
- Use Markdown tables for any tabular content
- Use 2-space indentation for nested items

OUTPUT: Only the extracted Markdown text. No explanations or code fences."""


# ---------------------------------------------------------------------------
# Disagreement Resolver Prompt
# ---------------------------------------------------------------------------
RESOLVER_PROMPT = """You are verifying OCR output for a handwritten document.

Two independent transcriptions of the same page are provided below. Compare both transcriptions against the handwriting in the image.

Return the most accurate transcription by:
1. Choosing the correct reading where the two versions disagree
2. Fixing any errors that both versions got wrong (by checking the image)
3. Keeping the formatting and structure from whichever version is more faithful

RULES:
- Preserve wording exactly as written in the handwriting
- Correct OCR mistakes only — do not paraphrase
- Preserve headings, lists, and tables
- Do not add content that is not in the image
- Do not duplicate any text

Output only the final corrected Markdown. No commentary, no code fences.

--- TRANSCRIPTION A ---

{text_a}

--- TRANSCRIPTION B ---

{text_b}"""


# Legacy single-pass prompt (used when ENABLE_DUAL_OCR=False)
OCR_PROMPT = OCR_PROMPT_A


# ---------------------------------------------------------------------------
# Image Preprocessing
# ---------------------------------------------------------------------------
def preprocess_image(pil_image: Image.Image) -> Image.Image:
    """Apply light preprocessing to improve OCR consistency.

    Steps:
    1. Convert to grayscale
    2. Apply small Gaussian blur to reduce noise
    3. Slight upscale (1.3x) for better character recognition
    """
    img_array = np.array(pil_image)

    # Convert to grayscale
    if len(img_array.shape) == 3:
        img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)

    # Apply small Gaussian blur
    img_array = cv2.GaussianBlur(img_array, (3, 3), 0)

    # Slight upscale (1.3x)
    img_array = cv2.resize(img_array, None, fx=1.3, fy=1.3, interpolation=cv2.INTER_CUBIC)

    # Convert back to PIL Image (grayscale)
    return Image.fromarray(img_array)


# ---------------------------------------------------------------------------
# Named Entity Correction
# ---------------------------------------------------------------------------
def correct_entities(text: str) -> str:
    """Fix common OCR misspellings of known proper nouns and domain terms."""
    for wrong, correct in ENTITY_CORRECTIONS.items():
        text = text.replace(wrong, correct)
    return text


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
def ocr_page(client: genai.Client, image: Image.Image, prompt: str = OCR_PROMPT_A) -> str:
    """Send a page image to Gemini and get Markdown text back."""
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[prompt, image],
        config=types.GenerateContentConfig(
            temperature=0,
        ),
    )

    text = response.text.strip()
    text = postprocess(text)
    return text


def resolve_disagreements(client: genai.Client, image: Image.Image, text_a: str, text_b: str) -> str:
    """Send both OCR results + image to Gemini to pick the best reading."""
    prompt = RESOLVER_PROMPT.format(text_a=text_a, text_b=text_b)

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[prompt, image],
        config=types.GenerateContentConfig(
            temperature=0,
        ),
    )

    text = response.text.strip()
    text = postprocess(text)
    return text


def ocr_page_dual(client: genai.Client, image: Image.Image) -> str:
    """Run dual OCR passes and resolve disagreements."""
    text_a = ocr_page(client, image, OCR_PROMPT_A)
    text_b = ocr_page(client, image, OCR_PROMPT_B)

    # If both are identical, no need to resolve
    if text_a.strip() == text_b.strip():
        return text_a

    # Resolve disagreements using the image
    resolved = resolve_disagreements(client, image, text_a, text_b)
    return resolved


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

    # Named entity correction
    text = correct_entities(text)

    return text


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
def rate_limit_delay(page_index: int, start_time: float, requests_per_page: int = 1) -> None:
    """
    Ensure we don't exceed the free tier RPM limit.
    Sleeps if we're sending requests too fast.
    requests_per_page: how many API calls per page (1 for single, 3 for dual OCR)
    """
    if page_index == 0:
        return
    total_requests = page_index * requests_per_page
    elapsed = time.time() - start_time
    expected_elapsed = total_requests * (60.0 / REQUESTS_PER_MINUTE)
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

    mode = "dual OCR + resolver" if ENABLE_DUAL_OCR else "single OCR"
    requests_per_page = 3 if ENABLE_DUAL_OCR else 1

    print(f"PDF has {total_pages} page(s) to process.")
    print(f"Using model: {MODEL_NAME}")
    print(f"Mode: {mode} ({requests_per_page} API calls/page)")
    print(f"Image preprocessing: {'enabled' if ENABLE_PREPROCESSING else 'disabled'}")

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
            rate_limit_delay(global_page_index, start_time, requests_per_page)

            # Optional image preprocessing
            if ENABLE_PREPROCESSING:
                processed_image = preprocess_image(raw_image)
            else:
                processed_image = raw_image

            try:
                if ENABLE_DUAL_OCR:
                    text = ocr_page_dual(client, processed_image)
                else:
                    text = ocr_page(client, processed_image)
                results[page_number] = text
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "RATE_LIMIT" in error_msg.upper():
                    # Hit rate limit — wait and retry once
                    print(f"\nRate limited on page {page_number}, waiting 60s...")
                    time.sleep(60)
                    try:
                        if ENABLE_DUAL_OCR:
                            text = ocr_page_dual(client, processed_image)
                        else:
                            text = ocr_page(client, processed_image)
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
