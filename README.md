# Tantei - Handwritten PDF to Markdown + DOCX

Converts handwritten PDF documents into structured Markdown and formatted DOCX using Google Gemini 2.5 Flash.

## Why Gemini?

Traditional OCR engines (Tesseract, Google Cloud Vision, TrOCR) struggle with cursive handwriting. Gemini is a large multimodal model that understands handwriting in context, producing ~95%+ accuracy on legible English handwriting.

The free tier (250 requests/day) is sufficient for most documents.

## Pipeline Overview

```
book.pdf
  │
  ├─ ocr_book.py ──────────► output.md           (raw OCR)
  │
  ├─ proofread.py ─────────► output_proofread.md  (chunked proofreading via Gemini)
  │
  ├─ verify_with_images.py ► output_verified.md   (optional: image-aware verification)
  │
  ├─ postprocess_markdown.py ► output_final.md    (formatting fixes for DOCX)
  │
  └─ pandoc + format_docx.py ► output_final.docx  (formatted Word document)
```

## Prerequisites

- **Python 3.10+**
- macOS / Linux
- [Poppler](https://poppler.freedesktop.org/) for PDF rendering
- [Pandoc](https://pandoc.org/) for DOCX conversion
- A Google Gemini API key (free)

## Setup

### 1. Install system dependencies

```bash
# macOS
brew install poppler pandoc

# Ubuntu/Debian
sudo apt-get install poppler-utils pandoc
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Get a Gemini API key

1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Click "Create API Key"
3. Copy the key

### 4. Configure

```bash
cp .env.example .env
```

Edit `.env` and paste your API key:

```
GEMINI_API_KEY=your-actual-key-here
```

## Usage

Place your PDF in the project directory as `book.pdf`.

### Step 1: OCR

```bash
python ocr_book.py
```

Converts each page to an image, sends it to Gemini, and writes `output.md`.

For testing, `MAX_PAGES` is set to 5. Set `MAX_PAGES = None` in `ocr_book.py` for the full document.

### Step 2: Proofread

```bash
python proofread.py
```

Sends the OCR output to Gemini in chunks (15 pages at a time) for grammar, spelling, and formatting corrections. Writes `output_proofread.md`.

### Step 3: Image verification (optional)

```bash
python verify_with_images.py
```

Sends each page image alongside its transcription to Gemini for word-level verification against the original handwriting. Writes `output_verified.md`.

This step is optional and experimental — see [Notes on image verification](#notes-on-image-verification) below.

### Step 4: Post-process and convert to DOCX

```bash
python postprocess_markdown.py
pandoc output_final.md -o output_final.docx --from markdown --to docx --reference-doc=reference.docx
python format_docx.py
```

The post-processing step fixes markdown formatting for clean DOCX rendering:
- Ensures blank lines before headings (required by pandoc)
- Removes `## Page N` markers
- Fixes `<br>` tags in tables (not supported by pandoc)
- Converts letter-style lists (a, b, c) to numbered lists
- Fixes list nesting and spacing

The formatting step adds:
- Visible borders on all tables
- Document header with title and bottom border
- Page footer with "Page X of Y pages" and top border

## Scripts

| Script | Purpose |
|--------|---------|
| `ocr_book.py` | Main OCR pipeline — PDF to Markdown via Gemini |
| `proofread.py` | Chunked proofreading of OCR output via Gemini |
| `verify_with_images.py` | Image-aware verification (page image + transcription) |
| `verify_sample.py` | Quick 5-page sample test for the verification pipeline |
| `postprocess_markdown.py` | Markdown formatting fixes for DOCX conversion |
| `convert_to_docx.py` | Simple pandoc wrapper for Markdown to DOCX |
| `format_docx.py` | DOCX post-processing (table borders, header, footer) |

## Configuration

Key settings in `ocr_book.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `PDF_PATH` | `book.pdf` | Input PDF file |
| `OUTPUT_PATH` | `output.md` | Output Markdown file |
| `OCR_DPI` | `300` | DPI for PDF rendering |
| `MAX_PAGES` | `5` | Pages to process (`None` for all) |
| `MODEL_NAME` | `gemini-2.5-flash` | Gemini model to use |
| `REQUESTS_PER_MINUTE` | `9` | Rate limit (free tier allows 10) |

## How it works

1. **PDF to images** — Converts each page to a 300 DPI image using `pdf2image` (poppler)
2. **Gemini OCR** — Sends each page image to Gemini 2.5 Flash with a domain-aware prompt
3. **Post-processing** — Strips code fences, removes duplicate lines
4. **Markdown output** — Writes structured output with page separators
5. **Proofreading** — Processes in 15-page chunks to stay within token limits, with retry logic and rate limiting
6. **DOCX conversion** — Pandoc handles markdown-to-DOCX with a reference document for styling, then python-docx adds table borders, header, and footer

The OCR prompt includes domain context (Indian civil services, ethics, governance) to help the model resolve ambiguous handwriting. Update the `DOMAIN CONTEXT` section in `OCR_PROMPT` for other document types.

## Notes on image verification

The `verify_with_images.py` script sends each page image alongside its transcription to Gemini for word-level correction. While promising in theory, testing showed a ~2.7:1 regression-to-improvement ratio — the model "confidently corrected" things that were already right, particularly:

- Proper nouns and names
- Domain-specific acronyms
- Dates and technical terms

The script includes safeguards (sanity checks for output size, incremental saves, resume capability), but results should be carefully compared before using verified output over proofread output.

## Costs

Gemini 2.5 Flash free tier: 10 requests/min, 250 requests/day. A 150-page PDF fits within the free daily limit. The full pipeline (OCR + proofreading) requires ~2x the page count in API calls.

## License

MIT
