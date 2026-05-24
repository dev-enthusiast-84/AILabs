/**
 * Generates walkthrough demo questions from the actual content of the uploaded
 * file(s) so queries are relevant to whatever documents are indexed.
 *
 * Two input modes:
 *
 *   generateWalkthroughQuestions(filePath)          — guest: single TXT file path
 *   generateWalkthroughQuestions(filePaths[])       — multi-file: array of paths
 *   generateWalkthroughQuestions(demoDocs[])        — admin walkthrough: in-memory DemoDoc objects
 *
 * For TXT/CSV the file is read as UTF-8.
 * For XLSX the content is extracted with SheetJS (sheet_to_txt).
 * For PDF the text is extracted with pdf-parse (PDFParse class) so questions
 * are derived from the PDF's own content, not a companion TXT file.
 *
 * Works for both local and remote deployments in guest and admin mode.
 */
import fs from 'node:fs'
import path from 'node:path'
import { PDFParse } from 'pdf-parse'
import * as XLSX from 'xlsx'
import type { DemoDoc } from './demo-docs'

// ── Section-header question extraction ────────────────────────────────────────

/**
 * Turns a section heading into a semantically rich, open-ended question.
 * Rotates through four phrasings so consecutive slots get diverse query types —
 * each phrasing exercises a different retrieval path in the hybrid pipeline:
 *   "What is …?"     → broad concept lookup (vector similarity)
 *   "How does … work?" → procedural / explanatory (semantic + BM25)
 *   "Why is … important?" → reasoning / implication (semantic)
 *   "What are the key aspects of …?" → multi-facet summary (hybrid)
 */
function headingToQuestion(heading: string, variant = 0): string {
  const stripped = heading.trim().replace(/^\d+(\.\d+)*\s+/, '').trim()
  // Keep the heading if it is already a well-formed question
  if (/^(What|How|Why|When|Where|Which|Who)\b/i.test(stripped) && stripped.endsWith('?')) {
    return stripped
  }
  const lc = stripped.charAt(0).toLowerCase() + stripped.slice(1)
  const templates = [
    `What is ${lc}?`,
    `How does ${lc} work in practice?`,
    `Why is ${lc} important?`,
    `What are the key aspects of ${lc}?`,
  ]
  return templates[variant % templates.length]
}

function extractHeadingQuestions(content: string): string[] {
  const lines = content.split('\n')
  const questions: string[] = []
  let variant = 0

  for (const line of lines) {
    const trimmed = line.trim()
    const numbered = trimmed.match(/^\d+(\.\d+)*\s+(.{10,80})$/)
    if (numbered) {
      const q = headingToQuestion(numbered[2], variant++)
      if (q && !questions.includes(q)) questions.push(q)
    }
    // Lines already phrased as questions — keep as-is
    const asQuestion = trimmed.match(/^(What|How|Why|Describe|Explain)\s+.{10,80}\?$/i)
    if (asQuestion && !questions.includes(trimmed)) questions.push(trimmed)
  }

  return questions
}

// ── Definition-sentence extraction ────────────────────────────────────────────

/**
 * Generates semantically varied questions for each defined concept:
 * rotates through "What is", "How does … work", "Why is … used",
 * "What role does … play" — so different query phrasings exercise both
 * vector and keyword retrieval arms of the hybrid pipeline.
 */
function extractDefinitionQuestions(content: string): string[] {
  const questions: string[] = []
  const pattern = /\b([A-Z][A-Za-z0-9-]+(?:\s+[A-Za-z0-9-]+){0,4})\s+(?:is|refers to|means|describes)\s+[a-z]/g
  const templates = [
    (s: string) => `What is ${s}?`,
    (s: string) => `How does ${s} work?`,
    (s: string) => `Why is ${s} used?`,
    (s: string) => `What role does ${s} play?`,
  ]
  let i = 0
  let match: RegExpExecArray | null
  while ((match = pattern.exec(content)) !== null) {
    const subject = match[1].trim()
    const wordCount = subject.split(/\s+/).length
    if (wordCount >= 1 && wordCount <= 5 && subject.length >= 3) {
      const q = templates[i % templates.length](subject)
      if (!questions.includes(q)) { questions.push(q); i++ }
    }
  }
  return questions
}

// ── CSV column-label extraction ────────────────────────────────────────────────

/**
 * For CSV/XLSX files, builds open-ended questions from header and value cells
 * so the hybrid pipeline can retrieve matching rows via both BM25 and semantic
 * similarity rather than an exact string lookup.
 */
