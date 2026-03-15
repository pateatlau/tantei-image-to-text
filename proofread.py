"""
Proofread OCR output using Gemini
===================================
Sends the OCR output to Gemini for proofreading and correction.

Usage:
    python proofread.py

Input: output.md
Output: output_proofread.md
"""

import os
import sys
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

    print(f"Sending to Gemini for proofreading...")
    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[
            PROOFREAD_PROMPT,
            f"\n\n--- OCR OUTPUT TO PROOFREAD ---\n\n{ocr_text}"
        ],
        config=types.GenerateContentConfig(
            temperature=0.3,  # Slight creativity for better corrections
        ),
    )

    proofread_text = response.text.strip()

    # Strip code fences if present
    import re
    proofread_text = re.sub(r'^```(?:markdown)?\s*\n', '', proofread_text)
    proofread_text = re.sub(r'\n```\s*$', '', proofread_text)

    print(f"Writing proofread output to {OUTPUT_PATH}...")
    OUTPUT_PATH.write_text(proofread_text, encoding='utf-8')

    # Create a side-by-side comparison file
    print(f"Creating comparison file at {DIFF_PATH}...")
    comparison = create_comparison(ocr_text, proofread_text)
    DIFF_PATH.write_text(comparison, encoding='utf-8')

    print(f"\nDone!")
    print(f"Original:  {INPUT_PATH} ({len(ocr_text)} chars)")
    print(f"Proofread: {OUTPUT_PATH} ({len(proofread_text)} chars)")
    print(f"Comparison: {DIFF_PATH}")


def create_comparison(original, proofread):
    """Create a simple side-by-side comparison showing changes."""
    comparison_lines = []
    comparison_lines.append("=" * 80)
    comparison_lines.append("PROOFREADING COMPARISON")
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
