/* ===== 数据层类型 ===== */

export interface Word {
  id: number
  word: string
  created_at: string
  updated_at: string
}

export interface Phonetic {
  id: number
  word_id: number
  ipa: string
  syllables: string
}

export interface Meaning {
  id: number
  word_id: number
  pos: string
  definition: string
  sources: Source[]
}

export interface Source {
  id: number
  meaning_id: number
  source_name: string
}

/* ===== 内容层类型 ===== */

export type ContentDimension = 'meaning' | 'phonetic' | 'syllable' | 'chunk' | 'sentence' | 'mnemonic'
export type QcStatus = 'pending' | 'layer1_passed' | 'layer1_failed' | 'layer2_passed' | 'layer2_failed' | 'approved' | 'rejected'

export interface ContentItem {
  id: number
  word_id: number
  meaning_id: number | null
  dimension: ContentDimension
  content: string
  content_cn: string | null
  qc_status: QcStatus
  retry_count: number
}

/* ===== 质检层类型 ===== */

export interface QualityIssue {
  id: number
  content_item_id: number
  rule_code: string
  field: string
  message: string
  severity: string
}

export interface ReviewItem {
  id: number
  content_item_id: number
  reason: string
  status: 'pending' | 'in_progress' | 'resolved'
  resolution: string | null
  content_item: ContentItem
  word: Word
  issues: QualityIssue[]
}

/* ===== 聚合视图类型 ===== */

export interface WordDetail extends Word {
  phonetics: Phonetic[]
  meanings: (Meaning & {
    chunk?: ContentItem
    sentence?: ContentItem
  })[]
  mnemonic?: ContentItem
  issues: QualityIssue[]
}

export interface BatchInfo {
  id: string
  name: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  total_words: number
  processed_words: number
  pass_rate: number | null
  created_at: string
}

export interface DashboardStats {
  total_words: number
  approved_count: number
  pending_count: number
  rejected_count: number
  pass_rate: number
}

/* ===== 认证类型 ===== */

export interface AuthUser {
  access_token: string
  user_name: string
  user_role: 'admin' | 'reviewer' | 'viewer'
}

/* ===== API 响应 ===== */

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  limit: number
}
