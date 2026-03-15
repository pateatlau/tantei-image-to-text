"""
Image-Aware Verification Pipeline
===================================
Verifies and corrects OCR output by comparing with original page images.
This is the missing piece for achieving 97-98% accuracy.

Architecture:
    PDF → images → initial transcription (output.md)
                ↓
    image + transcription → verification → corrected output

Usage:
    python verify_with_images.py

Input:
    - output.md (or output_proofread.md)
    - pages/ directory with page images
Output:
    - output_verified.md

Dependencies:
    pip install google-generativeai pillow pdf2image
"""

import os
import sys
import re
import time
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image
from pdf2image import convert_from_path

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
INPUT_PATH = Path("output_proofread.md")
FALLBACK_PATH = Path("output.md")
OUTPUT_PATH = Path("output_verified.md")
PROGRESS_PATH = Path("_verify_progress.md")  # Incremental saves
IMAGES_DIR = Path("pages")
DIFF_PATH = Path("verification_comparison.txt")

MODEL_NAME = "gemini-2.5-flash"
REQUESTS_PER_MINUTE = 10  # Free tier: 15 RPM, stay under
API_TIMEOUT = 120  # seconds per request
PDF_PATH = Path("book.pdf")

VERIFICATION_PROMPT = """You are verifying a transcription of a handwritten page against the original image.

CRITICAL RULES:
1. You MUST preserve the EXACT structure of the transcription provided.
2. You MUST keep all "## Page N" markers exactly as they appear.
3. You MUST keep all Markdown formatting (# headings, - bullets, 1. numbered lists, | tables |).
4. You MUST NOT add, remove, or reorder any sections or headings.
5. You MUST NOT paraphrase, rewrite, or restructure any sentence.
6. You MUST NOT add commentary or explanations.

YOUR ONLY JOB: Compare each word in the transcription against the handwriting in the image and fix:
- Misspelled words (e.g., "gavernance" → "governance")
- Wrong words (where the OCR misread the handwriting)
- Missing words (small words like "the", "a", "of", "in" that the OCR dropped)
- Extra words (words the OCR hallucinated that are NOT in the handwriting)

If a line is already correct, return it UNCHANGED — same words, same formatting, same indentation.

Return ONLY the corrected transcription in Markdown. Nothing else."""


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------
def split_into_pages(text):
    """Split document into individual pages by page markers."""
    page_pattern = r'^## Page (\d+)$'
    lines = text.split('\n')

    pages = []
    current_page = []
    current_num = None

    for line in lines:
        match = re.match(page_pattern, line)
        if match:
            if current_page and current_num is not None:
                pages.append({
                    'text': '\n'.join(current_page),
                    'page_num': current_num
                })
            current_page = [line]
            current_num = int(match.group(1))
        else:
            current_page.append(line)

    if current_page and current_num is not None:
        pages.append({
            'text': '\n'.join(current_page),
            'page_num': current_num
        })

    return pages


def extract_pages_from_pdf(pdf_path, page_numbers, images_dir):
    """Extract specific pages from PDF as images."""
    print(f"  Extracting pages {page_numbers[0]}-{page_numbers[-1]} from PDF...")
    try:
        # Convert specific pages from PDF
        images = convert_from_path(
            pdf_path,
            dpi=300,
            first_page=page_numbers[0],
            last_page=page_numbers[-1]
        )

        # Save images for future use
        for idx, img in enumerate(images):
            page_num = page_numbers[idx]
            image_path = images_dir / f"page_{page_num:03d}.png"
            img.save(image_path, 'PNG')

        return images

    except Exception as e:
        print(f"  ⚠ Failed to extract pages: {e}")
        return []


def load_page_images(page_numbers, images_dir, pdf_path=None):
    """Load images for given page numbers."""
    images = []
    missing_pages = []

    # Try to load existing images first
    for page_num in page_numbers:
        image_path = images_dir / f"page_{page_num:03d}.png"
        if image_path.exists():
            try:
                img = Image.open(image_path)
                images.append(img)
            except Exception as e:
                print(f"  ⚠ Warning: Failed to load {image_path}: {e}")
                missing_pages.append(page_num)
        else:
            missing_pages.append(page_num)

    # If images are missing and PDF is available, extract them
    if missing_pages and pdf_path and pdf_path.exists():
        extracted = extract_pages_from_pdf(pdf_path, missing_pages, images_dir)
        images.extend(extracted)

    return images


