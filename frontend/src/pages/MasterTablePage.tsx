import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import {
  Search, Download, ChevronLeft, ChevronRight, X, Loader2,
  CheckCircle2, AlertTriangle, MoreHorizontal, BookOpen, Lightbulb,
  Layers, Volume2, GraduationCap, Ban,
  ChevronDown, AlertCircle,
} from 'lucide-react'
import { api } from '../lib/api'
import type { WordDetail, PaginatedResponse, ContentItem } from '../types'

/* ===== 助记工具 ===== */

const MNEMONIC_TYPE_LABELS: Record<string, string> = {
  mnemonic_root_affix: '词根词缀',
  mnemonic_word_in_word: '词中词',
  mnemonic_sound_meaning: '音义联想',
  mnemonic_exam_app: '考试应用',
}

const ALL_MNEMONIC_DIMS = [
  'mnemonic_root_affix', 'mnemonic_word_in_word',
  'mnemonic_sound_meaning', 'mnemonic_exam_app',
] as const

function parseMnemonic(content: string): { formula: string; chant: string; script: string } {
  if (!content) return { formula: '', chant: '', script: '' }
  // JSON 格式优先
  try {
    const data = JSON.parse(content)
    if (data && typeof data === 'object' && 'formula' in data) {
      return { formula: data.formula ?? '', chant: data.chant ?? '', script: data.script ?? '' }
    }
  } catch { /* fallback to regex */ }
  // 旧格式兼容
  const formulaMatch = content.match(/\[核心公式\]\s*([\s\S]*?)(?=\[助记口诀\]|$)/)
  const chantMatch = content.match(/\[助记口诀\]\s*([\s\S]*?)(?=\[老师话术\]|$)/)
  const scriptMatch = content.match(/\[老师话术\]\s*([\s\S]*?)$/)
  return {
    formula: formulaMatch?.[1]?.trim() ?? '',
    chant: chantMatch?.[1]?.trim() ?? '',
    script: scriptMatch?.[1]?.trim() ?? '',
  }
}

/* ===== 导出就绪 ===== */

interface ExportReadiness {
  total_words: number
  approved_words: number
  ready: boolean
}

/* ===== 主组件 ===== */

