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
IMAGES_DIR = Path("pages")
DIFF_PATH = Path("verification_comparison.txt")

MODEL_NAME = "gemini-2.5-pro"  # Use Pro for verification (better accuracy)
CHUNK_SIZE = 5  # Pages per chunk (with images, need smaller chunks)
REQUESTS_PER_MINUTE = 2  # Conservative for Pro tier

VERIFICATION_PROMPT = """You are verifying a handwritten document transcription.

You will receive:
1. An IMAGE of the original handwritten page
2. The TRANSCRIPTION of that page (from OCR)

Your task:
- Compare the transcription carefully with the handwritten image
- Correct any OCR errors you find
- Preserve the original wording and structure
- Do NOT paraphrase or rewrite sentences
- Do NOT add interpretations or extra content
- Preserve all Markdown formatting (headings, lists, tables, etc.)

Common OCR errors to watch for:
- Dropped small words ("the", "a", "of", etc.)
- Word substitutions (similar-looking words)
- Missing punctuation
- Incorrect capitalization
- Table formatting issues

If the transcription is already correct, return it unchanged.

Return ONLY the corrected Markdown. No explanations, no commentary."""


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------
def split_into_page_chunks(text, pages_per_chunk):
    """Split document into chunks by page markers."""
    page_pattern = r'^## Page (\d+)$'
    lines = text.split('\n')

    chunks = []
    current_chunk = []
    current_pages = []
    pages_in_chunk = 0

    for line in lines:
        match = re.match(page_pattern, line)
        if match:
            page_num = int(match.group(1))
            if pages_in_chunk >= pages_per_chunk and current_chunk:
                # Save chunk
                chunks.append({
                    'text': '\n'.join(current_chunk),
                    'pages': current_pages
                })
                current_chunk = [line]
                current_pages = [page_num]
                pages_in_chunk = 1
            else:
                current_chunk.append(line)
                current_pages.append(page_num)
                pages_in_chunk += 1
        else:
            current_chunk.append(line)

    # Add remaining content
    if current_chunk:
        chunks.append({
            'text': '\n'.join(current_chunk),
            'pages': current_pages
        })

    return chunks


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
    # Check for PDF (we'll extract images on-the-fly)
    pdf_path = Path("book.pdf")
    if not pdf_path.exists():
        print(f"Error: PDF not found: {pdf_path}")
        print("The PDF is required to extract page images for verification.")
        sys.exit(1)

    # Check for images directory, create if needed
    if not IMAGES_DIR.exists():
        print(f"Images directory not found. Will extract pages from PDF...")
        IMAGES_DIR.mkdir(exist_ok=True)
        extract_needed = True
    else:
        extract_needed = False

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

    print(f"\n{'='*60}")
    print(f"IMAGE VERIFICATION PIPELINE")
    print(f"{'='*60}")
    print(f"Input: {input_file}")
    print(f"Images: {IMAGES_DIR}")
    print(f"Model: {MODEL_NAME}")
    print(f"Chunk size: {CHUNK_SIZE} pages")
    print(f"{'='*60}\n")

    # Read input
    print(f"Reading transcription from {input_file}...")
    input_text = input_file.read_text(encoding='utf-8')

    # Split into chunks
    print(f"Splitting document into chunks...")
    chunks = split_into_page_chunks(input_text, CHUNK_SIZE)
    print(f"Total chunks: {len(chunks)}")

    # Process each chunk
    client = genai.Client(api_key=api_key)
    verified_chunks = []

    for i, chunk in enumerate(chunks, 1):
        pages = chunk['pages']
        text = chunk['text']

        print(f"\nChunk {i}/{len(chunks)} - Pages {pages[0]}-{pages[-1]}...")

        # Load images
        images = load_page_images(pages, IMAGES_DIR, pdf_path)
        if not images:
            print(f"  ⚠ No images found, using original text")
            verified_chunks.append(text)
            continue

        print(f"  Loaded {len(images)} images")

        # Rate limiting
        if i > 1:
            wait_time = 60 / REQUESTS_PER_MINUTE
            print(f"  Rate limiting: waiting {wait_time:.1f}s...")
            time.sleep(wait_time)

        # Verify with images
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Build content list: prompt + images + transcription
                contents = [VERIFICATION_PROMPT]

                for idx, img in enumerate(images):
                    contents.append(f"\n--- PAGE {pages[idx]} IMAGE ---")
                    contents.append(img)

                contents.append(f"\n\n--- TRANSCRIPTION TO VERIFY ---\n\n{text}")

                response = client.models.generate_content(
                    model=MODEL_NAME,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        temperature=0.1,  # Very low for faithful verification
                    ),
                )

                if response.text is None:
                    raise ValueError("API returned empty response")

                verified_text = response.text.strip()

                # Strip code fences
                verified_text = re.sub(r'^```(?:markdown)?\s*\n', '', verified_text)
                verified_text = re.sub(r'\n```\s*$', '', verified_text)

                verified_chunks.append(verified_text)
                print(f"  ✓ Verified ({len(verified_text)} chars)")
                break

            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"  ⚠ Retry {attempt + 1}/{max_retries} - Error: {e}")
                    time.sleep(5)
                else:
                    print(f"  ✗ Failed after {max_retries} attempts: {e}")
                    print(f"  Using original text as fallback...")
                    verified_chunks.append(text)

    # Merge chunks
    print(f"\nMerging {len(verified_chunks)} verified chunks...")
    verified_text = "\n\n".join(verified_chunks)

    # Write output
    print(f"Writing verified output to {OUTPUT_PATH}...")
    OUTPUT_PATH.write_text(verified_text, encoding='utf-8')

    # Create comparison
    print(f"Creating comparison file at {DIFF_PATH}...")
    comparison = create_comparison(input_text, verified_text)
    DIFF_PATH.write_text(comparison, encoding='utf-8')

    print(f"\n{'='*60}")
    print(f"✓ Verification complete!")
    print(f"{'='*60}")
    print(f"Original:   {input_file} ({len(input_text):,} chars)")
    print(f"Verified:   {OUTPUT_PATH} ({len(verified_text):,} chars)")
    print(f"Comparison: {DIFF_PATH}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
