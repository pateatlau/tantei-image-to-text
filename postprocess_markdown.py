"""
Post-process proofread Markdown for clean DOCX conversion
==========================================================
Fixes formatting issues that affect pandoc rendering:
1. Ensures blank lines before all headings
2. Converts <br> table cells to proper multi-row format
3. Converts letter lists (a), b), c)) to numbered lists (1., 2., 3.)
4. Removes page number headings (## Page N)
5. Normalizes inconsistent heading styles
6. Fixes malformed tables (inline bullet lists in cells)
7. Removes unnecessary line breaks within paragraphs

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

    Handles patterns:
    - Top-level:       "a) text"       → "1. text"
    - Under bullet:    "-   a) text"   → "1. text"  (at same indent as the dash)
    - Under indent:    "    -   a) text" → "    1. text"
    - Roman numerals:  "- ii) text"    → "2. text"

    The dash marker is replaced by the number — no extra indentation is added.
    Pandoc renders numbered lists properly in DOCX but ignores bare a), b), c).
    """
    letter_to_num = {chr(c): str(c - ord('a') + 1) for c in range(ord('a'), ord('z') + 1)}
    roman_to_num = {
        'i': '1', 'ii': '2', 'iii': '3', 'iv': '4', 'v': '5',
        'vi': '6', 'vii': '7', 'viii': '8', 'ix': '9', 'x': '10',
    }

    lines = text.split('\n')
    result = []

    for line in lines:
        # Pattern 1: "-   ii) text" → roman numeral under dash (check BEFORE letters)
        match = re.match(r'^(\s*)-\s+(i{1,3}|iv|vi{0,3}|ix|x)\)\s+(.*)$', line)
        if match and match.group(2) in roman_to_num:
            indent = match.group(1)
            roman = match.group(2)
            content = match.group(3)
            num = roman_to_num[roman]
            result.append(f"{indent}{num}. {content}")
            continue

        # Pattern 2: bare "ii) text" → roman numeral at any indent (check BEFORE letters)
        match = re.match(r'^(\s*)(i{1,3}|iv|vi{0,3}|ix|x)\)\s+(.*)$', line)
        if match and match.group(2) in roman_to_num:
            indent = match.group(1)
            roman = match.group(2)
            content = match.group(3)
            num = roman_to_num[roman]
            result.append(f"{indent}{num}. {content}")
            continue

        # Pattern 3: "-   a) text" or "- a) text" → letter list, replace dash with number
        match = re.match(r'^(\s*)-\s+([a-z])\)\s+(.*)$', line)
        if match:
            indent = match.group(1)
            letter = match.group(2)
            content = match.group(3)
            num = letter_to_num[letter]
            result.append(f"{indent}{num}. {content}")
            continue

        # Pattern 4: bare "a) text" at any indent level
        match = re.match(r'^(\s*)([a-z])\)\s+(.*)$', line)
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
            new_indent = ' ' * (numbered_indent + 4)
            result.append(f"{new_indent}{stripped}")
            continue

        # Blank line or heading ends the numbered context
        if stripped == '' or stripped.startswith('#'):
            in_numbered_item = False

        result.append(line)

    return '\n'.join(result)


def fix_double_dashes(text):
    """Fix '- -' malformed list markers by converting to properly indented single dash.

    Patterns:
        '  - - text'   → '    - text'   (indent increases by 2)
        '    - - text'  → '      - text'
        '- - text'      → '  - text'
    """
    lines = text.split('\n')
    result = []

    for line in lines:
        # Match lines with "- -" pattern (with optional leading whitespace)
        match = re.match(r'^(\s*)- -\s+(.*)$', line)
        if match:
            indent = match.group(1)
            content = match.group(2)
            new_indent = indent + '  '
            result.append(f"{new_indent}- {content}")
        else:
            # Also handle "    -   - text" pattern (dash, whitespace, dash)
            match = re.match(r'^(\s*)-\s+-\s+(.*)$', line)
            if match:
                indent = match.group(1)
                content = match.group(2)
                new_indent = indent + '  '
                result.append(f"{new_indent}- {content}")
            else:
                result.append(line)

    return '\n'.join(result)


def normalize_list_markers(text):
    """Normalize all * list markers to - for consistency.

    Converts:
        '* text'       → '- text'
        '    * text'   → '    - text'
        '*   text'     → '-   text'
    """
    lines = text.split('\n')
    result = []

    for line in lines:
        # Match lines starting with optional whitespace + * + space(s) + text
        match = re.match(r'^(\s*)\*(\s+.*)$', line)
        if match:
            indent = match.group(1)
            rest = match.group(2)
            result.append(f"{indent}-{rest}")
        else:
            result.append(line)

    return '\n'.join(result)


