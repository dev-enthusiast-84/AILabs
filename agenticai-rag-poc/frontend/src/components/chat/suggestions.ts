const STOP_WORDS = new Set([
  'about', 'after', 'again', 'also', 'their', 'there', 'these', 'those', 'through',
  'under', 'where', 'which', 'while', 'would', 'could', 'should', 'using', 'with',
  'from', 'into', 'this', 'that', 'than', 'then', 'they', 'them', 'were', 'been',
  'have', 'your', 'will', 'what', 'when', 'each', 'such', 'more', 'most', 'only',
  'some', 'other', 'over', 'page', 'document', 'documents', 'section', 'content',
  'uploaded', 'file', 'files', 'sheet', 'columns', 'rows', 'table',
  'because', 'therefore', 'however', 'strongest', 'theme', 'themes',
])

const WEAK_TERM_BOUNDARIES = new Set([
  'improve', 'improved', 'improves', 'increase', 'increased', 'decrease', 'decreased',
  'update', 'updated', 'include', 'included', 'includes', 'provide', 'provided',
  'provides', 'show', 'shows', 'shown', 'report', 'reported',
])

function titleCaseTerm(term: string): string {
  return term
    .split(' ')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function normalizeTerm(term: string): string {
  return term
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function isUsefulTerm(term: string): boolean {
  const words = normalizeTerm(term).split(/\s+/).filter(Boolean)
  if (words.length === 0 || words.length > 4) return false
  if (words.every((word) => STOP_WORDS.has(word) || /^\d+$/.test(word))) return false
  if (WEAK_TERM_BOUNDARIES.has(words[0]) || WEAK_TERM_BOUNDARIES.has(words[words.length - 1])) return false
  return words.some((word) => word.length >= 4 && !STOP_WORDS.has(word) && !/^\d+$/.test(word))
}

function addTerm(counts: Map<string, number>, term: string, weight = 1) {
  const normalized = normalizeTerm(term)
  if (!isUsefulTerm(normalized)) return
  counts.set(normalized, (counts.get(normalized) ?? 0) + weight)
}

function extractContentTerms(content: string): string[] {
  const counts = new Map<string, number>()
  const cleaned = content
    .replace(/\[[^\]]+\]/g, ' ')
    .replace(/\bColumns\s*\(\d+\):/gi, ' ')
    .replace(/\bRows:\s*\d+/gi, ' ')

  const capitalizedPhrases = cleaned.match(/\b[A-Z][A-Za-z0-9-]*(?:\s+(?:and|of|for|to|in|with|[A-Z][A-Za-z0-9-]*)){1,3}\b/g) ?? []
  for (const phrase of capitalizedPhrases) addTerm(counts, phrase, 3)

  const words = content
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, ' ')
    .split(/\s+/)
    .filter((word) => word.length >= 4 && !STOP_WORDS.has(word) && !/^\d+$/.test(word))

  for (let i = 0; i < words.length; i += 1) {
    addTerm(counts, words[i])
    if (i + 1 < words.length) addTerm(counts, `${words[i]} ${words[i + 1]}`, 2)
    if (i + 2 < words.length) addTerm(counts, `${words[i]} ${words[i + 1]} ${words[i + 2]}`, 2)
  }

  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].split(' ').length - b[0].split(' ').length || a[0].length - b[0].length)
    .map(([term]) => term)
    .reduce<string[]>((selected, term) => {
      const words = term.split(' ')
      if (words.length === 1) {
        if (selected.some((other) => other.includes(term) && other !== term)) return selected
      } else if (selected.some((other) => term.includes(other) || other.includes(term))) {
        return selected
      }
      selected.push(term)
      return selected
    }, [])
    .slice(0, 5)
    .map((term) => titleCaseTerm(term))
}

/** Build suggestions from uploaded document text, not file names. */
export function buildSuggestionsFromContent(contents: string[]): string[] {
  const combined = contents.join('\n').slice(0, 40_000)
  const terms = extractContentTerms(combined).filter((term) => term.split(' ').length >= 2)

  if (terms.length < 2) return []

  return terms.slice(0, 4).map((term) => `What details does the document provide about ${term}?`)
}
