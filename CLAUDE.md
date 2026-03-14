# CLAUDE.md

## Project Overview

Tantei is a handwritten PDF to Markdown converter. It uses Google Gemini 2.5 Flash to OCR handwritten pages and output structured Markdown.

## Architecture

Single-script pipeline (`ocr_book.py`):
- PDF → images via `pdf2image` (poppler)
- Each page image → Gemini API → Markdown text
- Post-processing → final `output.md`

## Key Files

- `ocr_book.py` — Main script. All logic is in this one file.
- `.env` — Contains `GEMINI_API_KEY`. Never commit this.
- `requirements.txt` — Python dependencies.

## Development Notes

- The OCR prompt in `OCR_PROMPT` is domain-specific to Indian civil services/ethics/governance. For other document types, update the domain context section.
- `MAX_PAGES` is set to 5 for testing. Set to `None` for full runs.
- Rate limiting is built in to stay within Gemini free tier (10 RPM). Adjust `REQUESTS_PER_MINUTE` if on a paid plan.
- Post-processing (`postprocess()`) strips code fences and deduplicates lines. Add more cleanup rules there as needed.

## Common Tasks

### Run OCR on the full PDF
Set `MAX_PAGES = None` in `ocr_book.py` and run `python ocr_book.py`.

### Change the input PDF
Update `PDF_PATH` at the top of `ocr_book.py`.

### Improve accuracy for a different domain
Update the `DOMAIN CONTEXT` section in `OCR_PROMPT` with relevant terminology, proper nouns, and abbreviations for the new domain.

## Things to Avoid

- Do not commit `.env`, `book.pdf`, `output.md`, or any `.json` credential files.
- Do not remove rate limiting — the free tier will block requests.
- Do not use `temperature > 0` for OCR — deterministic output is critical for faithful transcription.