export default function MasterTablePage() {
  const [words, setWords] = useState<WordDetail[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [selectedWordId, setSelectedWordId] = useState<number | null>(null)
  const [detailWord, setDetailWord] = useState<WordDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [exportInfo, setExportInfo] = useState<ExportReadiness | null>(null)
  const [exportLoading, setExportLoading] = useState(false)
  const limit = 50

  const loadWords = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ page: String(page), limit: String(limit) })
      if (search) params.set('q', search)
      const res = await api.get<PaginatedResponse<WordDetail>>(`/words?${params}`)
      setWords(res.items)
      setTotal(res.total)
    } catch {
      setWords([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadWords() }, [page])

  const handleSearch = () => { setPage(1); loadWords() }
  const totalPages = Math.max(1, Math.ceil(total / limit))

  const handleOpenDetail = async (wordId: number) => {
    setSelectedWordId(wordId)
    setDetailLoading(true)
    setDetailWord(null)
    try {
      const data = await api.get<WordDetail>(`/words/${wordId}`)
      setDetailWord(data)
    } catch {
      setDetailWord(null)
    } finally {
      setDetailLoading(false)
    }
  }

  const handleCloseDetail = () => {
    setSelectedWordId(null)
    setDetailWord(null)
  }

  const handleExport = async () => {
    setExportLoading(true)
    try {
      const data = await api.get<ExportReadiness>('/export/readiness')
      setExportInfo(data)
    } catch {
      setExportInfo(null)
    } finally {
      setExportLoading(false)
    }
  }

  const handleDownload = async () => {
    try {
      const data = await api.get<unknown[]>('/export/download')
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'vocab_export.json'
      a.click()
      URL.revokeObjectURL(url)
    } catch { /* ignore */ }
  }

  return (
    <div className="space-y-4">
      {/* 工具栏 */}
      <div className="flex items-center justify-between gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
            placeholder="搜索单词..."
            className="w-full pl-9 pr-3 py-2.5 bg-white/95 backdrop-blur-sm rounded-xl text-sm border border-white/80 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-200/50 placeholder:text-slate-400"
          />
        </div>
        <div className="flex items-center gap-2.5">
          <span className="text-xs text-white/70">{total} 条记录</span>
          <button
            onClick={handleExport}
            disabled={exportLoading}
            className="flex items-center gap-1.5 px-4 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-bold shadow-lg shadow-blue-600/20 hover:bg-blue-700 hover:-translate-y-0.5 active:scale-95 transition-all disabled:opacity-50"
          >
            {exportLoading ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
            导出
          </button>
        </div>
      </div>

      {/* 导出就绪 */}
      <AnimatePresence>
        {exportInfo && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="bg-white rounded-2xl p-4 border border-slate-200 shadow-sm"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                {exportInfo.ready ? <CheckCircle2 size={20} className="text-green-600" /> : <AlertTriangle size={20} className="text-yellow-600" />}
                <div>
                  <p className="text-slate-900 text-sm font-medium">{exportInfo.ready ? '数据就绪，可以导出' : '部分数据未审核通过'}</p>
                  <p className="text-slate-400 text-xs">已审核 {exportInfo.approved_words}/{exportInfo.total_words} 词</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {exportInfo.ready && (
                  <button onClick={handleDownload} className="flex items-center gap-1 px-4 py-1.5 bg-green-50 hover:bg-green-100 text-green-700 border border-green-200 rounded-xl text-sm transition-all">
                    <Download size={14} /> 下载 JSON
                  </button>
                )}
                <button onClick={() => setExportInfo(null)} className="text-slate-400 hover:text-slate-600"><X size={16} /></button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* 表格 */}
      <div className="bg-white rounded-2xl border border-white overflow-hidden shadow-sm">
        {loading ? (
          <div className="flex items-center justify-center py-20 gap-2 text-slate-400">
            <Loader2 className="animate-spin" size={20} />
            <span className="text-sm">加载中...</span>
          </div>
        ) : words.length === 0 ? (
          <div className="text-center text-slate-400 py-16 text-sm">暂无数据</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse min-w-[1800px]">
              <thead className="bg-slate-50 text-slate-400 text-[10px] uppercase tracking-wider">
                <tr>
                  <th className="px-5 py-3 font-semibold sticky left-0 bg-slate-50 z-10">单词</th>
                  <th className="px-5 py-3 font-semibold">音标</th>
                  <th className="px-5 py-3 font-semibold">音节</th>
                  <th className="px-5 py-3 font-semibold">词性/释义</th>
                  <th className="px-5 py-3 font-semibold">教材来源</th>
                  <th className="px-5 py-3 font-semibold">核心语块</th>
                  <th className="px-5 py-3 font-semibold">语块翻译</th>
                  <th className="px-5 py-3 font-semibold">例句</th>
                  <th className="px-5 py-3 font-semibold">例句翻译</th>
                  <th className="px-5 py-3 font-semibold">助记类型</th>
                  <th className="px-5 py-3 font-semibold">助记公式</th>
                  <th className="px-5 py-3 font-semibold">助记口诀</th>
                  <th className="px-5 py-3 font-semibold">老师话术</th>
                  <th className="px-5 py-3 font-semibold">创建时间</th>
                  <th className="px-5 py-3 font-semibold sticky right-0 bg-slate-50 z-10">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {words.map(w => {
                  const meanings = w.meanings ?? []
                  const rowCount = Math.max(meanings.length, 1)
                  const ipa = w.phonetics?.[0]?.ipa ?? ''
                  const syllables = w.syllable?.content ?? ''

                  if (meanings.length === 0) {
                    return (
                      <tr key={w.id} className="hover:bg-blue-50/30 transition-colors group">
                        <td className="px-5 py-3 sticky left-0 bg-white group-hover:bg-blue-50/30 transition-colors z-10">
                          <button onClick={() => handleOpenDetail(w.id)} className="font-bold text-slate-900 hover:text-blue-600 transition-colors cursor-pointer text-left">{w.word}</button>
                        </td>
                        <td className="px-5 py-3 font-mono text-xs text-slate-400">{ipa}</td>
                        <td className="px-5 py-3 text-xs text-slate-500">{syllables}</td>
                        <td className="px-5 py-3 text-xs text-slate-300 italic" colSpan={10}>暂无义项数据</td>
                        <td className="px-5 py-3 text-xs text-slate-400 whitespace-nowrap">{w.created_at ? new Date(w.created_at).toLocaleDateString() : '-'}</td>
                        <td className="px-5 py-3 sticky right-0 bg-white group-hover:bg-blue-50/30 transition-colors z-10">
                          <button onClick={() => handleOpenDetail(w.id)} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 opacity-0 group-hover:opacity-100 transition-opacity">
                            <MoreHorizontal size={16} />
                          </button>
                        </td>
                      </tr>
                    )
                  }

                  return meanings.map((m: any, mi: number) => {
                    // 收集该义项下所有助记维度（包括 rejected）
                    const mnemonicsMap = new Map<string, any>()
                    for (const mn of (m.mnemonics ?? [])) {
                      mnemonicsMap.set(mn.dimension, mn)
                    }
                    // 选择第一条有效助记显示在主行
                    const firstMn = ALL_MNEMONIC_DIMS.map(d => mnemonicsMap.get(d)).find(mn => mn?.content) ?? null
                    const mnData = firstMn ? parseMnemonic(firstMn.content) : null
                    const mnType = firstMn ? (MNEMONIC_TYPE_LABELS[firstMn.dimension] ?? firstMn.dimension) : ''
                    // 统计不适用数
                    const rejectedCount = ALL_MNEMONIC_DIMS.filter(d => {
                      const mn = mnemonicsMap.get(d)
                      return mn && mn.qc_status === 'rejected'
                    }).length
                    const validCount = ALL_MNEMONIC_DIMS.filter(d => {
                      const mn = mnemonicsMap.get(d)
                      return mn && mn.content
                    }).length

                    return (
                      <tr key={`${w.id}-${mi}`} className={`hover:bg-blue-50/30 transition-colors group ${mi > 0 ? 'border-t border-dashed border-slate-100' : ''}`}>
                        {mi === 0 && (
                          <>
                            <td rowSpan={rowCount} className="px-5 py-3 sticky left-0 bg-white group-hover:bg-blue-50/30 transition-colors z-10 align-top border-r border-slate-50">
                              <button onClick={() => handleOpenDetail(w.id)} className="font-bold text-slate-900 hover:text-blue-600 transition-colors cursor-pointer text-left">{w.word}</button>
                              {rowCount > 1 && <span className="block text-[9px] text-slate-400 mt-0.5">{rowCount} 个义项</span>}
                            </td>
                            <td rowSpan={rowCount} className="px-5 py-3 font-mono text-xs text-slate-400 align-top">{ipa}</td>
                            <td rowSpan={rowCount} className="px-5 py-3 text-xs text-slate-500 align-top">{syllables}</td>
                          </>
                        )}
                        {/* 义项行 */}
                        <td className="px-5 py-2">
                          <div className="flex flex-col gap-0.5 min-w-[100px]">
                            <span className="text-[10px] font-bold text-blue-600 uppercase">{m.pos}</span>
                            <span className="text-xs text-slate-700 line-clamp-1">{m.definition}</span>
                          </div>
                        </td>
                        <td className="px-5 py-2"><span className="text-xs text-slate-400 line-clamp-1 max-w-[130px]">{m.sources?.map((s: any) => s.source_name).join('; ') ?? ''}</span></td>
                        <td className="px-5 py-2"><span className="text-xs text-slate-500 italic line-clamp-1 max-w-[130px]">{m.chunk?.content ?? ''}</span></td>
                        <td className="px-5 py-2"><span className="text-xs text-slate-400 line-clamp-1 max-w-[130px]">{m.chunk?.content_cn ?? ''}</span></td>
                        <td className="px-5 py-2"><span className="text-xs text-slate-400 line-clamp-1 max-w-[180px]">{m.sentence?.content ?? ''}</span></td>
                        <td className="px-5 py-2"><span className="text-xs text-slate-400 line-clamp-1 max-w-[180px]">{m.sentence?.content_cn ?? ''}</span></td>
                        {/* 助记列 — 显示有效类型 + 不适用数 */}
                        <td className="px-5 py-2">
                          <div className="flex flex-col gap-1">
                            {mnType && <span className="px-2 py-0.5 bg-yellow-50 text-yellow-700 text-[10px] font-bold rounded border border-yellow-200 whitespace-nowrap w-fit">{mnType}</span>}
                            {rejectedCount > 0 && (
                              <span className="text-[9px] text-slate-400">{validCount} 适用 / {rejectedCount} 不适用</span>
                            )}
                          </div>
                        </td>
                        <td className="px-5 py-2"><span className="text-xs font-mono text-blue-600 line-clamp-2 max-w-[140px]">{mnData?.formula}</span></td>
                        <td className="px-5 py-2"><span className="text-xs text-slate-500 line-clamp-2 max-w-[140px]">{mnData?.chant}</span></td>
                        <td className="px-5 py-2"><span className="text-xs text-slate-400 line-clamp-2 max-w-[160px]">{mnData?.script}</span></td>
                        {mi === 0 && (
                          <>
                            <td rowSpan={rowCount} className="px-5 py-3 text-xs text-slate-400 whitespace-nowrap align-top">{w.created_at ? new Date(w.created_at).toLocaleDateString() : '-'}</td>
                            <td rowSpan={rowCount} className="px-5 py-3 sticky right-0 bg-white group-hover:bg-blue-50/30 transition-colors z-10 align-top">
                              <button onClick={() => handleOpenDetail(w.id)} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 opacity-0 group-hover:opacity-100 transition-opacity">
                                <MoreHorizontal size={16} />
                              </button>
                            </td>
                          </>
                        )}
                      </tr>
                    )
                  })
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* 分页 */}
        {!loading && totalPages > 1 && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-slate-100 bg-slate-50/50">
            <span className="text-xs text-slate-400">
              第 {(page - 1) * limit + 1}-{Math.min(page * limit, total)} 条，共 {total} 条
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="p-1.5 rounded-lg hover:bg-slate-100 disabled:opacity-30 transition-colors text-slate-500"
              >
                <ChevronLeft size={16} />
              </button>
              {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
                let p: number
                if (totalPages <= 7) { p = i + 1 }
                else if (page <= 4) { p = i + 1 }
                else if (page >= totalPages - 3) { p = totalPages - 6 + i }
                else { p = page - 3 + i }
                return (
                  <button
                    key={p}
                    onClick={() => setPage(p)}
                    className={`min-w-[32px] h-8 rounded-lg text-xs font-bold transition-colors ${
                      page === p ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-500 hover:bg-slate-100'
                    }`}
                  >
                    {p}
                  </button>
                )
              })}
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="p-1.5 rounded-lg hover:bg-slate-100 disabled:opacity-30 transition-colors text-slate-500"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* 详情弹窗 */}
      <AnimatePresence>
        {selectedWordId !== null && (
          <WordDetailModal word={detailWord} loading={detailLoading} onClose={handleCloseDetail} />
        )}
      </AnimatePresence>
    </div>
  )
}

/* ===== 详情弹窗 ===== */

/** 将质检问题按 content_item_id 归类到义项 */
function groupIssuesByMeaning(
  issues: WordDetail['issues'],
  meanings: WordDetail['meanings'],
  syllable?: ContentItem,
) {
  // 收集每个义项拥有的 content_item_id
  const meaningIssuesMap = new Map<number, typeof issues>() // meaningIdx → issues
  const wordLevelIssues: typeof issues = []
  const syllableId = syllable?.id

  // 建立 content_item_id → meaningIdx 的映射
  const itemToMeaning = new Map<number, number>()
  meanings.forEach((m, idx) => {
    if (m.chunk?.id) itemToMeaning.set(m.chunk.id, idx)
    if (m.sentence?.id) itemToMeaning.set(m.sentence.id, idx)
    for (const mn of (m.mnemonics ?? [])) {
      if (mn.id) itemToMeaning.set(mn.id, idx)
    }
  })

  for (const issue of issues) {
    const mIdx = itemToMeaning.get(issue.content_item_id)
    if (mIdx !== undefined) {
      const arr = meaningIssuesMap.get(mIdx) ?? []
      arr.push(issue)
      meaningIssuesMap.set(mIdx, arr)
    } else {
      wordLevelIssues.push(issue)
    }
  }
  return { meaningIssuesMap, wordLevelIssues }
}

function WordDetailModal({ word, loading, onClose }: { word: WordDetail | null; loading: boolean; onClose: () => void }) {
  const [meaningIdx, setMeaningIdx] = useState(0)
  const meanings = word?.meanings ?? []
  const currentMeaning = meanings[meaningIdx] ?? null

  // 质检问题按义项归类
  const { meaningIssuesMap, wordLevelIssues } = word
    ? groupIssuesByMeaning(word.issues ?? [], meanings, word.syllable)
    : { meaningIssuesMap: new Map(), wordLevelIssues: [] }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.95, y: 20 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.95, y: 20 }}
        className="bg-white w-full max-w-2xl max-h-[85vh] rounded-[28px] shadow-2xl overflow-hidden flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {loading ? (
          <div className="flex items-center justify-center py-24 gap-2 text-slate-400">
            <Loader2 className="animate-spin" size={24} />
            <span className="text-sm">加载中...</span>
          </div>
        ) : !word ? (
          <div className="text-center text-slate-400 py-10">加载失败</div>
        ) : (
          <>
            {/* 头部 */}
            <div className="p-6 pb-4 border-b border-slate-100 bg-gradient-to-r from-blue-50 to-white">
              <div className="flex items-start justify-between">
                <div>
                  <h2 className="text-3xl font-black text-slate-900 tracking-tight">{word.word}</h2>
                  <div className="flex items-center gap-3 mt-2">
                    {word.phonetics?.[0] && (
                      <>
                        <span className="font-mono text-sm text-blue-600">{word.phonetics[0].ipa}</span>
                        <span className="text-xs text-slate-400">·</span>
                        <span className="text-sm text-slate-500">
                          {word.syllable?.content ?? word.phonetics[0].syllables}
                        </span>
                      </>
                    )}
                  </div>
                </div>
                <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-xl transition-colors text-slate-400">
                  <X size={20} />
                </button>
              </div>
            </div>

            {/* 内容 */}
            <div className="flex-1 overflow-y-auto p-6 space-y-5">
              {/* 义项 Tab 切换 */}
              {meanings.length > 1 && (
                <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-2xl w-fit">
                  {meanings.map((m, idx) => (
                    <button
                      key={m.id || idx}
                      onClick={() => setMeaningIdx(idx)}
                      className={`px-4 py-1.5 rounded-xl text-xs font-bold transition-all ${
                        meaningIdx === idx
                          ? 'bg-white text-blue-600 shadow-sm'
                          : 'text-slate-400 hover:text-slate-600'
                      }`}
                    >
                      义项 {idx + 1}
                    </button>
                  ))}
                </div>
              )}

              {/* 当前义项内容 */}
              {currentMeaning && (() => {
                const m = currentMeaning
                return (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2">
                      <BookOpen size={15} className="text-blue-500" />
                      <span className="text-xs font-bold text-slate-400 uppercase">义项 {meaningIdx + 1}</span>
                    </div>
                    <div className="bg-slate-50 rounded-2xl p-4 space-y-3">
                      <div className="flex items-baseline gap-2">
                        <span className="text-xs font-bold text-blue-600 uppercase bg-blue-50 px-2 py-0.5 rounded">{m.pos}</span>
                        <span className="text-sm font-medium text-slate-900">{m.definition}</span>
                      </div>

                      {m.sources && m.sources.length > 0 && (
                        <div className="flex items-center gap-2 flex-wrap">
                          <GraduationCap size={13} className="text-slate-400 shrink-0" />
                          {m.sources.map((s: any, si: number) => (
                            <span key={si} className="text-[10px] px-2 py-0.5 bg-white border border-slate-200 rounded-md text-slate-500">{s.source_name}</span>
                          ))}
                        </div>
                      )}

                      {m.chunk && m.chunk.content && (
                        <ReadOnlyContentItem
                          item={m.chunk}
                          label="核心语块"
                          icon={<Layers size={13} className="text-violet-400 mt-0.5 shrink-0" />}
                          contentClass="text-sm text-violet-700 italic font-medium"
                          hasCn

                        />
                      )}

                      {m.sentence && m.sentence.content && (
                        <ReadOnlyContentItem
                          item={m.sentence}
                          label="例句"
                          icon={<Volume2 size={13} className="text-emerald-400 mt-0.5 shrink-0" />}
                          contentClass="text-sm text-slate-800"
                          hasCn

                        />
                      )}

                      {/* 该义项的助记 — 显示全部 4 种类型 */}
                      {m.mnemonics && m.mnemonics.length > 0 && (
                        <MnemonicSection mnemonics={m.mnemonics} />
                      )}

                      {/* 该义项的质检问题 — 可折叠 */}
                      {(meaningIssuesMap.get(meaningIdx) ?? []).length > 0 && (
                        <CollapsibleIssues issues={meaningIssuesMap.get(meaningIdx)!} label={`义项 ${meaningIdx + 1} 质检问题`} />
                      )}
                    </div>
                  </div>
                )
              })()}

              {/* 词级质检问题（音节等不属于具体义项的） */}
              {wordLevelIssues.length > 0 && (
                <CollapsibleIssues issues={wordLevelIssues} label="词级质检问题" />
              )}

              {/* 元信息 */}
              <div className="flex items-center gap-4 pt-2 text-[10px] text-slate-400 uppercase tracking-wider">
                <span>ID: {word.id}</span>
                <span>创建: {word.created_at ? new Date(word.created_at).toLocaleDateString() : '-'}</span>
              </div>
            </div>
          </>
        )}
      </motion.div>
    </motion.div>
  )
}