def fix_heading_in_list_items(text):
    """Remove # heading markers from inside numbered/lettered list items.

    Converts:
        '3. # Economic Policy'  → '3. Economic Policy'
        'D. # Whistle Blower'   → 'D. Whistle Blower'
    """
    # Pattern: number or letter followed by ". # "
    text = re.sub(r'^(\s*\d+\.\s+)#\s+', r'\1', text, flags=re.MULTILINE)
    text = re.sub(r'^(\s*[A-Z]\.\s+)#\s+', r'\1', text, flags=re.MULTILINE)
    return text


def join_fragmented_list_items(text):
    """Join list items that are fragmented across multiple continuation lines.

    Handles the pattern where OCR breaks a single bullet into multiple lines:
        '-   Reduce cognitive\\n    dissonance and\\n    mental stress'
    becomes:
        '-   Reduce cognitive dissonance and mental stress'

    Only joins when continuation lines are:
    - Indented (more than the dash)
    - NOT a list marker themselves (no leading - or * or digit.)
    - NOT blank
    - Short (< 60 chars, typical of OCR line fragments)
    """
    lines = text.split('\n')
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Check if this is a list item (starts with - or * or digit.)
        is_list_item = bool(re.match(r'^(\s*)(-|\*|\d+\.)\s+', line))

        if is_list_item:
            # Get the indent level of content after the marker
            match = re.match(r'^(\s*(?:-|\*|\d+\.)\s+)', line)
            marker_prefix = match.group(1)
            content_indent = len(marker_prefix)

            # Collect continuation lines
            combined = line
            j = i + 1
            while j < len(lines):
                next_line = lines[j]
                next_stripped = next_line.strip()

                # Stop if blank line
                if next_stripped == '':
                    break

                # Stop if it's a new list item or heading
                if re.match(r'^\s*(-|\*|\d+\.)\s+', next_line) or next_stripped.startswith('#'):
                    break

                # Check if it's a continuation line (indented, not a marker, short)
                next_leading = len(next_line) - len(next_line.lstrip())
                if next_leading >= content_indent - 2 and len(next_stripped) < 60:
                    # Join to current line
                    combined = combined.rstrip() + ' ' + next_stripped
                    j += 1
                else:
                    break

            result.append(combined)
            i = j
        else:
            result.append(line)
            i += 1

    return '\n'.join(result)


def clean_stray_markers(text):
    """Clean up stray markers like standalone '- *' or orphaned section numbers."""
    lines = text.split('\n')
    result = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        # Remove standalone "- *" lines (stray bullet + asterisk)
        if stripped == '- *' or stripped == '*':
            continue
        # Remove orphaned section numbers (e.g., "1.5", "16.1") followed by a heading
        if re.match(r'^\d+\.\d+$', stripped):
            # Check if next non-blank line is a heading
            for j in range(i + 1, min(i + 3, len(lines))):
                next_stripped = lines[j].strip()
                if next_stripped == '':
                    continue
                if next_stripped.startswith('#'):
                    break  # Skip this orphaned number
                else:
                    result.append(line)  # Keep it, not before a heading
                    break
            continue
        result.append(line)

    return '\n'.join(result)


def make_nested_lists_loose(text):
    """Insert blank lines to make pandoc render multi-level lists with proper nesting.

    Pandoc requires "loose" lists (blank lines between items) to produce proper
    nesting levels in DOCX. Without blank lines, all items flatten to level 0.

    Rules applied:
    1. If a list item is followed by a more-indented list item (child),
       insert a blank line between them.
    2. If a list item with children is followed by a sibling at the same level,
       insert a blank line between the last child and the sibling.
    """
    lines = text.split('\n')
    result = []
    list_item_re = re.compile(r'^(\s*)(-|\d+\.)\s+')

    for i, line in enumerate(lines):
        result.append(line)

        if i + 1 >= len(lines):
            continue

        current_match = list_item_re.match(line)
        next_match = list_item_re.match(lines[i + 1])

        if not current_match or not next_match:
            continue

        current_indent = len(current_match.group(1))
        next_indent = len(next_match.group(1))

        # Rule 1: current item followed by a deeper-indented child → insert blank line
        if next_indent > current_indent:
            result.append('')

        # Rule 2: current item followed by a less-indented sibling (popping out) → insert blank line
        if next_indent < current_indent:
            result.append('')

    return '\n'.join(result)


def collapse_excessive_blank_lines(text):
    """Collapse 3+ consecutive blank lines into 2."""
    return re.sub(r'\n{4,}', '\n\n\n', text)


