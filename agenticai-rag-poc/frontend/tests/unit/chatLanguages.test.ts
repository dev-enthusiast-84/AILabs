import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { CHAT_LANGUAGES, languageByCode } from '@/lib/chatLanguages'

describe('chat language contract', () => {
  it('matches the shared language source of truth', () => {
    const shared = JSON.parse(
      readFileSync(resolve(process.cwd(), '../shared/chat_languages.json'), 'utf8'),
    )

    expect(CHAT_LANGUAGES).toEqual(shared)
  })

  it('falls back to the first supported language for unknown codes', () => {
    expect(languageByCode('zz')).toBe(CHAT_LANGUAGES[0])
  })
})
