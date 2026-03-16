# Tantei - Handwritten PDF to Markdown + DOCX

Converts handwritten PDF documents into structured Markdown and formatted DOCX using Google Gemini 2.5 Flash with dual OCR and disagreement resolution for high accuracy.

## Why Gemini?

Traditional OCR engines (Tesseract, Google Cloud Vision, TrOCR) struggle with cursive handwriting. Gemini is a large multimodal model that understands handwriting in context, producing ~95%+ accuracy on legible English handwriting.

The free tier (250 requests/day) is sufficient for most documents.

## Pipeline Overview

```
book.pdf
  │
  ├─ ocr_book.py ──────────► output.md           (dual OCR + resolver)
  │    ├─ image preprocessing (grayscale, blur, upscale)
  │    ├─ OCR pass A (structure-focused prompt)
  │    ├─ OCR pass B (character-focused prompt)
  │    ├─ disagreement resolver (picks best reading)
  │    └─ named entity correction
  │
  ├─ proofread.py ─────────► output_proofread.md  (chunked proofreading via Gemini)
  │
  ├─ verify_with_images.py ► output_verified.md   (optional: image-aware verification)
  │
  ├─ postprocess_markdown.py ► output_final.md    (15-step formatting normalization)
  │
  └─ convert_to_docx.py + format_docx.py ► output_final.docx  (formatted Word document)
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

Converts each page to an image, preprocesses it (grayscale + blur + upscale), runs two independent OCR passes with different prompts, and resolves disagreements against the original image. Applies named entity correction and writes `output.md`.

Set `ENABLE_DUAL_OCR = False` for single-pass mode (faster, fewer API calls).

For testing, set `MAX_PAGES = 5` in `ocr_book.py`. Set `MAX_PAGES = None` for the full document.

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
python convert_to_docx.py
python format_docx.py
```

The post-processing step runs 15 normalization passes:
- Normalizes heading styles (trailing `#`, extra spaces)
- Ensures blank lines before headings and lists
- Removes `## Page N` markers
- Fixes `<br>` tags and inline bullet lists in tables
- Normalizes list markers (`*` to `-`)
- Converts letter lists (a, b, c) to numbered lists
- Fixes double dashes, heading markers inside list items
- Joins fragmented list items and orphaned continuation lines
- Fixes list nesting and cleans stray markers

The DOCX conversion uses Pandoc with extended Markdown support (`pipe_tables+grid_tables`) and the `reference.docx` template. The formatting step adds:
- Visible borders on all tables
- Document header with title and bottom border
- Page footer with "Page X of Y pages" and top border

## Scripts

| Script | Purpose |
|--------|---------|
| `ocr_book.py` | Dual OCR pipeline with preprocessing and entity correction |
| `proofread.py` | Chunked proofreading of OCR output via Gemini |
| `verify_with_images.py` | Image-aware verification (page image + transcription) |
| `verify_sample.py` | Quick 5-page sample test for the verification pipeline |
| `postprocess_markdown.py` | 15-step Markdown normalization for DOCX conversion |
| `convert_to_docx.py` | Pandoc wrapper with reference template and extended Markdown |
| `format_docx.py` | DOCX post-processing (table borders, header, footer) |

## Configuration

Key settings in `ocr_book.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `PDF_PATH` | `book.pdf` | Input PDF file |
| `OUTPUT_PATH` | `output.md` | Output Markdown file |
| `OCR_DPI` | `300` | DPI for PDF rendering |
| `MAX_PAGES` | `None` | Pages to process (`None` for all) |
| `MODEL_NAME` | `gemini-2.5-flash` | Gemini model to use |
| `REQUESTS_PER_MINUTE` | `9` | Rate limit (free tier allows 10) |
| `ENABLE_DUAL_OCR` | `True` | Use dual OCR + resolver (3 calls/page) |
| `ENABLE_PREPROCESSING` | `True` | Apply image preprocessing before OCR |

## How it works

1. **PDF to images** — Converts each page to a 300 DPI image using `pdf2image` (poppler)
2. **Image preprocessing** — Grayscale conversion, Gaussian blur (3x3), 1.3x upscale via OpenCV for cleaner character recognition
3. **Dual OCR** — Two independent OCR passes with different prompts (structure-focused and character-focused) encourage different interpretations of ambiguous handwriting
4. **Disagreement resolution** — When the two passes disagree, a resolver prompt receives both transcriptions plus the original image and picks the most accurate reading
5. **Named entity correction** — Dictionary-based correction of common OCR misspellings for domain-specific proper nouns and terms
6. **Proofreading** — Processes in 15-page chunks with retry logic and rate limiting
7. **Markdown normalization** — 15-step post-processing pipeline fixes formatting for clean DOCX rendering
8. **DOCX conversion** — Pandoc with `reference.docx` template and extended Markdown, then python-docx adds table borders, header, and footer

The OCR prompts include domain context (Indian civil services, ethics, governance) to help the model resolve ambiguous handwriting. Update the `DOMAIN CONTEXT` sections in `OCR_PROMPT_A` and `OCR_PROMPT_B` for other document types.

## Performance

| Metric | Single OCR | Dual OCR |
|--------|-----------|----------|
| API calls/page | 1 | 3 |
| Time/page (at 9 RPM) | ~7s | ~50s |
| 104-page document | ~15 min | ~86 min |
| Expected accuracy | ~97-98% | ~99% |

## Notes on image verification

The `verify_with_images.py` script sends each page image alongside its transcription to Gemini for word-level correction. While promising in theory, testing showed a ~2.7:1 regression-to-improvement ratio — the model "confidently corrected" things that were already right, particularly:

- Proper nouns and names
- Domain-specific acronyms
- Dates and technical terms

The script includes safeguards (sanity checks for output size, incremental saves, resume capability), but results should be carefully compared before using verified output over proofread output.

## Costs

Gemini 2.5 Flash free tier: 10 requests/min, 250 requests/day. In dual OCR mode, a 104-page PDF needs ~312 API calls (over the daily limit — may need to split across days or use a paid plan). In single OCR mode, the full pipeline (OCR + proofreading) needs ~110 calls and fits within the free daily limit.

## License

MIT
