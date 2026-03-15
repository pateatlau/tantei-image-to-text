"""
Convert Markdown to DOCX using Pandoc
======================================
Converts the Markdown OCR output to a Word document with proper formatting.
Uses pandoc for professional-quality conversion with full table support.

Usage:
    python convert_to_docx.py [input.md] [output.docx]

Defaults:
    Input: output_proofread.md (or output.md if proofread doesn't exist)
    Output: output_proofread.docx

Dependencies:
    - pandoc (must be installed: brew install pandoc)
"""

import sys
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEFAULT_INPUT = Path("output_proofread.md")
FALLBACK_INPUT = Path("output.md")
DEFAULT_OUTPUT = Path("output_proofread.docx")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    # Parse command line arguments
    if len(sys.argv) == 3:
        input_path = Path(sys.argv[1])
        output_path = Path(sys.argv[2])
    elif len(sys.argv) == 2:
        input_path = Path(sys.argv[1])
        output_path = DEFAULT_OUTPUT
    else:
        # Use defaults
        if DEFAULT_INPUT.exists():
            input_path = DEFAULT_INPUT
            print(f"Using proofread version: {input_path}")
        elif FALLBACK_INPUT.exists():
            input_path = FALLBACK_INPUT
            print(f"Proofread version not found, using: {input_path}")
        else:
            print(f"Error: No input file found. Run ocr_book.py first.")
            sys.exit(1)
        output_path = DEFAULT_OUTPUT

    # Check if input exists
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    # Check if pandoc is installed
    try:
        subprocess.run(['pandoc', '--version'],
                      capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: pandoc is not installed.")
        print("Install with: brew install pandoc")
        sys.exit(1)

    # Convert using pandoc
    print(f"Converting {input_path} to {output_path} using pandoc...")

    try:
        subprocess.run([
            'pandoc',
            str(input_path),
            '-o', str(output_path),
            '--from', 'markdown',
            '--to', 'docx'
        ], check=True)

        print(f"✓ Successfully created {output_path}")
        print(f"  File size: {output_path.stat().st_size / 1024:.1f} KB")

    except subprocess.CalledProcessError as e:
        print(f"Error: pandoc conversion failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
