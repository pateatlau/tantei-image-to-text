"""
Proofread OCR output using Gemini (Chunked Processing)
=======================================================
Sends the OCR output to Gemini for proofreading and correction.
Processes document in chunks to avoid token limits.

Usage:
    python proofread.py

Input: output.md
Output: output_proofread.md
"""

import os
import sys
import re
import time
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
INPUT_PATH = Path("output.md")
OUTPUT_PATH = Path("output_proofread.md")
DIFF_PATH = Path("proofread_comparison.txt")
MODEL_NAME = "gemini-2.5-flash"
CHUNK_SIZE = 15  # Pages per chunk (to stay under token limits)
REQUESTS_PER_MINUTE = 15  # Free tier rate limit

PROOFREAD_PROMPT = """You are a professional proofreader specializing in Indian civil services study materials.

I will provide you with OCR output from a handwritten document about Ethics in Administration, Probity, Governance, and Civil Services. The OCR may contain minor errors from handwriting recognition.

Your task:
1. Fix obvious OCR errors (e.g., "Sourcis" → "Services", "gavernance" → "governance")
2. Correct spelling mistakes while preserving domain-specific terms
3. Fix grammatical errors and improve clarity
4. Preserve the original structure, headings, bullet points, and numbered lists
5. Maintain all Markdown formatting
6. Keep abbreviations as-is (CS, IAS, IPS, IFS, PA, WF, etc.)
7. Do NOT add new content or interpretations — only fix errors

Domain terminology to watch for:
- Civil Services, Public Administration, Governance, Probity, Ethics
- IAS (Indian Administrative Service), IPS (Indian Police Service), IFS (Indian Forest Service)
- RTI (Right to Information), E-governance, Sevottam Model
- Accountability, Transparency, Citizen Charters, Social Audit
- KSRTC, NERCORMP, SHGs (Self Help Groups)

Return ONLY the corrected text in Markdown format. No explanations, no commentary."""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    if not INPUT_PATH.exists():
        print(f"Error: Input file not found: {INPUT_PATH}")
        sys.exit(1)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY is not set.")
        sys.exit(1)

    print(f"Reading OCR output from {INPUT_PATH}...")
    ocr_text = INPUT_PATH.read_text(encoding='utf-8')

    # Split into chunks by page markers
    print(f"Splitting document into chunks...")
    chunks = split_into_chunks(ocr_text, CHUNK_SIZE)
    print(f"Total chunks: {len(chunks)}")

    # Process each chunk
    client = genai.Client(api_key=api_key)
    proofread_chunks = []

    for i, chunk in enumerate(chunks, 1):
        print(f"\nProcessing chunk {i}/{len(chunks)}...")

        # Rate limiting
        if i > 1:
            wait_time = 60 / REQUESTS_PER_MINUTE
            print(f"  Rate limiting: waiting {wait_time:.1f}s...")
            time.sleep(wait_time)

        # Retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=MODEL_NAME,
                    contents=[
                        PROOFREAD_PROMPT,
                        f"\n\n--- OCR OUTPUT TO PROOFREAD ---\n\n{chunk}"
                    ],
                    config=types.GenerateContentConfig(
                        temperature=0.3,
                    ),
                )

                if response.text is None:
                    raise ValueError("API returned empty response")

                proofread_chunk = response.text.strip()

                # Strip code fences if present
                proofread_chunk = re.sub(r'^```(?:markdown)?\s*\n', '', proofread_chunk)
                proofread_chunk = re.sub(r'\n```\s*$', '', proofread_chunk)

                proofread_chunks.append(proofread_chunk)
                print(f"  ✓ Chunk {i} completed ({len(proofread_chunk)} chars)")
                break  # Success, exit retry loop

            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"  ⚠ Retry {attempt + 1}/{max_retries} - Error: {e}")
                    time.sleep(5)  # Wait before retry
                else:
                    print(f"  ✗ Failed after {max_retries} attempts: {e}")
                    print(f"  Using original chunk as fallback...")
                    proofread_chunks.append(chunk)  # Fallback to original

    # Merge chunks
    print(f"\nMerging {len(proofread_chunks)} chunks...")
    proofread_text = "\n\n".join(proofread_chunks)

    print(f"Writing proofread output to {OUTPUT_PATH}...")
    OUTPUT_PATH.write_text(proofread_text, encoding='utf-8')

    # Create a side-by-side comparison file
    print(f"Creating comparison file at {DIFF_PATH}...")
    comparison = create_comparison(ocr_text, proofread_text)
    DIFF_PATH.write_text(comparison, encoding='utf-8')

    print(f"\n{'='*60}")
    print(f"✓ Proofreading complete!")
    print(f"{'='*60}")
    print(f"Original:   {INPUT_PATH} ({len(ocr_text):,} chars)")
    print(f"Proofread:  {OUTPUT_PATH} ({len(proofread_text):,} chars)")
    print(f"Comparison: {DIFF_PATH}")
    print(f"{'='*60}")


def split_into_chunks(text, pages_per_chunk):
    """Split document into chunks by page markers."""
    # Split by page markers (e.g., "## Page 1", "## Page 2", etc.)
    page_pattern = r'^## Page \d+$'
    lines = text.split('\n')

    chunks = []
    current_chunk = []
    pages_in_chunk = 0

    for line in lines:
        if re.match(page_pattern, line):
            if pages_in_chunk >= pages_per_chunk and current_chunk:
                # Start new chunk
                chunks.append('\n'.join(current_chunk))
                current_chunk = [line]
                pages_in_chunk = 1
            else:
                current_chunk.append(line)
                pages_in_chunk += 1
        else:
            current_chunk.append(line)

    # Add remaining content
    if current_chunk:
        chunks.append('\n'.join(current_chunk))

    return chunks


def create_comparison(original, proofread):
    """Create a simple side-by-side comparison showing changes."""
    comparison_lines = []
    comparison_lines.append("=" * 80)
    comparison_lines.append("PROOFREADING COMPARISON (CHUNKED PROCESSING)")
    comparison_lines.append("=" * 80)
    comparison_lines.append("")
    comparison_lines.append("This file shows a basic comparison between the original OCR")
    comparison_lines.append("and the proofread version. For detailed diff, use a diff tool.")
    comparison_lines.append("")
    comparison_lines.append("=" * 80)
    comparison_lines.append("")

    # Simple line-by-line comparison showing changed lines
    orig_lines = original.split('\n')
    proof_lines = proofread.split('\n')

    max_lines = max(len(orig_lines), len(proof_lines))
    changes_found = 0

    for i in range(max_lines):
        orig_line = orig_lines[i] if i < len(orig_lines) else ""
        proof_line = proof_lines[i] if i < len(proof_lines) else ""

        if orig_line.strip() != proof_line.strip():
            changes_found += 1
            comparison_lines.append(f"Line {i+1} - CHANGED:")
            comparison_lines.append(f"  BEFORE: {orig_line}")
            comparison_lines.append(f"  AFTER:  {proof_line}")
            comparison_lines.append("")

    comparison_lines.append("=" * 80)
    comparison_lines.append(f"Total changes detected: {changes_found} lines")
    comparison_lines.append("=" * 80)

    return '\n'.join(comparison_lines)


if __name__ == "__main__":
    main()
