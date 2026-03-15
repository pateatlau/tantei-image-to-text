# Tantei - Handwritten PDF to Markdown

Converts handwritten PDF documents into structured Markdown text using Google Gemini 2.5 Flash.

## Why Gemini?

Traditional OCR engines (Tesseract, Google Cloud Vision, TrOCR) struggle with cursive handwriting. Gemini is a large multimodal model that understands handwriting in context, producing ~95%+ accuracy on legible English handwriting.

The free tier (250 requests/day) is sufficient for most documents.

## Prerequisites

- **Python 3.10+** (for Python version) OR **Node.js 18+** (for TypeScript version)
- macOS / Linux
- [Poppler](https://poppler.freedesktop.org/) for PDF rendering
- A Google Gemini API key (free)

## Setup

### 1. Install Poppler

```bash
# macOS
brew install poppler

# Ubuntu/Debian
sudo apt-get install poppler-utils
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

Place your PDF in the project directory as `book.pdf`, then run:

### Python version
```bash
python ocr_book.py
```

### TypeScript version
```bash
npm install
npm run dev    # or: npm run build && npm start
```

Output is saved to `output.md`.

### Configuration

Edit the constants at the top of `ocr_book.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `PDF_PATH` | `book.pdf` | Input PDF file |
| `OUTPUT_PATH` | `output.md` | Output Markdown file |
| `OCR_DPI` | `300` | DPI for PDF rendering |
| `MAX_PAGES` | `5` | Pages to process (`None` for all) |
| `MODEL_NAME` | `gemini-2.5-flash` | Gemini model to use |
| `REQUESTS_PER_MINUTE` | `9` | Rate limit (free tier allows 10) |

### Processing all pages

Set `MAX_PAGES = None` in `ocr_book.py`, then run. For a 150-page PDF, expect ~25 minutes (rate-limited to 9 pages/minute).

## Output format

```markdown
## Page 1

# ETHICS IN ADMINISTRATION + PROBITY + GOVERNANCE

## I. Public Administration
1. Public Services, Role of Civil Services in Democracy.
   - Conflict areas between Civil Services and Politicians
2. Issues with Civil Services in India,
   Civil Services Reforms in India
```

## How it works

1. **PDF to images** - Converts each page to a 300 DPI image using `pdf2image` (poppler)
2. **Gemini OCR** - Sends each page image to Gemini 2.5 Flash with a domain-aware prompt
3. **Post-processing** - Strips code fences, removes duplicate lines
4. **Markdown output** - Writes structured output with page separators

The OCR prompt includes domain context (Indian civil services, ethics, governance) to help the model resolve ambiguous handwriting.

## Costs

Gemini 2.5 Flash free tier: 10 requests/min, 250 requests/day. A 150-page PDF fits within the free daily limit.

## License

MIT
