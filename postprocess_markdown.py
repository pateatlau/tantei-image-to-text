"""
Post-process proofread Markdown for clean DOCX conversion
==========================================================
Fixes formatting issues that affect pandoc rendering:
1. Ensures blank lines before all headings
2. Converts <br> table cells to proper multi-row format
3. Converts letter lists (a), b), c)) to numbered lists (1., 2., 3.)
4. Removes page number headings (## Page N)

Usage:
    python postprocess_markdown.py

Input: output_proofread.md
Output: output_final.md
"""

import re
from pathlib import Path


INPUT_PATH = Path("output_proofread.md")
OUTPUT_PATH = Path("output_final.md")


def ensure_blank_lines_before_headings(text):
    """Ensure every heading has a blank line before it."""
    lines = text.split('\n')
    result = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('#') and i > 0:
            # Check if previous line is non-empty
            if result and result[-1].strip() != '':
                result.append('')
        result.append(line)

    return '\n'.join(result)


def remove_page_headings(text):
    """Remove ## Page N headings."""
    # Remove "## Page N" lines and the blank line after them
    text = re.sub(r'^## Page \d+\s*\n\n?', '', text, flags=re.MULTILINE)
    return text


def fix_br_tables(text):
    """Convert tables with <br> tags to clean multi-line content.

    Pandoc doesn't render <br> in table cells well.
    Convert to pandoc grid tables which support multi-line cells.
    """
    lines = text.split('\n')
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Detect table start (header row with |)
        if '|' in line and '<br>' in line:
            # This is a table row with <br> tags - convert to clean format
            # Replace <br> with newline within cells for readability
            # But since pandoc pipe tables don't support multi-line,
            # convert <br> to semicolons for cleaner display
            cleaned = line.replace('<br>', '; ')
            # Clean up multiple spaces
            cleaned = re.sub(r';\s+- ', '; ', cleaned)
            cleaned = re.sub(r';\s+', '; ', cleaned)
            result.append(cleaned)
        elif '|' in line and i + 1 < len(lines) and '<br>' in lines[i + 1]:
            # Header row before br rows
            result.append(line)
        else:
            result.append(line)

        i += 1

    return '\n'.join(result)


def fix_letter_lists(text):
    """Convert letter-style lists (a), b), c)...) to numbered lists (1., 2., 3...).

    Handles three patterns:
    - Top-level:       "a) text" → "1. text"
    - Under bullet:    "  a) text" → "  1. text"  (also "  - a) text")
    - Under number:    "    a) text" → "    1. text"

    Pandoc renders numbered lists properly in DOCX but ignores bare a), b), c).
    """
    letter_to_num = {chr(c): str(c - ord('a') + 1) for c in range(ord('a'), ord('z') + 1)}

    lines = text.split('\n')
    result = []

    for line in lines:
        # Pattern 1: "- a) text" → remove the "- " prefix, convert to numbered
        match = re.match(r'^(\s*)- ([a-z])\) (.*)$', line)
        if match:
            indent = match.group(1)
            letter = match.group(2)
            content = match.group(3)
            num = letter_to_num[letter]
            result.append(f"{indent}{num}. {content}")
            continue

        # Pattern 2: bare "a) text" at any indent level
        match = re.match(r'^(\s*)([a-z])\) (.*)$', line)
        if match:
            indent = match.group(1)
            letter = match.group(2)
            content = match.group(3)
            num = letter_to_num[letter]
            result.append(f"{indent}{num}. {content}")
            continue

        result.append(line)

    return '\n'.join(result)


def ensure_blank_lines_before_lists(text):
    """Ensure a blank line before numbered and bulleted lists.

    Pandoc requires a blank line before a list to parse it as a list.
    Without it, "text\\n1. item" becomes a single paragraph.
    """
    lines = text.split('\n')
    result = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        is_list_start = (
            re.match(r'^\d+\.\s+', stripped) or
            re.match(r'^-\s+', stripped)
        )

        if is_list_start and i > 0:
            prev = result[-1].strip() if result else ''
            prev_is_list = (
                re.match(r'^\d+\.\s+', prev) or
                re.match(r'^-\s+', prev)
            )
            # Add blank line if previous line is non-empty plain text (not a list or heading or blank)
            if prev != '' and not prev.startswith('#') and not prev_is_list:
                result.append('')

        result.append(line)

    return '\n'.join(result)


def fix_list_nesting(text):
    """Ensure bullet sub-items are indented under their parent numbered items.

    Fixes patterns like:
        1. Protective functions
        - maintaining law and order    ← should be indented under 1.

    Converts to:
        1. Protective functions
           - maintaining law and order
    """
    lines = text.split('\n')
    result = []
    in_numbered_item = False
    numbered_indent = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        leading = len(line) - len(line.lstrip())

        # Detect numbered list item at current indent
        if re.match(r'^\s*\d+\.\s+', line):
            in_numbered_item = True
            numbered_indent = leading
            result.append(line)
            continue

        # If we're under a numbered item and this is a bullet at same or less indent
        if in_numbered_item and stripped.startswith('- ') and leading <= numbered_indent:
            # Indent the bullet under the numbered item
            new_indent = ' ' * (numbered_indent + 3)
            result.append(f"{new_indent}{stripped}")
            continue

        # Blank line or heading ends the numbered context
        if stripped == '' or stripped.startswith('#'):
            in_numbered_item = False

        result.append(line)

    return '\n'.join(result)


def clean_stray_markers(text):
    """Clean up stray markers like standalone '- *' or section numbers on their own line."""
    lines = text.split('\n')
    result = []

    for line in lines:
        stripped = line.strip()
        # Remove standalone "- *" lines (stray bullet + asterisk)
        if stripped == '- *' or stripped == '*':
            continue
        result.append(line)

    return '\n'.join(result)


def collapse_excessive_blank_lines(text):
    """Collapse 3+ consecutive blank lines into 2."""
    return re.sub(r'\n{4,}', '\n\n\n', text)


def main():
    if not INPUT_PATH.exists():
        print(f"Error: Input not found: {INPUT_PATH}")
        return

    print(f"Reading {INPUT_PATH}...")
    text = INPUT_PATH.read_text(encoding='utf-8')
    original_len = len(text)

    print("Fixing headings (adding blank lines)...")
    text = ensure_blank_lines_before_headings(text)

    print("Removing page number headings...")
    text = remove_page_headings(text)

    print("Fixing table <br> tags...")
    text = fix_br_tables(text)

    print("Converting letter lists (a, b, c) to numbered lists (1, 2, 3)...")
    text = fix_letter_lists(text)

    print("Adding blank lines before lists...")
    text = ensure_blank_lines_before_lists(text)

    print("Fixing list nesting (indenting sub-bullets under numbers)...")
    text = fix_list_nesting(text)

    print("Cleaning stray markers...")
    text = clean_stray_markers(text)

    print("Collapsing excessive blank lines...")
    text = collapse_excessive_blank_lines(text)

    # Trim leading/trailing whitespace
    text = text.strip() + '\n'

    print(f"Writing {OUTPUT_PATH}...")
    OUTPUT_PATH.write_text(text, encoding='utf-8')

    print(f"\n{'='*60}")
    print(f"✓ Post-processing complete!")
    print(f"{'='*60}")
    print(f"Original:      {INPUT_PATH} ({original_len:,} chars)")
    print(f"Post-processed: {OUTPUT_PATH} ({len(text):,} chars)")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
