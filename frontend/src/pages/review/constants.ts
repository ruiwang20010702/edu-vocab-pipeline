export const DIMENSION_LABELS: Record<string, string> = {
  meaning: '释义',
  phonetic: '音标',
  syllable: '音节',
  chunk: '语块',
  sentence: '例句',
  mnemonic_root_affix: '词根词缀',
  mnemonic_word_in_word: '词中词',
  mnemonic_sound_meaning: '音义联想',
  mnemonic_exam_app: '考试应用',
}

export const FILTER_GROUPS = [
  { group: '语义 Meaning', items: [
    { value: 'meaning', label: '释义问题' },
  ]},
  { group: '语境 Context', items: [
    { value: 'chunk', label: '语块问题' },
    { value: 'sentence', label: '例句问题' },
  ]},
  { group: '助记 Mnemonic', items: [
    { value: 'mnemonic', label: '助记问题' },
  ]},
]

export const STATUS_BADGE: Record<string, { bg: string; text: string; label: string }> = {
  approved: { bg: 'bg-green-50 border-green-200', text: 'text-green-600', label: '已通过' },
  rejected: { bg: 'bg-slate-50 border-slate-200', text: 'text-slate-400', label: '不适用' },
  layer1_failed: { bg: 'bg-rose-50 border-rose-200', text: 'text-rose-600', label: '异常' },
  layer2_failed: { bg: 'bg-rose-50 border-rose-200', text: 'text-rose-600', label: '异常' },
  layer1_passed: { bg: 'bg-blue-50 border-blue-200', text: 'text-blue-600', label: '质检中' },
  layer2_passed: { bg: 'bg-blue-50 border-blue-200', text: 'text-blue-600', label: '质检中' },
  pending: { bg: 'bg-slate-50 border-slate-200', text: 'text-slate-400', label: '待处理' },
}

export const ALL_MNEMONIC_DIMS = [
  'mnemonic_root_affix', 'mnemonic_word_in_word',
  'mnemonic_sound_meaning', 'mnemonic_exam_app',
] as const

export const MNEMONIC_TYPE_LABELS: Record<string, string> = {
  mnemonic_root_affix: '词根词缀',
  mnemonic_word_in_word: '词中词',
  mnemonic_sound_meaning: '音义联想',
  mnemonic_exam_app: '考试应用',
}
