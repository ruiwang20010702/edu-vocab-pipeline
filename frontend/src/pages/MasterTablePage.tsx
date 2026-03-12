import { useState, useEffect, useRef, useCallback } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import {
  Search, Download, ChevronLeft, ChevronRight, Loader2, MoreHorizontal,
} from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { useToast } from '../components/Toast'
import type { WordDetail, PaginatedResponse, StatusCounts } from '../types'
import WordDetailModal from './mastertable/WordDetailModal'
import { ALL_MNEMONIC_DIMS, MNEMONIC_TYPE_LABELS } from './review/constants'
import { parseMnemonic } from './review/utils'

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
  const [exportLoading, setExportLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState<'approved' | 'in_progress' | null>('approved')
  const [statusCounts, setStatusCounts] = useState<StatusCounts>({ approved: 0, in_progress: 0, total: 0 })
  const { showToast } = useToast()
  const limit = 50

  // F-M1: 翻页防抖，避免快速连点触发多次请求
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const debouncedLoadWords = useCallback((fn: () => void) => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(fn, 300)
  }, [])

  const loadWords = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ page: String(page), limit: String(limit) })
      if (search) params.set('q', search)
      if (statusFilter) params.set('status', statusFilter)
      const res = await api.get<PaginatedResponse<WordDetail>>(`/words?${params}`)
      setWords(res.items)
      setTotal(res.total)
      if (res.status_counts) setStatusCounts(res.status_counts)
    } catch (e) {
      showToast('error', e instanceof ApiError ? e.detail : '加载数据失败')
      setWords([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { debouncedLoadWords(loadWords) }, [page, statusFilter])

  const handleSearch = () => { setPage(1); loadWords() }

  const handleStatusChange = (s: 'approved' | 'in_progress' | null) => {
    setStatusFilter(s)
    setPage(1)
  }
  const totalPages = Math.max(1, Math.ceil(total / limit))

  const handleOpenDetail = async (wordId: number) => {
    setSelectedWordId(wordId)
    setDetailLoading(true)
    setDetailWord(null)
    try {
      const data = await api.get<WordDetail>(`/words/${wordId}`)
      setDetailWord(data)
    } catch (e) {
      showToast('error', e instanceof ApiError ? e.detail : '加载详情失败')
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
      const blob = await api.blob('/export/excel')
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `vocab_export_${new Date().toISOString().slice(0, 10)}.xlsx`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e: any) {
      console.error('导出失败', e)
      alert(e?.detail || e?.message || '导出失败，请重试')
    } finally {
      setExportLoading(false)
    }
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
            {exportLoading ? '导出中...' : '导出已通过'}
          </button>
        </div>
      </div>

      {/* 状态 Tab */}
      <div className="flex items-center gap-1 p-1 bg-white/80 backdrop-blur-sm rounded-2xl w-fit shadow-sm border border-white/80">
        {([
          { key: null, label: '全部', count: statusCounts.total },
          { key: 'approved' as const, label: '已通过', count: statusCounts.approved },
          { key: 'in_progress' as const, label: '进行中', count: statusCounts.in_progress },
        ] as const).map(tab => (
          <button
            key={tab.key ?? 'all'}
            onClick={() => handleStatusChange(tab.key)}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 ${
              statusFilter === tab.key
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50'
            }`}
          >
            {tab.key === 'approved' && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block" />}
            {tab.key === 'in_progress' && <span className="w-1.5 h-1.5 rounded-full bg-blue-400 inline-block" />}
            {tab.label}
            <span className={`text-[10px] ${statusFilter === tab.key ? 'text-white/70' : 'text-slate-400'}`}>
              {tab.count}
            </span>
          </button>
        ))}
      </div>

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
                          {statusFilter === null && (
                            <span className={`flex items-center gap-1 text-[9px] mt-0.5 ${w.completion_status === 'approved' ? 'text-emerald-500' : 'text-blue-500'}`}>
                              <span className={`w-1.5 h-1.5 rounded-full ${w.completion_status === 'approved' ? 'bg-emerald-400' : 'bg-blue-400'}`} />
                              {w.completion_status === 'approved' ? '已通过' : '进行中'}
                            </span>
                          )}
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
                    const mnemonicsMap = new Map<string, any>()
                    for (const mn of (m.mnemonics ?? [])) {
                      mnemonicsMap.set(mn.dimension, mn)
                    }
                    const firstMn = ALL_MNEMONIC_DIMS.map(d => mnemonicsMap.get(d)).find(mn => mn?.content) ?? null
                    const mnData = firstMn ? parseMnemonic(firstMn.content) : null
                    const mnType = firstMn ? (MNEMONIC_TYPE_LABELS[firstMn.dimension] ?? firstMn.dimension) : ''
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
                              {statusFilter === null && (
                                <span className={`flex items-center gap-1 text-[9px] mt-0.5 ${w.completion_status === 'approved' ? 'text-emerald-500' : 'text-blue-500'}`}>
                                  <span className={`w-1.5 h-1.5 rounded-full ${w.completion_status === 'approved' ? 'bg-emerald-400' : 'bg-blue-400'}`} />
                                  {w.completion_status === 'approved' ? '已通过' : '进行中'}
                                </span>
                              )}
                            </td>
                            <td rowSpan={rowCount} className="px-5 py-3 font-mono text-xs text-slate-400 align-top">{ipa}</td>
                            <td rowSpan={rowCount} className="px-5 py-3 text-xs text-slate-500 align-top">{syllables}</td>
                          </>
                        )}
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
          <WordDetailModal word={detailWord} loading={detailLoading} onClose={handleCloseDetail} onWordUpdate={setDetailWord} editable={detailWord?.completion_status === 'approved'} />
        )}
      </AnimatePresence>
    </div>
  )
}
