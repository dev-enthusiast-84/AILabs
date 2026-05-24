/**
 * Generates walkthrough demo questions from the content of the sample file.
 * Questions are derived from the document's actual headings and definition
 * sentences so they remain answerable whenever the sample content changes.
 */
import fs from 'node:fs'
import path from 'node:path'

// ── Section-header question extraction ────────────────────────────────────────

/**
 * Turns a numbered section heading into a plain question.
 * e.g. "2.1 The Knowledge Cutoff Problem" → "What is the Knowledge Cutoff Problem?"
 *      "3.4 How Does HyDE Work?" → "How Does HyDE Work?"
 */
function headingToQuestion(heading: string): string {
  const stripped = heading.trim().replace(/^\d+(\.\d+)*\s+/, '').trim()
  if (/^(What|How|Why|When|Where|Which|Who)\b/i.test(stripped) && stripped.endsWith('?')) {
    return stripped
  }
  // Detect "X Problem / X Approach / X Concepts" patterns → "What is X?"
  return `What is ${stripped.charAt(0).toLowerCase()}${stripped.slice(1)}?`
}

function extractHeadingQuestions(content: string): string[] {
  const lines = content.split('\n')
  const questions: string[] = []

  for (const line of lines) {
    const trimmed = line.trim()
    // Match numbered headings like "2.1 Something" or "SECTION 3: ..."
    const numbered = trimmed.match(/^\d+\.\d+\s+(.{10,80})$/)
    if (numbered) {
      const q = headingToQuestion(numbered[1])
      if (q && !questions.includes(q)) questions.push(q)
    }
    // Match "What is X?" / "How does X?" style headings already phrased as questions
    const asQuestion = trimmed.match(/^(What|How|Why)\s+.{10,80}\?$/i)
    if (asQuestion && !questions.includes(trimmed)) questions.push(trimmed)
  }

  return questions
}

// ── Definition-sentence extraction ────────────────────────────────────────────

/**
 * Finds sentences matching "X is/refers to/means Y" and converts them to
 * "What is X?" questions so we get granular fact-retrieval queries.
 */
function extractDefinitionQuestions(content: string): string[] {
  const questions: string[] = []
  // Matches: capitalized phrase (1–5 words) + "is" / "refers to" / "means"
  const pattern = /\b([A-Z][A-Za-z0-9-]+(?:\s+[A-Za-z0-9-]+){0,4})\s+(?:is|refers to|means|describes)\s+[a-z]/g
  let match: RegExpExecArray | null
  while ((match = pattern.exec(content)) !== null) {
    const subject = match[1].trim()
    const wordCount = subject.split(/\s+/).length
    if (wordCount >= 1 && wordCount <= 5 && subject.length >= 3) {
      const q = `What is ${subject}?`
      if (!questions.includes(q)) questions.push(q)
    }
  }
  return questions
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
}

/**
 * Derives 5 answerable walkthrough questions from the sample document.
 * Preference order: section-heading questions → definition questions → fallbacks.
 */
export function generateWalkthroughQuestions(uploadFilePath: string): WalkthroughQuestions {
  let content = ''
  const txtCandidates = [
    uploadFilePath.replace(/\.pdf$/i, '.txt'),
    path.resolve(path.dirname(uploadFilePath), 'sample.txt'),
    path.resolve(process.cwd(), '..', 'sample-data', 'sample.txt'),
  ]

  for (const candidate of txtCandidates) {
    try {
      content = fs.readFileSync(candidate, 'utf-8')
      break
    } catch {
      // try next candidate
    }
  }

  const headingQs = extractHeadingQuestions(content.slice(0, 40_000))
  const definitionQs = extractDefinitionQuestions(content.slice(0, 40_000))

  // Merge: heading questions first (more specific), then definition questions
  const allQuestions = [...headingQs, ...definitionQs].filter(
    (q, i, arr) => arr.indexOf(q) === i,
  )

  const FALLBACKS = [
    'What is Retrieval-Augmented Generation?',
    'What are the main stages of the RAG pipeline?',
    'How does the agentic RAG workflow differ from simple RAG?',
    'What file formats does the ingestion pipeline support?',
    'What is a vector store and how is it used in RAG?',
  ]

  while (allQuestions.length < 5) {
    const fb = FALLBACKS[allQuestions.length]
    if (fb && !allQuestions.includes(fb)) allQuestions.push(fb)
    else allQuestions.push(`Question ${allQuestions.length + 1}`)
  }

  return {
    simpleText:   allQuestions[0],
    agenticText:  allQuestions[1],
    voiceSimple:  allQuestions[2],
    voiceAgentic: allQuestions[3],
    multilingual: allQuestions[4],
  }
}