function extractCsvQuestions(content: string): string[] {
  const lines = content.split('\n').filter(l => l.trim())
  if (lines.length < 2) return []
  const headers = lines[0].split(',').map(h => h.replace(/^"|"$/g, '').trim())
  const questions: string[] = []

  const textCols = headers
    .map((h, i) => ({ h, i }))
    .filter(({ h }) => /name|title|description|summary|policy|feature|product|service|benefit|role|department/i.test(h))

  // Two templates — both use only values from the document (header name + cell value)
  const colTemplates: Array<(h: string, v: string) => string> = [
    (_h, v) => `What are the details about ${v}?`,
    (h, v) => `How is ${v} described in the ${h.toLowerCase()}?`,
  ]
  let t = 0

  for (const { h, i } of textCols.slice(0, 3)) {
    for (const row of lines.slice(1, 5)) {
      const cells = row.split(',').map(c => c.replace(/^"|"$/g, '').trim())
      const val = cells[i] ?? ''
      if (val.length >= 8 && !/^\d/.test(val)) {
        const q = colTemplates[t % colTemplates.length](h, val.slice(0, 50))
        if (!questions.includes(q)) { questions.push(q); t++ }
      }
    }
  }

  return questions
}

// ── Text extraction ────────────────────────────────────────────────────────────

async function extractTextFromBuffer(buf: Buffer, ext: string): Promise<string> {
  if (ext === '.pdf') {
    try {
      const parser = new PDFParse({ data: new Uint8Array(buf) })
      const result = await parser.getText()
      if (result.text && result.text.trim().length > 100) return result.text
    } catch { /* fall through */ }
    return ''
  }

  if (ext === '.xlsx') {
    try {
      const wb = XLSX.read(buf, { type: 'buffer' })
      const sheetName = wb.SheetNames[0]
      const ws = wb.Sheets[sheetName]
      return XLSX.utils.sheet_to_txt(ws)
    } catch { return '' }
  }

  // txt / csv: treat as UTF-8
  return buf.toString('utf-8')
}

async function extractTextFromFile(filePath: string): Promise<string> {
  const ext = path.extname(filePath).toLowerCase()

  if (ext === '.pdf') {
    try {
      const buf = fs.readFileSync(filePath)
      const text = await extractTextFromBuffer(Buffer.from(buf), '.pdf')
      if (text) return text
    } catch { /* fall through */ }
    // Fallback: companion TXT in the same directory
    const companions = [
      filePath.replace(/\.pdf$/i, '.txt'),
      path.resolve(path.dirname(filePath), 'sample.txt'),
    ]
    for (const c of companions) {
      try {
        const t = fs.readFileSync(c, 'utf-8')
        if (t.trim().length > 50) return t
      } catch { /* try next */ }
    }
    return ''
  }

  if (ext === '.xlsx') {
    try {
      const buf = fs.readFileSync(filePath)
      return extractTextFromBuffer(buf, '.xlsx')
    } catch { return '' }
  }

  try {
    return fs.readFileSync(filePath, 'utf-8')
  } catch {
    return ''
  }
}

// ── Negative query — intentionally out of scope ───────────────────────────────

/**
 * Returns a question that is guaranteed to be outside any indexed enterprise document.
 * Uses NO content from the document so the hybrid retriever finds nothing and the
 * pipeline returns an honest "not found" response.
 *
 * Domain strings are purely structural placeholders — no domain term appears in
 * any typical enterprise document (HR, finance, tech reports, employee data).
 * Content length is used only as a stable index to vary across different documents;
 * nothing from the document text enters the question.
 */
function deriveNegativeQuery(content: string): string {
  const outOfScopeDomains = [
    'deep-sea bioluminescent organisms',
    'ancient Mesopotamian cuneiform tablets',
    'quantum chromodynamics particle collisions',
    'tectonic subduction zone geology',
  ]
  const domain = outOfScopeDomains[content.length % outOfScopeDomains.length]
  return `What are the documented findings on ${domain}?`
}

// ── Per-source question list ───────────────────────────────────────────────────

function questionsFromContent(content: string, ext: string): string[] {
  let candidates: string[]
  if (ext === '.csv') {
    candidates = [
      ...extractCsvQuestions(content),
      ...extractDefinitionQuestions(content.slice(0, 20_000)),
    ]
  } else {
    candidates = [
      ...extractHeadingQuestions(content.slice(0, 40_000)),
      ...extractDefinitionQuestions(content.slice(0, 40_000)),
    ]
  }
  return candidates.filter((q, i, arr) => arr.indexOf(q) === i)
}


async function questionsFromDoc(doc: DemoDoc): Promise<string[]> {
  const ext = path.extname(doc.name).toLowerCase()
  const buf = Buffer.isBuffer(doc.content)
    ? doc.content
    : Buffer.from(doc.content as string, 'utf-8')
  const content = await extractTextFromBuffer(buf, ext)
  return questionsFromContent(content, ext)
}

// ── Public API ─────────────────────────────────────────────────────────────────