def create_comparison(original, verified):
    """Create a comparison showing changes."""
    comparison_lines = []
    comparison_lines.append("=" * 80)
    comparison_lines.append("IMAGE VERIFICATION COMPARISON")
    comparison_lines.append("=" * 80)
    comparison_lines.append("")
    comparison_lines.append("This shows changes made during image-aware verification.")
    comparison_lines.append("")
    comparison_lines.append("=" * 80)
    comparison_lines.append("")

    orig_lines = original.split('\n')
    verify_lines = verified.split('\n')

    max_lines = max(len(orig_lines), len(verify_lines))
    changes_found = 0

    for i in range(max_lines):
        orig_line = orig_lines[i] if i < len(orig_lines) else ""
        verify_line = verify_lines[i] if i < len(verify_lines) else ""

        if orig_line.strip() != verify_line.strip():
            changes_found += 1
            comparison_lines.append(f"Line {i+1} - CHANGED:")
            comparison_lines.append(f"  BEFORE: {orig_line}")
            comparison_lines.append(f"  AFTER:  {verify_line}")
            comparison_lines.append("")

    comparison_lines.append("=" * 80)
    comparison_lines.append(f"Total changes detected: {changes_found} lines")
    comparison_lines.append("=" * 80)

    return '\n'.join(comparison_lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    if not PDF_PATH.exists():
        print(f"Error: PDF not found: {PDF_PATH}")
        sys.exit(1)

    # Create images directory if needed
    IMAGES_DIR.mkdir(exist_ok=True)

    # Determine input file
    if INPUT_PATH.exists():
        input_file = INPUT_PATH
        print(f"Using proofread version: {input_file}")
    elif FALLBACK_PATH.exists():
        input_file = FALLBACK_PATH
        print(f"Using original OCR: {input_file}")
    else:
        print(f"Error: No input file found.")
        sys.exit(1)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY is not set.")
        sys.exit(1)

    # Read input
    print(f"Reading transcription from {input_file}...")
    input_text = input_file.read_text(encoding='utf-8')

    # Split into individual pages
    print(f"Splitting document into pages...")
    pages = split_into_pages(input_text)
    print(f"Total pages: {len(pages)}")

    print(f"\n{'='*60}")
    print(f"IMAGE VERIFICATION PIPELINE")
    print(f"{'='*60}")
    print(f"Input:  {input_file}")
    print(f"Pages:  {len(pages)}")
    print(f"Model:  {MODEL_NAME}")
    print(f"Output: {OUTPUT_PATH}")
    print(f"{'='*60}\n")

    # Check for resume from progress file
    client = genai.Client(api_key=api_key)
    verified_pages = []
    start_idx = 0

    if PROGRESS_PATH.exists():
        progress_text = PROGRESS_PATH.read_text(encoding='utf-8')
        # Count how many pages we already have
        existing_pages = re.findall(r'^## Page \d+', progress_text, re.MULTILINE)
        if existing_pages:
            start_idx = len(existing_pages)
            # Re-split progress into page chunks
            for page in pages[:start_idx]:
                pattern = rf'(## Page {page["page_num"]}\n.*?)(?=\n## Page \d+|\Z)'
                match = re.search(pattern, progress_text, re.DOTALL)
                if match:
                    verified_pages.append(match.group(1).strip())
                else:
                    verified_pages.append(page['text'])
            print(f"Resuming from page {start_idx + 1} (found {start_idx} pages in progress file)")

    # Process each page individually
    for i, page in enumerate(pages):
        if i < start_idx:
            continue

        page_num = page['page_num']
        page_text = page['text']

        print(f"Page {page_num} ({i+1}/{len(pages)})...", end=" ", flush=True)

        # Rate limiting
        if i > start_idx:
            wait_time = 60 / REQUESTS_PER_MINUTE
            time.sleep(wait_time)

        # Load page image from PDF
        image_path = IMAGES_DIR / f"page_{page_num:03d}.png"
        if not image_path.exists():
            try:
                imgs = convert_from_path(PDF_PATH, dpi=300,
                                         first_page=page_num, last_page=page_num)
                imgs[0].save(image_path, 'PNG')
            except Exception as e:
                print(f"⚠ Image extraction failed: {e}, using original")
                verified_pages.append(page_text)
                continue

        try:
            image = Image.open(image_path)
        except Exception as e:
            print(f"⚠ Image load failed: {e}, using original")
            verified_pages.append(page_text)
            continue

        # Verify with image
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=MODEL_NAME,
                    contents=[
                        VERIFICATION_PROMPT,
                        image,
                        f"\n--- TRANSCRIPTION TO VERIFY ---\n\n{page_text}"
                    ],
                    config=types.GenerateContentConfig(
                        temperature=0.0,
                        http_options={'timeout': API_TIMEOUT * 1000},
                    ),
                )

                if response.text is None:
                    raise ValueError("Empty response")

                verified_text = response.text.strip()
                verified_text = re.sub(r'^```(?:markdown)?\s*\n', '', verified_text)
                verified_text = re.sub(r'\n```\s*$', '', verified_text)

                # Sanity check: reject if output is way too large (hallucination)
                if len(verified_text) > len(page_text) * 3:
                    print(f"⚠ output too large ({len(verified_text)} chars), using original")
                    verified_pages.append(page_text)
                else:
                    verified_pages.append(verified_text)
                    print(f"✓ ({len(verified_text)} chars)")
                break

            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"⚠ retry {attempt+1}...", end=" ", flush=True)
                    time.sleep(10)
                else:
                    print(f"✗ failed, using original")
                    verified_pages.append(page_text)

        # Save progress incrementally every 10 pages
        if (i + 1) % 10 == 0:
            progress = "\n\n".join(verified_pages)
            PROGRESS_PATH.write_text(progress, encoding='utf-8')
            print(f"  [progress saved: {i+1}/{len(pages)} pages]")

    # Merge pages
    print(f"\nMerging {len(verified_pages)} verified pages...")
    verified_text = "\n\n".join(verified_pages)

    print(f"Writing verified output to {OUTPUT_PATH}...")
    OUTPUT_PATH.write_text(verified_text, encoding='utf-8')

    # Create comparison
    print(f"Creating comparison file at {DIFF_PATH}...")
    comparison = create_comparison(input_text, verified_text)
    DIFF_PATH.write_text(comparison, encoding='utf-8')

    # Clean up progress file
    if PROGRESS_PATH.exists():
        PROGRESS_PATH.unlink()

    print(f"\n{'='*60}")
    print(f"✓ Verification complete!")
    print(f"{'='*60}")
    print(f"Original:   {input_file} ({len(input_text):,} chars)")
    print(f"Verified:   {OUTPUT_PATH} ({len(verified_text):,} chars)")
    print(f"Comparison: {DIFF_PATH}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