def normalize_heading_styles(text):
    """Normalize inconsistent heading styles.

    Fixes:
    - Headings with trailing # marks: "## Title ##" → "## Title"
    - Headings with extra spaces: "#  Title" → "# Title"
    - Ensure consistent spacing after # marks
    """
    lines = text.split('\n')
    result = []

    for line in lines:
        stripped = line.strip()
        # Fix trailing # marks
        match = re.match(r'^(#{1,6})\s+(.+?)\s*#{1,6}\s*$', stripped)
        if match:
            result.append(f"{match.group(1)} {match.group(2)}")
            continue

        # Fix extra spaces after # marks
        match = re.match(r'^(#{1,6})\s{2,}(.+)$', stripped)
        if match:
            result.append(f"{match.group(1)} {match.group(2)}")
            continue

        result.append(line)

    return '\n'.join(result)


def fix_table_inline_lists(text):
    """Convert inline bullet lists inside table cells to semicolon-separated text.

    Bad:  | Premature Transfers | - political patronage | - corruption |
    Good: | Premature Transfers | political patronage; corruption |

    This avoids broken DOCX table rendering.
    """
    lines = text.split('\n')
    result = []

    for line in lines:
        if '|' not in line:
            result.append(line)
            continue

        # Check if this is a table row (contains | separators)
        if not re.match(r'^\s*\|', line):
            result.append(line)
            continue

        # Skip separator rows (|---|---|)
        if re.match(r'^\s*\|[\s\-:]+\|', line):
            result.append(line)
            continue

        # Process each cell: convert "- item" patterns to inline text
        cells = line.split('|')
        new_cells = []
        for cell in cells:
            # Convert inline bullet lists within a cell
            # Match cells that contain "- item1 - item2" or "- item1; - item2"
            if re.search(r'^\s*-\s+', cell.strip()):
                # Remove leading dash markers and join with semicolons
                items = re.split(r'\s*-\s+', cell.strip())
                items = [item.strip() for item in items if item.strip()]
                new_cells.append(' ' + '; '.join(items) + ' ')
            else:
                new_cells.append(cell)

        result.append('|'.join(new_cells))

    return '\n'.join(result)


def fix_orphaned_continuation_lines(text):
    """Join short orphaned lines that should be part of the previous paragraph.

    OCR sometimes breaks long sentences into multiple lines. This joins
    continuation lines that are:
    - Not blank
    - Not a heading, list item, or table row
    - Short (< 50 chars)
    - Following a line that doesn't end with punctuation suggesting a paragraph end
    """
    lines = text.split('\n')
    result = []

    for i, line in enumerate(lines):
        stripped = line.strip()

        if i == 0 or not stripped:
            result.append(line)
            continue

        # Skip structural lines
        if (stripped.startswith('#') or
            stripped.startswith('-') or
            stripped.startswith('*') or
            re.match(r'^\d+\.', stripped) or
            '|' in stripped):
            result.append(line)
            continue

        # Check if previous line is a candidate for joining
        if not result:
            result.append(line)
            continue

        prev = result[-1].strip()
        if (prev and
            not prev.startswith('#') and
            not prev.startswith('-') and
            not prev.startswith('*') and
            not re.match(r'^\d+\.', prev) and
            '|' not in prev and
            len(stripped) < 50 and
            not prev.endswith(('.', ':', '!', '?', '"'))):
            # Join to previous line
            result[-1] = result[-1].rstrip() + ' ' + stripped
        else:
            result.append(line)

    return '\n'.join(result)


def main():
    if not INPUT_PATH.exists():
        print(f"Error: Input not found: {INPUT_PATH}")
        return

    print(f"Reading {INPUT_PATH}...")
    text = INPUT_PATH.read_text(encoding='utf-8')
    original_len = len(text)

    print("Normalizing heading styles...")
    text = normalize_heading_styles(text)

    print("Fixing headings (adding blank lines)...")
    text = ensure_blank_lines_before_headings(text)

    print("Removing page number headings...")
    text = remove_page_headings(text)

    print("Fixing table <br> tags...")
    text = fix_br_tables(text)

    print("Fixing inline lists in table cells...")
    text = fix_table_inline_lists(text)

    print("Normalizing list markers (* to -)...")
    text = normalize_list_markers(text)

    print("Converting letter lists (a, b, c) to numbered lists (1, 2, 3)...")
    text = fix_letter_lists(text)

    print("Fixing double dashes (- - markers)...")
    text = fix_double_dashes(text)

    print("Fixing heading markers inside list items...")
    text = fix_heading_in_list_items(text)

    print("Joining fragmented list items...")
    text = join_fragmented_list_items(text)

    print("Joining orphaned continuation lines...")
    text = fix_orphaned_continuation_lines(text)

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
