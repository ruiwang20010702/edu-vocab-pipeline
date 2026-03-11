import type { ReviewItem } from '../../types'

export interface WordGroup {
  word_id: number
  word_name: string
  items: ReviewItem[]
}

export type Tab = 'all' | 'can_retry' | 'must_manual'

export type QcIssue = { rule_id: string; field: string; message: string }

export interface MnemonicData { formula: string; chant: string; script: string }
