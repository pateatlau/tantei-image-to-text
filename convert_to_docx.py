"""
Convert Markdown to DOCX using Pandoc
======================================
Converts the Markdown OCR output to a Word document with proper formatting.
Uses pandoc for professional-quality conversion with full table support.

Features:
- Extended Markdown support (pipe tables, grid tables)
- Optional reference DOCX template for styling
- Optional section numbering
- Optional table of contents

Usage:
    python convert_to_docx.py [input.md] [output.docx]

Defaults:
    Input: output_final.md (or output_proofread.md, or output.md)
    Output: output_final.docx

Dependencies:
    - pandoc (must be installed: brew install pandoc)
"""

import sys
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEFAULT_INPUTS = [
    Path("output_final.md"),
    Path("output_proofread.md"),
    Path("output.md"),
]
DEFAULT_OUTPUT = Path("output_final.docx")
REFERENCE_DOC = Path("reference.docx")

# Pandoc options
ENABLE_TOC = False               # Set to True to add table of contents
ENABLE_SECTION_NUMBERS = False   # Set to True for numbered headings (1.1, 1.2, etc.)


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
        # Use defaults — try each input in order
        input_path = None
        for candidate in DEFAULT_INPUTS:
            if candidate.exists():
                input_path = candidate
                print(f"Using input: {input_path}")
                break

        if input_path is None:
            print(f"Error: No input file found. Run the pipeline first.")
            sys.exit(1)
        output_path = DEFAULT_OUTPUT

    # Check if input exists
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    # Check if pandoc is installed
    try:
        result = subprocess.run(['pandoc', '--version'],
                      capture_output=True, check=True, text=True)
        version_line = result.stdout.split('\n')[0]
        print(f"Using {version_line}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: pandoc is not installed.")
        print("Install with: brew install pandoc")
        sys.exit(1)

    # Build pandoc command
    cmd = [
        'pandoc',
        str(input_path),
        '-o', str(output_path),
        '--from', 'markdown+pipe_tables+grid_tables',
        '--to', 'docx',
        '--wrap=none',
        '--standalone',
    ]

    # Use reference DOCX template if available
    if REFERENCE_DOC.exists():
        cmd.extend(['--reference-doc', str(REFERENCE_DOC)])
        print(f"Using reference template: {REFERENCE_DOC}")

    # Optional: section numbering
    if ENABLE_SECTION_NUMBERS:
        cmd.append('--number-sections')
        print("Section numbering: enabled")

    # Optional: table of contents
    if ENABLE_TOC:
        cmd.append('--toc')
        print("Table of contents: enabled")

    # Convert using pandoc
    print(f"Converting {input_path} → {output_path}...")

    try:
        subprocess.run(cmd, check=True)

        size_kb = output_path.stat().st_size / 1024
        print(f"  Successfully created {output_path} ({size_kb:.1f} KB)")

    except subprocess.CalledProcessError as e:
        print(f"Error: pandoc conversion failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
