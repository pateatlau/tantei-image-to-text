/**
 * Handwritten PDF → Markdown OCR Pipeline (TypeScript)
 * ======================================================
 * Converts a handwritten PDF into structured Markdown using Google Gemini 2.5 Flash.
 *
 * Usage:
 *   npm install
 *   npm run build
 *   npm start
 *
 * Or with tsx:
 *   npm install -g tsx
 *   tsx ocr_book.ts
 */

import * as fs from 'fs';
import * as path from 'path';
import { promisify } from 'util';
import { exec } from 'child_process';
import dotenv from 'dotenv';
import { GoogleGenerativeAI } from '@google/generative-ai';
import cliProgress from 'cli-progress';

dotenv.config();

const execAsync = promisify(exec);

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------
const PDF_PATH = 'book.pdf';
const OUTPUT_PATH = 'output.md';
const OCR_DPI = 300;
const TEMP_DIR = './temp_images';
const MODEL_NAME = 'gemini-2.5-flash';
const MAX_PAGES: number | null = null; // Set to a number to limit pages
const REQUESTS_PER_MINUTE = 9;

// ---------------------------------------------------------------------------
// OCR Prompt
// ---------------------------------------------------------------------------
const OCR_PROMPT = `You are an expert OCR system specializing in handwritten documents about Indian public administration, civil services, ethics, and governance.

Extract ALL handwritten text from this image exactly as written.

DOMAIN CONTEXT (use this to resolve ambiguous handwriting):
This document covers: Ethics in Administration, Probity, Governance, Civil Services, Public Administration, Indian Administrative Service (IAS), Indian Police Service (IPS), Indian Forest Service (IFS), Accountability, Transparency, E-governance, RTI (Right to Information), Citizen Charters, Social Audit, Sevottam Model, KSRTC, NERCORMP, SHGs (Self Help Groups).

TRANSCRIPTION RULES:
- Read every word carefully. Do NOT guess or hallucinate — if a word is unclear, transcribe your best reading of it
- Do NOT duplicate words or phrases — each word should appear exactly once
- Preserve abbreviations as written (e.g., "CS" for Civil Services, "WF" for Way Forward, "PA" for Public Administration, "wc" for work culture)
- Indian proper names: read carefully — common names include Shenoy, Sabharwal, Pragyan Das, Narahari, Yadav, Shaikh
- Do NOT add words that aren't in the image

MARKDOWN FORMATTING:
- # for main headings/titles (text in boxes, large underlined text, ALL CAPS titles)
- ## for section headings (Roman numeral prefixed: I., II., III., IV., V., VI., VII.)
- Numbered lists (1. 2. 3.) for circled numbers ①②③ or numbered points
- Bullet lists (- ) for sub-points marked with circles, arrows, dashes, or dots
- Markdown tables (| col1 | col2 |) if tabular content is present
- Indented sub-items (2 spaces) under their parent item
- If text is crossed out, skip it
- If arrows point to inserted text, incorporate it in the logical reading position

OUTPUT: Only the extracted text in Markdown. No commentary, no explanation, no code fences.`;

// ---------------------------------------------------------------------------
// Helper Functions
// ---------------------------------------------------------------------------

/** Get total page count from PDF */
async function getPdfPageCount(pdfPath: string): Promise<number> {
  const { stdout } = await execAsync(`pdfinfo "${pdfPath}"`);
  const match = stdout.match(/Pages:\s+(\d+)/);
  if (!match) throw new Error('Could not determine page count');
  return parseInt(match[1], 10);
}

/** Convert a single PDF page to PNG using pdftoppm (part of poppler) */
async function pdfPageToImage(
  pdfPath: string,
  pageNumber: number,
  dpi: number,
  outputDir: string
): Promise<string> {
  const outputPath = path.join(outputDir, `page_${pageNumber}.png`);
  const cmd = `pdftoppm -png -r ${dpi} -f ${pageNumber} -l ${pageNumber} -singlefile "${pdfPath}" "${path.join(outputDir, `page_${pageNumber}`)}"`
  await execAsync(cmd);
  return outputPath;
}

