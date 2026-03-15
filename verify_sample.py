"""
Quick sample test for image verification (5 pages).
Tests the refined prompt before committing to a full 104-page run.
"""

import os
import sys
import re
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image
from pdf2image import convert_from_path

load_dotenv()

PDF_PATH = Path("book.pdf")
INPUT_PATH = Path("output_proofread.md")
IMAGES_DIR = Path("pages")
MODEL_NAME = "gemini-2.5-flash"
SAMPLE_PAGES = [1, 2, 3, 4, 5]

# Import the prompt from the main script
from verify_with_images import VERIFICATION_PROMPT


def extract_page_text(markdown_text, page_num):
    """Extract text for a specific page."""
    pattern = rf'(## Page {page_num}\n.*?)(?=\n## Page \d+|\Z)'
    match = re.search(pattern, markdown_text, re.DOTALL)
    return match.group(1).strip() if match else None


def main():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY is not set.")
        sys.exit(1)

    IMAGES_DIR.mkdir(exist_ok=True)
    markdown_text = INPUT_PATH.read_text(encoding='utf-8')
    client = genai.Client(api_key=api_key)

    print(f"{'='*60}")
    print(f"SAMPLE VERIFICATION TEST (pages {SAMPLE_PAGES})")
    print(f"Model: {MODEL_NAME}")
    print(f"{'='*60}\n")

    for page_num in SAMPLE_PAGES:
        print(f"--- Page {page_num} ---")

        page_text = extract_page_text(markdown_text, page_num)
        if not page_text:
            print(f"  ⚠ Not found in markdown\n")
            continue

        # Extract image
        image_path = IMAGES_DIR / f"page_{page_num:03d}.png"
        if not image_path.exists():
            imgs = convert_from_path(PDF_PATH, dpi=300,
                                     first_page=page_num, last_page=page_num)
            imgs[0].save(image_path, 'PNG')

        image = Image.open(image_path)

        # Verify
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                VERIFICATION_PROMPT,
                image,
                f"\n--- TRANSCRIPTION TO VERIFY ---\n\n{page_text}"
            ],
            config=types.GenerateContentConfig(temperature=0.0),
        )

        verified = response.text.strip()
        verified = re.sub(r'^```(?:markdown)?\s*\n', '', verified)
        verified = re.sub(r'\n```\s*$', '', verified)

        # Check structural preservation
        has_page_marker = f"## Page {page_num}" in verified
        orig_lines = page_text.split('\n')
        veri_lines = verified.split('\n')

        print(f"  Page marker preserved: {'✅' if has_page_marker else '❌'}")
        print(f"  Lines: {len(orig_lines)} → {len(veri_lines)}")

        # Show actual changes (word-level)
        changes = 0
        for j, (orig, veri) in enumerate(zip(orig_lines, veri_lines)):
            if orig.strip() != veri.strip():
                changes += 1
                if changes <= 5:
                    print(f"  L{j+1} BEFORE: {orig.strip()[:70]}")
                    print(f"  L{j+1} AFTER:  {veri.strip()[:70]}")
                    print()
        if changes > 5:
            print(f"  ... +{changes - 5} more changes")
        if changes == 0:
            print(f"  ✅ No changes (transcription was correct)")
        print(f"  Total lines changed: {changes}\n")

    print(f"{'='*60}")
    print(f"Sample test complete!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
