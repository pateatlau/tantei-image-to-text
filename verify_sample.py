"""
Sample Image Verification
===========================
Tests image verification on a small sample (5 pages) to evaluate quality improvement.

Usage:
    python verify_sample.py

This will verify pages 1-5 and show the improvements.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image
from pdf2image import convert_from_path
import re

load_dotenv()

# Configuration
PDF_PATH = Path("book.pdf")
INPUT_PATH = Path("output_proofread.md")
SAMPLE_PAGES = [1, 2, 3, 4, 5]  # Test on first 5 pages
MODEL_NAME = "gemini-2.5-pro"

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


def extract_page_text(markdown_text, page_num):
    """Extract text for a specific page from markdown."""
    pattern = rf'## Page {page_num}\n\n(.*?)(?=\n## Page \d+|\Z)'
    match = re.search(pattern, markdown_text, re.DOTALL)
    if match:
        return f"## Page {page_num}\n\n{match.group(1).strip()}"
    return None


def main():
    if not PDF_PATH.exists():
        print(f"Error: PDF not found: {PDF_PATH}")
        sys.exit(1)

    if not INPUT_PATH.exists():
        print(f"Error: Input file not found: {INPUT_PATH}")
        sys.exit(1)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY is not set.")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"SAMPLE IMAGE VERIFICATION TEST")
    print(f"{'='*60}")
    print(f"Testing on pages: {SAMPLE_PAGES}")
    print(f"Model: {MODEL_NAME}")
    print(f"{'='*60}\n")

    # Read input markdown
    print(f"Reading transcription...")
    markdown_text = INPUT_PATH.read_text(encoding='utf-8')

    # Extract and verify each sample page
    client = genai.Client(api_key=api_key)

    for page_num in SAMPLE_PAGES:
        print(f"\n--- Page {page_num} ---")

        # Extract page text
        page_text = extract_page_text(markdown_text, page_num)
        if not page_text:
            print(f"  ⚠ Page {page_num} not found in markdown")
            continue

        print(f"  Original text length: {len(page_text)} chars")

        # Extract page image from PDF
        print(f"  Extracting page from PDF...")
        try:
            images = convert_from_path(
                PDF_PATH,
                dpi=300,
                first_page=page_num,
                last_page=page_num
            )
            if not images:
                print(f"  ⚠ Failed to extract image")
                continue

            image = images[0]
            print(f"  ✓ Image loaded ({image.size[0]}x{image.size[1]})")

        except Exception as e:
            print(f"  ⚠ Error extracting image: {e}")
            continue

        # Verify with Gemini Pro
        print(f"  Verifying with {MODEL_NAME}...")
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=[
                    VERIFICATION_PROMPT,
                    f"\n--- PAGE {page_num} IMAGE ---",
                    image,
                    f"\n\n--- TRANSCRIPTION TO VERIFY ---\n\n{page_text}"
                ],
                config=types.GenerateContentConfig(
                    temperature=0.1,
                ),
            )

            if response.text is None:
                print(f"  ⚠ No response from API")
                continue

            verified_text = response.text.strip()

            # Strip code fences
            verified_text = re.sub(r'^```(?:markdown)?\s*\n', '', verified_text)
            verified_text = re.sub(r'\n```\s*$', '', verified_text)

            print(f"  ✓ Verified text length: {len(verified_text)} chars")

            # Show differences
            if page_text.strip() != verified_text.strip():
                print(f"\n  CHANGES DETECTED:")
                orig_lines = page_text.split('\n')
                verify_lines = verified_text.split('\n')

                changes = 0
                for i, (orig, verify) in enumerate(zip(orig_lines, verify_lines)):
                    if orig.strip() != verify.strip():
                        changes += 1
                        if changes <= 5:  # Show first 5 changes
                            print(f"    Line {i+1}:")
                            print(f"      BEFORE: {orig[:70]}")
                            print(f"      AFTER:  {verify[:70]}")

                if changes > 5:
                    print(f"    ... and {changes - 5} more changes")

                print(f"\n  Total lines changed: {changes}")
            else:
                print(f"  ✓ No changes needed (transcription was already correct)")

        except Exception as e:
            print(f"  ⚠ Verification error: {e}")
            continue

    print(f"\n{'='*60}")
    print(f"Sample verification complete!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
