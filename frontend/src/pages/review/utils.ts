import type { ReviewItem } from '../../types'
import type { WordGroup, MnemonicData } from './types'

export function groupByWord(items: ReviewItem[]): WordGroup[] {
  const map = new Map<number, WordGroup>()
  for (const item of items) {
    const wid = item.word_id
    if (!map.has(wid)) {
      map.set(wid, { word_id: wid, word_name: item.word?.word ?? '', items: [] })
    }
    map.get(wid)!.items.push(item)
  }
  return Array.from(map.values())
}

export function parseMnemonicJson(content: string): MnemonicData | null {
  if (!content) return null
  try {
    const data = JSON.parse(content)
    if (data && typeof data === 'object' && 'formula' in data) return data as MnemonicData
  } catch { /* not JSON */ }
  return null
}

export function isMnemonicDim(dim: string): boolean {
  return dim.startsWith('mnemonic_')
}

export function parseMnemonic(content: string): {
  formula: string
  chant: string
  script: string
  exam_sentence: string
  exam_sentence_translation: string
} {
  const empty = { formula: '', chant: '', script: '', exam_sentence: '', exam_sentence_translation: '' }
  if (!content) return empty
  try {
    const data = JSON.parse(content)
    if (data && typeof data === 'object' && 'formula' in data) {
      return {
        formula: data.formula ?? '',
        chant: data.chant ?? '',
        script: data.script ?? '',
        exam_sentence: data.exam_sentence ?? '',
        exam_sentence_translation: data.exam_sentence_translation ?? '',
      }
    }
  } catch { /* fallback to regex */ }
  const formulaMatch = content.match(/\[核心公式\]\s*([\s\S]*?)(?=\[助记口诀\]|$)/)
  const chantMatch = content.match(/\[助记口诀\]\s*([\s\S]*?)(?=\[老师话术\]|$)/)
  const scriptMatch = content.match(/\[老师话术\]\s*([\s\S]*?)$/)
  return {
    formula: formulaMatch?.[1]?.trim() ?? '',
    chant: chantMatch?.[1]?.trim() ?? '',
    script: scriptMatch?.[1]?.trim() ?? '',
    exam_sentence: '',
    exam_sentence_translation: '',
  }
}

export function buildMnemonicJson(
  formula: string,
  chant: string,
  script: string,
  examSentence?: string,
  examSentenceTranslation?: string,
): string {
  if (examSentence !== undefined || examSentenceTranslation !== undefined) {
    return JSON.stringify({
      formula, chant, script,
      exam_sentence: examSentence ?? '',
      exam_sentence_translation: examSentenceTranslation ?? '',
    })
  }
  return JSON.stringify({ formula, chant, script })
}
