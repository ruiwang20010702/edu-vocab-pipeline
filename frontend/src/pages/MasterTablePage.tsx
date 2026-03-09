import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { Search, Download, ChevronLeft, ChevronRight, X, Loader2, CheckCircle2, AlertTriangle } from 'lucide-react'
import { api } from '../lib/api'
import type { WordDetail, PaginatedResponse } from '../types'

interface ExportReadiness {
  total_words: number
  approved_words: number
  ready: boolean
}

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
  const totalPages = Math.ceil(total / limit)

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

  return (
    <div className="space-y-4">
      {/* 搜索 + 导出 */}
      <div className="flex items-center gap-3">
        <div className="flex-1 relative">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-white/40" size={18} />
          <input
            type="text"
            placeholder="搜索单词..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
            className="w-full pl-11 pr-4 py-3 glass-module rounded-2xl text-white placeholder-white/40 focus:outline-none focus:border-white/50 transition-all"
          />
        </div>
        <button
          onClick={handleExport}
          disabled={exportLoading}
          className="flex items-center gap-2 px-5 py-3 glass-module rounded-2xl text-white/70 hover:text-white transition-colors disabled:opacity-50"
        >
          {exportLoading ? <Loader2 size={18} className="animate-spin" /> : <Download size={18} />}
          <span className="text-sm">导出检查</span>
        </button>
      </div>

      {/* 导出就绪状态 */}
      <AnimatePresence>
        {exportInfo && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="glass-card rounded-2xl p-4"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                {exportInfo.ready ? (
                  <CheckCircle2 size={20} className="text-green-300" />
                ) : (
                  <AlertTriangle size={20} className="text-yellow-300" />
                )}
                <div>
                  <p className="text-white text-sm font-medium">
                    {exportInfo.ready ? '数据就绪，可以导出' : '部分数据未审核通过'}
                  </p>
                  <p className="text-white/50 text-xs">
                    已审核 {exportInfo.approved_words}/{exportInfo.total_words} 词
                  </p>
                </div>
              </div>
              <button
                onClick={() => setExportInfo(null)}
                className="text-white/40 hover:text-white/70"
              >
                <X size={16} />
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* 表格 */}
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="glass-card rounded-3xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-40">
            <Loader2 size={24} className="animate-spin text-white/50" />
          </div>
        ) : words.length === 0 ? (
          <div className="text-center text-white/50 py-10">暂无数据</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="text-left text-sm font-medium text-white/60 px-6 py-4">单词</th>
                  <th className="text-left text-sm font-medium text-white/60 px-6 py-4">音标</th>
                  <th className="text-left text-sm font-medium text-white/60 px-6 py-4">义项数</th>
                  <th className="text-left text-sm font-medium text-white/60 px-6 py-4">状态</th>
                  <th className="text-left text-sm font-medium text-white/60 px-6 py-4">更新时间</th>
                </tr>
              </thead>
              <tbody>
                {words.map(w => (
                  <tr
                    key={w.id}
                    className="border-b border-white/5 hover:bg-white/5 cursor-pointer transition-colors"
                    onClick={() => handleOpenDetail(w.id)}
                  >
                    <td className="px-6 py-3 text-white font-medium">{w.word}</td>
                    <td className="px-6 py-3 text-white/60 font-mono text-sm">{w.phonetics[0]?.ipa ?? '-'}</td>
                    <td className="px-6 py-3 text-white/60">{w.meanings.length}</td>
                    <td className="px-6 py-3">
                      {w.issues.length > 0 ? (
                        <span className="px-2 py-1 rounded-lg text-xs bg-red-400/20 text-red-200">有问题</span>
                      ) : (
                        <span className="px-2 py-1 rounded-lg text-xs bg-green-400/20 text-green-200">正常</span>
                      )}
                    </td>
                    <td className="px-6 py-3 text-white/40 text-sm">{w.updated_at ? new Date(w.updated_at).toLocaleDateString() : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* 分页 */}
        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-3 p-4 border-t border-white/10">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              className="p-2 rounded-xl hover:bg-white/10 text-white/50 disabled:opacity-30 transition-colors"
            >
              <ChevronLeft size={18} />
            </button>
            <span className="text-sm text-white/60">{page} / {totalPages}</span>
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="p-2 rounded-xl hover:bg-white/10 text-white/50 disabled:opacity-30 transition-colors"
            >
              <ChevronRight size={18} />
            </button>
          </div>
        )}
      </motion.div>

      {/* 详情弹窗 */}
      <AnimatePresence>
        {selectedWordId !== null && (
          <WordDetailModal
            word={detailWord}
            loading={detailLoading}
            onClose={handleCloseDetail}
          />
        )}
      </AnimatePresence>
    </div>
  )
}

function WordDetailModal({ word, loading, onClose }: { word: WordDetail | null; loading: boolean; onClose: () => void }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.95 }}
        animate={{ scale: 1 }}
        exit={{ scale: 0.95 }}
        className="glass-card rounded-3xl p-6 w-full max-w-2xl max-h-[80vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        {loading ? (
          <div className="flex items-center justify-center h-40">
            <Loader2 size={24} className="animate-spin text-white/50" />
          </div>
        ) : !word ? (
          <div className="text-center text-white/50 py-10">加载失败</div>
        ) : (
          <>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-2xl font-bold text-white">{word.word}</h3>
                {word.phonetics[0] && (
                  <p className="text-white/50 font-mono">{word.phonetics[0].ipa} · {word.phonetics[0].syllables}</p>
                )}
              </div>
              <button onClick={onClose} className="text-white/40 hover:text-white/80">
                <X size={20} />
              </button>
            </div>

            {/* 义项 */}
            <div className="space-y-4">
              {word.meanings.map((m) => (
                <div key={m.id} className="bg-white/5 rounded-2xl p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="px-2 py-0.5 bg-blue-400/20 text-blue-200 rounded-lg text-xs">{m.pos}</span>
                    <span className="text-white">{m.definition}</span>
                  </div>
                  {m.sources && m.sources.length > 0 && (
                    <p className="text-xs text-white/40">来源: {m.sources.map(s => s.source_name).join(', ')}</p>
                  )}
                  {m.chunk && m.chunk.content && (
                    <div className="mt-2 pl-3 border-l-2 border-blue-400/30">
                      <p className="text-sm text-white/70">语块: {m.chunk.content}</p>
                    </div>
                  )}
                  {m.sentence && m.sentence.content && (
                    <div className="mt-1 pl-3 border-l-2 border-green-400/30">
                      <p className="text-sm text-white/70">例句: {m.sentence.content}</p>
                      {m.sentence.content_cn && <p className="text-sm text-white/50">{m.sentence.content_cn}</p>}
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* 助记 */}
            {word.mnemonic && word.mnemonic.content && (
              <div className="mt-4 bg-yellow-400/10 rounded-2xl p-4">
                <p className="text-sm text-yellow-200/80 font-medium mb-1">助记</p>
                <p className="text-white/80">{word.mnemonic.content}</p>
              </div>
            )}

            {/* 质检问题 */}
            {word.issues.length > 0 && (
              <div className="mt-4">
                <p className="text-sm text-white/60 mb-2">质检问题 ({word.issues.length})</p>
                <div className="space-y-1">
                  {word.issues.map((issue, i) => (
                    <div key={i} className="text-sm bg-red-400/10 text-red-200 px-3 py-2 rounded-xl">
                      <span className="font-mono text-xs text-red-300 mr-2">[{issue.rule_id}]</span>
                      {issue.message}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </motion.div>
    </motion.div>
  )
}
