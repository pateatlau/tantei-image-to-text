# CLAUDE.md

## Project Overview

Tantei is a handwritten PDF to Markdown converter. It uses Google Gemini 2.5 Flash with a dual OCR strategy and disagreement resolution for high-accuracy transcription.

## Architecture

Multi-step pipeline:

```
PDF → images (300 DPI)
  → image preprocessing (grayscale, blur, upscale via OpenCV)
  → Gemini OCR Pass A (structure-focused prompt)
  → Gemini OCR Pass B (character-focused prompt)
  → disagreement resolver (image + both results → best reading)
  → named entity correction
  → proofreading (chunked, via Gemini)
  → Markdown post-processing (15 normalization steps)
  → Pandoc conversion (with reference DOCX template)
  → DOCX formatting (table borders, header, footer)
```

## Key Files

- `ocr_book.py` — Main OCR pipeline with dual OCR, preprocessing, and entity correction.
- `proofread.py` — Chunked proofreading via Gemini.
- `verify_with_images.py` — Optional image-aware verification (experimental).
- `postprocess_markdown.py` — Markdown normalization for clean DOCX rendering.
- `convert_to_docx.py` — Pandoc wrapper with reference template and extended Markdown support.
- `format_docx.py` — DOCX post-processing (table borders, header, footer).
- `reference.docx` — Pandoc reference template controlling DOCX styles.
- `.env` — Contains `GEMINI_API_KEY`. Never commit this.
- `requirements.txt` — Python dependencies.

## Development Notes

- `ocr_book.py` uses two OCR prompts (`OCR_PROMPT_A` and `OCR_PROMPT_B`) and a `RESOLVER_PROMPT`. Toggle dual mode with `ENABLE_DUAL_OCR`.
- Image preprocessing (grayscale + Gaussian blur + 1.3x upscale) is toggled with `ENABLE_PREPROCESSING`.
- `ENTITY_CORRECTIONS` dictionary in `ocr_book.py` maps common OCR misspellings to correct terms. Add domain-specific corrections there.
- `MAX_PAGES = None` processes all pages. Set to a small number for testing.
- Dual OCR uses 3 API calls per page (vs 1 for single pass). At 9 RPM, 104 pages takes ~86 min.
- Rate limiting is built in to stay within Gemini free tier (10 RPM). Adjust `REQUESTS_PER_MINUTE` if on a paid plan.
- `postprocess_markdown.py` runs 15 normalization steps including heading normalization, table inline list fixing, orphaned line joining, list nesting, and more.
- `convert_to_docx.py` uses `markdown+pipe_tables+grid_tables` input format with `--wrap=none --standalone`. It auto-detects `reference.docx` if present.

## Common Tasks

### Run the full pipeline
```bash
python ocr_book.py              # Dual OCR → output.md
python proofread.py              # Proofreading → output_proofread.md
python postprocess_markdown.py   # Normalize → output_final.md
python convert_to_docx.py        # Pandoc → output_final.docx
python format_docx.py            # Add borders/header/footer
```

### Run OCR in single-pass mode (faster)
Set `ENABLE_DUAL_OCR = False` in `ocr_book.py`.

### Change the input PDF
Update `PDF_PATH` at the top of `ocr_book.py`.

### Improve accuracy for a different domain
1. Update the `DOMAIN CONTEXT` section in both `OCR_PROMPT_A` and `OCR_PROMPT_B`.
2. Update `ENTITY_CORRECTIONS` with domain-specific proper nouns and terms.

## Things to Avoid

- Do not commit `.env`, `book.pdf`, `output.md`, `output_*.md`, `output_*.docx`, or any `.json` credential files.
- Do not remove rate limiting — the free tier will block requests.
- Do not use `temperature > 0` for OCR — deterministic output is critical for faithful transcription.