/** OCR a single page image using Gemini */
async function ocrPage(
  genAI: GoogleGenerativeAI,
  imagePath: string
): Promise<string> {
  const model = genAI.getGenerativeModel({ model: MODEL_NAME });

  const imageData = fs.readFileSync(imagePath);
  const base64Image = imageData.toString('base64');

  const result = await model.generateContent([
    OCR_PROMPT,
    {
      inlineData: {
        data: base64Image,
        mimeType: 'image/png',
      },
    },
  ], {
    generationConfig: {
      temperature: 0,
    },
  });

  const response = await result.response;
  const text = response.text();
  return postprocess(text);
}

/** Post-process OCR output */
function postprocess(text: string): string {
  // Strip code fences
  text = text.replace(/^```(?:markdown)?\s*\n/gm, '');
  text = text.replace(/\n```\s*$/gm, '');

  // Remove duplicate consecutive lines
  const lines = text.split('\n');
  const deduped: string[] = lines.length > 0 ? [lines[0]] : [];
  for (let i = 1; i < lines.length; i++) {
    if (lines[i].trim() !== deduped[deduped.length - 1].trim()) {
      deduped.push(lines[i]);
    }
  }

  return deduped.join('\n');
}

/** Rate limiter */
function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function rateLimitDelay(pageIndex: number, startTime: number): Promise<void> {
  if (pageIndex === 0) return;
  const elapsed = Date.now() - startTime;
  const expectedElapsed = pageIndex * (60000 / REQUESTS_PER_MINUTE);
  if (elapsed < expectedElapsed) {
    await sleep(expectedElapsed - elapsed);
  }
}

// ---------------------------------------------------------------------------
// Main Pipeline
// ---------------------------------------------------------------------------
async function main() {
  // Validate environment
  if (!fs.existsSync(PDF_PATH)) {
    console.error(`Error: Input PDF not found: ${PDF_PATH}`);
    process.exit(1);
  }

  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    console.error('Error: GEMINI_API_KEY is not set.');
    console.error('Get a key from: https://aistudio.google.com/apikey');
    console.error('Then add it to .env file');
    process.exit(1);
  }

  const genAI = new GoogleGenerativeAI(apiKey);

  // Get page count
  let totalPages = await getPdfPageCount(PDF_PATH);
  if (MAX_PAGES !== null) {
    totalPages = Math.min(totalPages, MAX_PAGES);
  }
  console.log(`PDF has ${totalPages} page(s) to process.`);
  console.log(`Using model: ${MODEL_NAME}`);

  // Create temp directory
  if (!fs.existsSync(TEMP_DIR)) {
    fs.mkdirSync(TEMP_DIR);
  }

  const results: { [page: number]: string } = {};
  const progressBar = new cliProgress.SingleBar({}, cliProgress.Presets.shades_classic);
  progressBar.start(totalPages, 0);

  const startTime = Date.now();

  for (let pageNum = 1; pageNum <= totalPages; pageNum++) {
    await rateLimitDelay(pageNum - 1, startTime);

    try {
      // Convert PDF page to image
      const imagePath = await pdfPageToImage(PDF_PATH, pageNum, OCR_DPI, TEMP_DIR);

      // OCR the image
      const text = await ocrPage(genAI, imagePath);
      results[pageNum] = text;

      // Cleanup temp image
      fs.unlinkSync(imagePath);
    } catch (error) {
      console.error(`\nError on page ${pageNum}:`, error);
      results[pageNum] = `*[OCR error: ${error}]*`;
    }

    progressBar.update(pageNum);
  }

  progressBar.stop();

  // Write output
  const outputLines: string[] = [];
  for (let pageNum = 1; pageNum <= totalPages; pageNum++) {
    outputLines.push(`## Page ${pageNum}\n`);
    outputLines.push((results[pageNum] || '*[Missing]*').trim() + '\n');
  }

  fs.writeFileSync(OUTPUT_PATH, outputLines.join('\n'), 'utf-8');

  // Cleanup temp directory
  if (fs.existsSync(TEMP_DIR)) {
    fs.rmSync(TEMP_DIR, { recursive: true });
  }

  const elapsed = (Date.now() - startTime) / 1000;
  console.log(`\nDone. Output saved to ${OUTPUT_PATH}`);
  console.log(`Total time: ${elapsed.toFixed(0)}s (${(elapsed / totalPages).toFixed(1)}s per page)`);
}

main().catch(console.error);