export interface WalkthroughQuestions {
  /** Used for Simple RAG text query */
  simpleText: string
  /** Used for Agentic RAG text query */
  agenticText: string
  /** Used for Simple RAG voice query */
  voiceSimple: string
  /** Used for Agentic RAG voice query */
  voiceAgentic: string
  /** Used for multilingual query (in English; the app translates the response) */
  multilingual: string
  /** Intentionally out-of-scope — demonstrates the pipeline's honest "not found" response */
  negativeQuery: string
}

/**
 * Returns the most probable positive-response question from the list.
 * Scores each candidate by specificity (prefers 30–80 char questions that
 * start with "What is" or "How does" and contain a named subject).
 * `index` selects among equally-scored candidates so multiple slots can each
 * draw a distinct question from the same pool.
 */
/**
 * Selects the most probable positive-response question from `list` using only
 * structural signals — no hardcoded domain terms or fallback strings.
 * Scoring criteria (all derived from question shape, not content):
 *   +3  length 30–80 chars (specific enough to retrieve, not so long it overloads)
 *   +1  length 15–29 chars (acceptable but less specific)
 *   +2  opens with an interrogative (What/How/Why/Describe/Explain)
 *   +1  contains at least one capitalised named token after the first word
 *       (suggests the question references a concrete subject from the document)
 * `index` offsets into the sorted list so each call slot gets a distinct question.
 * Returns empty string when the list is empty — callers fall back to UI suggestions.
 */
function pick(list: string[], index = 0): string {
  if (!list.length) return ''
  const scored = list.map((q) => {
    let score = 0
    if (q.length >= 30 && q.length <= 80) score += 3
    else if (q.length >= 15 && q.length < 30) score += 1
    if (/^(What|How|Why|Describe|Explain)\b/i.test(q)) score += 2
    if (/[A-Z][a-z]/.test(q.slice(8))) score += 1
    return { q, score }
  })
  scored.sort((a, b) => b.score - a.score)
  return scored[index % scored.length]?.q ?? list[0]
}

/**
 * Derives answerable walkthrough questions from the uploaded document(s).
 *
 * Accepted inputs:
 *   string           — guest: single file path (TXT)
 *   string[]         — multi-path: array of file paths
 *   DemoDoc[]        — admin walkthrough: in-memory document objects
 *                      (works for both local and remote deployments)
 *
 * For multiple documents each query slot is assigned the best question from a
 * different document so the walkthrough exercises retrieval across diverse
 * content types and topics.
 */
export async function generateWalkthroughQuestions(
  input: string | string[] | DemoDoc[],
): Promise<WalkthroughQuestions> {
  // In-memory DemoDoc[] path (admin walkthrough — local or remote)
  if (Array.isArray(input) && input.length > 0 && typeof (input[0] as DemoDoc).content !== 'undefined') {
    const docs = input as DemoDoc[]
    const contents = await Promise.all(docs.map(async (d) => {
      const ext = path.extname(d.name).toLowerCase()
      const buf = Buffer.isBuffer(d.content) ? d.content : Buffer.from(d.content as string, 'utf-8')
      return extractTextFromBuffer(buf, ext)
    }))
    const perDoc = await Promise.all(docs.map(questionsFromDoc))
    const all = perDoc.flat()
    const primaryContent = contents[0] ?? ''
    return {
      // Each slot draws from a different document so each demo query covers
      // distinct content — slots 0-3 map to TXT/CSV/XLSX/PDF respectively.
      simpleText:    pick(perDoc[0] ?? all, 0),
      agenticText:   pick(perDoc[1] ?? all, 0),
      voiceSimple:   pick(perDoc[2] ?? all, 0),
      voiceAgentic:  pick(perDoc[3] ?? all, 0),
      multilingual:  pick(perDoc[0] ?? all, 0),
      negativeQuery: deriveNegativeQuery(primaryContent),
    }
  }

  // File-path path (guest single TXT, or multi-path array)
  const paths = Array.isArray(input) ? input as string[] : [input as string]

  if (paths.length === 1) {
    const content = await extractTextFromFile(paths[0])
    const qs = questionsFromContent(content, path.extname(paths[0]).toLowerCase())
    return {
      simpleText:    pick(qs, 0),
      agenticText:   pick(qs, 0),
      voiceSimple:   pick(qs, 1),
      voiceAgentic:  pick(qs, 1),
      multilingual:  pick(qs, 0),
      negativeQuery: deriveNegativeQuery(content),
    }
  }

  const contents = await Promise.all(paths.map(extractTextFromFile))
  const perFile = contents.map((c, i) => questionsFromContent(c, path.extname(paths[i]).toLowerCase()))
  const all = perFile.flat()
  return {
    simpleText:    pick(perFile[0] ?? all, 0),
    agenticText:   pick(perFile[0] ?? all, 0),
    voiceSimple:   pick(perFile[1] ?? all, 0),
    voiceAgentic:  pick(perFile[1] ?? all, 0),
    multilingual:  pick(perFile[0] ?? all, 0),
    negativeQuery: deriveNegativeQuery(contents[0] ?? ''),
  }
}