/* ===== 可编辑内容项（chunk / sentence） ===== */

function ReadOnlyContentItem({
  item, label, icon, contentClass, hasCn,
}: {
  item: ContentItem
  label: string
  icon: React.ReactNode
  contentClass: string
  hasCn?: boolean
}) {
  return (
    <div className="flex items-start gap-2">
      {icon}
      <div className="flex-1">
        <p className="text-[10px] font-bold text-slate-400 uppercase mb-0.5">{label}</p>
        <p className={contentClass}>{item.content}</p>
        {hasCn && item.content_cn && <p className="text-xs text-slate-500 mt-0.5">{item.content_cn}</p>}
      </div>
    </div>
  )
}

/* ===== 可折叠质检问题 ===== */

function CollapsibleIssues({ issues, label }: { issues: WordDetail['issues']; label: string }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="pt-2 border-t border-slate-200/60">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-2 w-full text-left group"
      >
        <AlertCircle size={13} className="text-red-400 shrink-0" />
        <span className="text-[10px] font-bold text-red-400 uppercase">{label} ({issues.length})</span>
        <ChevronDown size={13} className={`text-slate-400 ml-auto transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="space-y-1 mt-2">
              {issues.map((issue, i) => (
                <div key={i} className="text-sm bg-red-50 text-red-600 border border-red-100 px-3 py-2 rounded-xl">
                  <span className="font-mono text-xs text-red-500 mr-2">[{issue.rule_id}]</span>
                  {issue.message}
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

/* ===== 助记区块：显示全部 4 种类型 ===== */

function MnemonicSection({ mnemonics }: { mnemonics: any[] }) {
  const mnMap = new Map<string, any>()
  for (const mn of mnemonics) mnMap.set(mn.dimension, mn)

  return (
    <div className="space-y-2 pt-2 border-t border-slate-200/60">
      <div className="flex items-center gap-1.5">
        <Lightbulb size={13} className="text-yellow-500 shrink-0" />
        <span className="text-[10px] font-bold text-slate-400 uppercase">助记（4 种类型）</span>
      </div>
      {ALL_MNEMONIC_DIMS.map(dim => {
        const mn = mnMap.get(dim)
        const typeLabel = MNEMONIC_TYPE_LABELS[dim] ?? dim
        const isRejected = mn?.qc_status === 'rejected'
        const hasContent = mn?.content

        if (!mn) return null

        if (isRejected || !hasContent) {
          return (
            <div key={dim} className="bg-slate-50 rounded-xl p-3 border border-slate-100 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-[10px] px-2 py-0.5 bg-slate-200 text-slate-500 rounded-md font-bold">{typeLabel}</span>
                <span className="flex items-center gap-1 text-xs text-slate-400">
                  <Ban size={11} /> 不适用
                </span>
              </div>
            </div>
          )
        }

        // 有内容的助记
        const parsed = parseMnemonic(mn.content)
        return (
          <div
            key={dim}
            className="bg-yellow-50/60 rounded-xl p-3 space-y-2 border border-yellow-100"
          >
            <div className="flex items-center justify-between">
              <span className="text-[10px] px-2 py-0.5 bg-yellow-100 text-yellow-700 rounded-md font-bold">{typeLabel}</span>
              <span className="text-[9px] text-emerald-500 font-bold flex items-center gap-1">
                <CheckCircle2 size={10} /> 已通过
              </span>
            </div>
            {parsed.formula && (
              <div>
                <p className="text-[10px] font-bold text-yellow-600/60 uppercase mb-0.5">核心公式</p>
                <p className="text-sm font-mono font-bold text-yellow-800">{parsed.formula}</p>
              </div>
            )}
            {parsed.chant && (
              <div>
                <p className="text-[10px] font-bold text-yellow-600/60 uppercase mb-0.5">助记口诀</p>
                <p className="text-sm text-yellow-700">{parsed.chant}</p>
              </div>
            )}
            {parsed.script && (
              <div className="pt-2 border-t border-yellow-200/60">
                <p className="text-[10px] font-bold text-yellow-600/60 uppercase mb-0.5">老师话术</p>
                <p className="text-xs text-yellow-800/80 leading-relaxed">{parsed.script}</p>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
