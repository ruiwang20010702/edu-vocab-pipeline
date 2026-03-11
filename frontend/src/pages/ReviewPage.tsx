import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import {
  Search, RefreshCw, CheckCircle2, Loader2, X, PackagePlus,
  ArrowLeft, AlertCircle, Filter, ChevronDown, UserCog, Save,
  BookOpen, Layers, Volume2, Lightbulb, Ban,
} from 'lucide-react'
import { api, ApiError } from '../lib/api'
import type { ReviewItem, ReviewBatch, BatchDetail, WordDetail } from '../types'

interface Props {
  onBack: () => void
}

type Tab = 'all' | 'can_retry' | 'must_manual'

const DIMENSION_LABELS: Record<string, string> = {
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

const FILTER_GROUPS = [
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

/* ===== 按单词分组 ===== */

interface WordGroup {
  word_id: number
  word_name: string
  items: ReviewItem[]
}

function groupByWord(items: ReviewItem[]): WordGroup[] {
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

/* ===== 主组件 ===== */

export default function ReviewPage({ onBack }: Props) {
  const [items, setItems] = useState<ReviewItem[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [tab, setTab] = useState<Tab>('all')
  const [selectedWordId, setSelectedWordId] = useState<number | null>(null)
  const [actionLoading, setActionLoading] = useState<number | null>(null)
  const [filterDim, setFilterDim] = useState('')
  const [isFilterOpen, setIsFilterOpen] = useState(false)

  // 批次状态
  const [batch, setBatch] = useState<ReviewBatch | null>(null)
  const [batchLoading, setBatchLoading] = useState(true)
  const [assignLoading, setAssignLoading] = useState(false)

  // 重新生成结果
  const [regenResult, setRegenResult] = useState<{ id: number; passed: boolean; message: string } | null>(null)

  const loadBatch = useCallback(async () => {
    setBatchLoading(true)
    try {
      const data = await api.get<ReviewBatch | null>('/batches/current')
      setBatch(data)
    } catch (e) {
      console.error('加载批次信息失败', e)
      setBatch(null)
    } finally {
      setBatchLoading(false)
    }
  }, [])

  const loadItems = useCallback(async () => {
    setLoading(true)
    try {
      if (batch) {
        const detail = await api.get<BatchDetail>(`/batches/${batch.id}/words`)
        const res = await api.get<{ items: ReviewItem[]; total: number }>('/reviews?limit=200')
        const allReviews = res.items ?? []
        const batchReviewIds = new Set(
          detail.words.flatMap(w => w.items.map(i => i.review_id))
        )
        setItems(allReviews.filter(r => batchReviewIds.has(r.id)))
      } else {
        const res = await api.get<{ items: ReviewItem[]; total: number }>('/reviews?limit=200')
        setItems(res.items ?? [])
      }
    } catch (e) {
      console.error('加载审核列表失败', e)
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [batch])

  useEffect(() => { loadBatch() }, [loadBatch])
  useEffect(() => { if (!batchLoading) loadItems() }, [batchLoading, loadItems])

  const handleAssign = async () => {
    setAssignLoading(true)
    try {
      const data = await api.post<ReviewBatch | null>('/batches/assign')
      setBatch(data)
    } catch (e) {
      console.error('领取批次失败', e)
    } finally {
      setAssignLoading(false)
    }
  }

  const handleApprove = async (id: number) => {
    setActionLoading(id)
    try {
      await api.post(`/reviews/${id}/approve`)
      setItems(prev => prev.filter(i => i.id !== id))
    } catch (e) { console.error('审核通过失败', e) }
    finally { setActionLoading(null) }
  }

  const handleRegenerate = async (id: number) => {
    setActionLoading(id)
    setRegenResult(null)
    try {
      const res = await api.post<{
        success: boolean; qc_passed: boolean; retry_count: number; message: string
        new_content: string | null; new_content_cn: string | null
        new_issues: Array<{ rule_id: string; field: string; message: string }>
      }>(`/reviews/${id}/regenerate`)
      if (res.qc_passed) {
        setRegenResult({ id, passed: true, message: res.message })
        setTimeout(() => {
          setItems(prev => prev.filter(i => i.id !== id))
          setRegenResult(null)
        }, 1500)
      } else {
        setRegenResult({ id, passed: false, message: res.message })
        await loadItems()
        setTimeout(() => setRegenResult(null), 3000)
      }
    } catch (e) { console.error('重新生成失败', e) }
    finally { setActionLoading(null) }
  }

  // 过滤
  const filtered = items.filter(item => {
    if (search && !item.word?.word.toLowerCase().includes(search.toLowerCase())) return false
    if (tab === 'can_retry' && (item.content_item?.retry_count ?? 0) >= 3) return false
    if (tab === 'must_manual' && (item.content_item?.retry_count ?? 0) < 3) return false
    if (filterDim) {
      const dim = item.content_item?.dimension ?? ''
      if (filterDim === 'mnemonic') {
        if (!dim.startsWith('mnemonic')) return false
      } else if (dim !== filterDim) {
        return false
      }
    }
    return true
  })

  const wordGroups = groupByWord(filtered)

  // 从实时数据派生当前选中的 group（而非快照）
  const selectedWordGroup = selectedWordId !== null
    ? groupByWord(items).find(g => g.word_id === selectedWordId) ?? null
    : null

  const counts = {
    total: items.length,
    can_retry: items.filter(i => (i.content_item?.retry_count ?? 0) < 3).length,
    must_manual: items.filter(i => (i.content_item?.retry_count ?? 0) >= 3).length,
  }

  return (
    <div className="space-y-6 pb-20">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button onClick={onBack} className="p-2 hover:bg-white/30 rounded-xl transition-colors text-white/60 shrink-0">
            <ArrowLeft size={20} />
          </button>
          <div>
            <h2 className="text-2xl font-bold tracking-tight text-white drop-shadow-sm">质检修复</h2>
            <p className="text-sm text-white/70">{wordGroups.length} 个单词 · {counts.total} 个异常项</p>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          {/* 搜索框 */}
          <div className="relative">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="搜索单词..."
              className="w-48 pl-9 pr-3 py-2 bg-white/95 backdrop-blur-sm rounded-xl text-sm border border-white/80 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-200/50 placeholder:text-slate-400"
            />
          </div>

          {/* 错误类型筛选 */}
          <div className="relative">
            <button
              onClick={() => setIsFilterOpen(!isFilterOpen)}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm transition-all border shadow-sm ${
                filterDim
                  ? 'bg-blue-50 border-blue-200 text-blue-700 font-medium'
                  : 'bg-white/95 backdrop-blur-sm border-white/80 text-slate-500 hover:text-slate-700'
              }`}
            >
              <Filter size={13} />
              <span className="max-w-[100px] truncate">
                {filterDim
                  ? FILTER_GROUPS.flatMap(g => g.items).find(i => i.value === filterDim)?.label ?? '错误类型'
                  : '错误类型'
                }
              </span>
              {filterDim ? (
                <span
                  onClick={e => { e.stopPropagation(); setFilterDim(''); setIsFilterOpen(false) }}
                  className="p-0.5 rounded hover:bg-blue-200/50 transition-colors"
                >
                  <X size={11} />
                </span>
              ) : (
                <ChevronDown size={12} className={`transition-transform ${isFilterOpen ? 'rotate-180' : ''}`} />
              )}
            </button>

            {isFilterOpen && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setIsFilterOpen(false)} />
                <div className="absolute top-full right-0 mt-2 w-64 bg-white rounded-2xl shadow-2xl border border-slate-100 z-50 overflow-hidden">
                  <div className="max-h-80 overflow-y-auto py-2">
                    <button
                      onClick={() => { setFilterDim(''); setIsFilterOpen(false) }}
                      className={`w-full text-left px-4 py-2.5 text-sm transition-colors ${
                        !filterDim ? 'bg-blue-50 text-blue-700 font-medium' : 'text-slate-600 hover:bg-slate-50'
                      }`}
                    >
                      全部错误类型
                    </button>
                    {FILTER_GROUPS.map(group => (
                      <div key={group.group}>
                        <div className="px-4 pt-3 pb-1 text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                          {group.group}
                        </div>
                        {group.items.map(item => (
                          <button
                            key={item.value}
                            onClick={() => { setFilterDim(item.value); setIsFilterOpen(false) }}
                            className={`w-full text-left px-4 py-2.5 text-sm transition-colors ${
                              filterDim === item.value
                                ? 'bg-blue-50 text-blue-700 font-medium'
                                : 'text-slate-600 hover:bg-slate-50'
                            }`}
                          >
                            {item.label}
                          </button>
                        ))}
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>

          {/* 批次按钮 */}
          {batchLoading ? (
            <Loader2 size={16} className="animate-spin text-white/60" />
          ) : batch ? (
            <div className="flex items-center gap-2 px-3 py-2 bg-white/95 backdrop-blur-sm rounded-xl text-sm border border-white/80 shadow-sm">
              <PackagePlus size={14} className="text-blue-600" />
              <span className="text-slate-600">批次 #{batch.id}</span>
              <span className="text-slate-400">{batch.reviewed_count}/{batch.word_count}</span>
              <button onClick={() => { setBatch(null) }} className="text-slate-300 hover:text-slate-500 ml-1">
                <X size={12} />
              </button>
            </div>
          ) : (
            <button
              onClick={handleAssign}
              disabled={assignLoading}
              className="flex items-center gap-1.5 px-3 py-2 bg-white/95 backdrop-blur-sm rounded-xl text-sm border border-white/80 shadow-sm text-slate-500 hover:text-blue-600 transition-colors disabled:opacity-50"
            >
              {assignLoading ? <Loader2 size={14} className="animate-spin" /> : <PackagePlus size={14} />}
              领取批次
            </button>
          )}

          {/* AI 修复按钮 */}
          <button
            onClick={() => {
              const canRetryItems = filtered.filter(i => (i.content_item?.retry_count ?? 0) < 3)
              canRetryItems.forEach(item => handleRegenerate(item.id))
            }}
            disabled={counts.can_retry === 0 || actionLoading !== null}
            className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 text-white rounded-xl text-sm font-bold hover:bg-blue-700 transition-all disabled:opacity-40 shadow-lg shadow-blue-600/20 hover:-translate-y-0.5 active:scale-95"
          >
            <RefreshCw size={14} />
            AI 修复 ({counts.can_retry})
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 p-1 bg-white rounded-[32px] w-fit shadow-sm border border-white">
        {([
          { id: 'all' as Tab, label: '全部', count: counts.total },
          { id: 'can_retry' as Tab, label: '可 AI 修复', count: counts.can_retry },
          { id: 'must_manual' as Tab, label: '已达上限', count: counts.must_manual },
        ]).map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-6 py-2 rounded-2xl text-sm font-bold transition-all ${
              tab === t.id
                ? 'bg-blue-600 text-white shadow-lg shadow-blue-200'
                : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50'
            }`}
          >
            {t.label} {t.count}
          </button>
        ))}
      </div>

      {/* Loading / Empty / Content */}
      {loading ? (
        <div className="flex items-center justify-center h-40">
          <Loader2 size={32} className="animate-spin text-blue-600" />
        </div>
      ) : wordGroups.length === 0 ? (
        <div className="text-center py-20 space-y-4">
          <div className="w-20 h-20 bg-emerald-50 text-emerald-600 rounded-full flex items-center justify-center mx-auto">
            <CheckCircle2 size={40} />
          </div>
          <h3 className="text-2xl font-bold text-white">
            {filterDim ? '该类型下暂无待修复项' : '暂无待修复项'}
          </h3>
          <p className="text-white/60">
            {filterDim ? '尝试切换其他错误类型查看' : '所有内容已通过质检。'}
          </p>
          {filterDim && (
            <button onClick={() => setFilterDim('')} className="px-4 py-2 bg-white/20 text-white rounded-xl text-sm font-medium hover:bg-white/30 transition-all">
              清除筛选
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {wordGroups.map(group => (
            <WordGroupCard
              key={group.word_id}
              group={group}
              onOpen={() => setSelectedWordId(group.word_id)}
            />
          ))}
        </div>
      )}

      {/* 单词审核弹窗 */}
      <AnimatePresence>
        {selectedWordGroup && (
          <WordReviewModal
            group={selectedWordGroup}
            onClose={() => setSelectedWordId(null)}
            onApprove={handleApprove}
            onRegenerate={handleRegenerate}
            onSaved={() => { loadItems(); }}
            actionLoading={actionLoading}
            regenResult={regenResult}
          />
        )}
      </AnimatePresence>
    </div>
  )
}

/* ===== 单词卡片（按词分组） ===== */

function WordGroupCard({ group, onOpen }: { group: WordGroup; onOpen: () => void }) {
  const canRetry = group.items.filter(i => (i.content_item?.retry_count ?? 0) < 3).length
  const mustManual = group.items.filter(i => (i.content_item?.retry_count ?? 0) >= 3).length
  const dims = [...new Set(group.items.map(i => DIMENSION_LABELS[i.content_item?.dimension ?? ''] ?? i.content_item?.dimension))]

  return (
    <motion.div
      layout
      className="bg-white rounded-[24px] border border-white shadow-sm hover:border-blue-200 hover:shadow-md p-5 space-y-3 cursor-pointer transition-all"
      onClick={onOpen}
    >
      <div className="flex items-start justify-between">
        <h3 className="text-lg font-bold text-slate-900">{group.word_name}</h3>
        <span className="text-[10px] font-bold text-slate-400">{group.items.length} 项</span>
      </div>

      {/* 维度标签 */}
      <div className="flex flex-wrap gap-1.5">
        {dims.map(d => (
          <span key={d} className="px-2 py-0.5 bg-rose-50 text-rose-600 text-[10px] font-bold rounded-lg border border-rose-100">
            {d}
          </span>
        ))}
      </div>

      {/* 状态 */}
      <div className="flex items-center gap-3 text-[10px] font-bold uppercase tracking-tight">
        {canRetry > 0 && <span className="text-blue-500">可修复 {canRetry}</span>}
        {mustManual > 0 && <span className="text-rose-500">需人工 {mustManual}</span>}
      </div>
    </motion.div>
  )
}

/* ===== 单词审核弹窗 ===== */

function WordReviewModal({
  group, onClose, onApprove, onRegenerate, onSaved, actionLoading, regenResult,
}: {
  group: WordGroup
  onClose: () => void
  onApprove: (id: number) => void
  onRegenerate: (id: number) => void
  onSaved: () => void
  actionLoading: number | null
  regenResult: { id: number; passed: boolean; message: string } | null
}) {
  const [wordDetail, setWordDetail] = useState<WordDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(true)
  const [meaningIdx, setMeaningIdx] = useState(0)

  // 编辑状态 — 按 review_id 跟踪
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editContent, setEditContent] = useState('')
  const [editContentCn, setEditContentCn] = useState('')
  const [saving, setSaving] = useState(false)
  const [editError, setEditError] = useState('')
  const [editResult, setEditResult] = useState<{ passed: boolean; message: string } | null>(null)

  useEffect(() => {
    setDetailLoading(true)
    api.get<WordDetail>(`/words/${group.word_id}`)
      .then(data => setWordDetail(data))
      .catch(() => setWordDetail(null))
      .finally(() => setDetailLoading(false))
  }, [group.word_id])

  const meanings = wordDetail?.meanings ?? []
  const currentMeaning = meanings[meaningIdx] ?? null

  // 当前义项下的审核项
  const currentItems = currentMeaning
    ? group.items.filter(i => i.meaning_id === currentMeaning.id)
    : group.items.filter(i => i.meaning_id === null)

  // 无义项关联的审核项（音标等词级维度）
  const wordLevelItems = group.items.filter(i => !i.meaning_id)

  const startEdit = (item: ReviewItem) => {
    setEditingId(item.id)
    setEditContent(item.content_item?.content ?? '')
    setEditContentCn(item.content_item?.content_cn ?? '')
    setEditError('')
    setEditResult(null)
  }

  const cancelEdit = () => {
    setEditingId(null)
    setEditError('')
    setEditResult(null)
  }

  const handleSaveEdit = async (reviewId: number) => {
    setSaving(true)
    setEditError('')
    setEditResult(null)
    try {
      const res = await api.post<{
        success: boolean; qc_passed: boolean; message: string
        new_content: string | null; new_content_cn: string | null
        new_issues: Array<{ rule_id: string; field: string; message: string }>
      }>(`/reviews/${reviewId}/edit`, {
        content: editContent,
        content_cn: editContentCn || null,
      })
      if (res.qc_passed) {
        setEditResult({ passed: true, message: res.message })
        setTimeout(() => { onSaved(); cancelEdit() }, 1500)
      } else {
        setEditResult({ passed: false, message: res.message })
        if (res.new_content !== null) setEditContent(res.new_content)
        if (res.new_content_cn !== null) setEditContentCn(res.new_content_cn)
        onSaved()
      }
    } catch (e) {
      setEditError(e instanceof ApiError ? e.detail : '保存失败')
    } finally {
      setSaving(false)
    }
  }

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
        className="bg-white rounded-[32px] shadow-2xl border border-slate-100 w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {detailLoading ? (
          <div className="flex items-center justify-center py-24 gap-2 text-slate-400">
            <Loader2 className="animate-spin" size={24} />
            <span className="text-sm">加载中...</span>
          </div>
        ) : (
          <>
            {/* Header: 单词 + 音标 */}
            <div className="p-6 pb-4 border-b border-slate-100 bg-gradient-to-r from-blue-50 to-white">
              <div className="flex items-start justify-between">
                <div>
                  <h2 className="text-3xl font-black text-slate-900 tracking-tight">{group.word_name}</h2>
                  {wordDetail?.phonetics?.[0] && (
                    <div className="flex items-center gap-3 mt-2">
                      <span className="font-mono text-sm text-blue-600">{wordDetail.phonetics[0].ipa}</span>
                      {wordDetail.phonetics[0].syllables && (
                        <>
                          <span className="text-xs text-slate-400">·</span>
                          <span className="text-sm text-slate-500">{wordDetail.phonetics[0].syllables}</span>
                        </>
                      )}
                    </div>
                  )}
                  <p className="text-xs text-slate-400 mt-1">{group.items.length} 个异常项待处理</p>
                </div>
                <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-xl transition-colors text-slate-400">
                  <X size={20} />
                </button>
              </div>
            </div>

            {/* 义项 Tab */}
            {meanings.length > 1 && (
              <div className="px-6 pt-4 flex items-center gap-1 bg-white">
                <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-2xl">
                  {meanings.map((m, idx) => {
                    const itemsForMeaning = group.items.filter(i => i.meaning_id === m.id)
                    return (
                      <button
                        key={m.id || idx}
                        onClick={() => setMeaningIdx(idx)}
                        className={`px-4 py-1.5 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 ${
                          meaningIdx === idx
                            ? 'bg-white text-blue-600 shadow-sm'
                            : 'text-slate-400 hover:text-slate-600'
                        }`}
                      >
                        义项 {idx + 1}
                        {itemsForMeaning.length > 0 && (
                          <span className="w-4 h-4 bg-rose-500 text-white text-[9px] rounded-full flex items-center justify-center">
                            {itemsForMeaning.length}
                          </span>
                        )}
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            {/* 内容区 */}
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {/* 当前义项信息 */}
              {currentMeaning && (
                <div className="bg-slate-50 rounded-2xl p-4 space-y-2">
                  <div className="flex items-center gap-2">
                    <BookOpen size={14} className="text-blue-500" />
                    <span className="text-xs font-bold text-blue-600 uppercase bg-blue-50 px-2 py-0.5 rounded">{currentMeaning.pos}</span>
                    <span className="text-sm font-medium text-slate-900">{currentMeaning.definition}</span>
                  </div>

                  {/* 语块/例句预览 */}
                  {currentMeaning.chunk?.content && (
                    <div className="flex items-start gap-2 pt-1">
                      <Layers size={12} className="text-violet-400 mt-0.5 shrink-0" />
                      <p className="text-xs text-violet-700 italic">{currentMeaning.chunk.content}</p>
                    </div>
                  )}
                  {currentMeaning.sentence?.content && (
                    <div className="flex items-start gap-2">
                      <Volume2 size={12} className="text-emerald-400 mt-0.5 shrink-0" />
                      <p className="text-xs text-slate-600">{currentMeaning.sentence.content}</p>
                    </div>
                  )}
                </div>
              )}

              {/* 该义项下的异常维度列表 */}
              {currentItems.length > 0 ? (
                <div className="space-y-3">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">待修复维度</p>
                  {currentItems.map(item => (
                    <ReviewDimensionCard
                      key={item.id}
                      item={item}
                      isLoading={actionLoading === item.id}
                      regenResult={regenResult?.id === item.id ? regenResult : null}
                      isEditing={editingId === item.id}
                      editContent={editContent}
                      editContentCn={editContentCn}
                      editResult={editResult}
                      editError={editError}
                      saving={saving}
                      onEditContentChange={setEditContent}
                      onEditContentCnChange={setEditContentCn}
                      onApprove={() => onApprove(item.id)}
                      onRegenerate={() => onRegenerate(item.id)}
                      onStartEdit={() => startEdit(item)}
                      onCancelEdit={cancelEdit}
                      onSaveEdit={() => handleSaveEdit(item.id)}
                    />
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-slate-400 text-sm">
                  该义项下暂无异常
                </div>
              )}

              {/* 不适用的助记维度（rejected） */}
              {currentMeaning && (() => {
                const rejectedMnemonics = (currentMeaning.mnemonics ?? []).filter(
                  (mn: any) => mn.qc_status === 'rejected' || (!mn.content && mn.dimension?.startsWith('mnemonic_'))
                )
                if (rejectedMnemonics.length === 0) return null
                return (
                  <RejectedMnemonicsSection
                    mnemonics={rejectedMnemonics}
                    onRegenerated={() => {
                      // 刷新 wordDetail
                      api.get<WordDetail>(`/words/${group.word_id}`)
                        .then(data => setWordDetail(data))
                        .catch(() => {})
                    }}
                  />
                )
              })()}

              {/* 词级维度（音标等） */}
              {wordLevelItems.length > 0 && meaningIdx === 0 && (
                <div className="space-y-3 pt-2 border-t border-slate-100">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">词级维度</p>
                  {wordLevelItems.map(item => (
                    <ReviewDimensionCard
                      key={item.id}
                      item={item}
                      isLoading={actionLoading === item.id}
                      regenResult={regenResult?.id === item.id ? regenResult : null}
                      isEditing={editingId === item.id}
                      editContent={editContent}
                      editContentCn={editContentCn}
                      editResult={editResult}
                      editError={editError}
                      saving={saving}
                      onEditContentChange={setEditContent}
                      onEditContentCnChange={setEditContentCn}
                      onApprove={() => onApprove(item.id)}
                      onRegenerate={() => onRegenerate(item.id)}
                      onStartEdit={() => startEdit(item)}
                      onCancelEdit={cancelEdit}
                      onSaveEdit={() => handleSaveEdit(item.id)}
                    />
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </motion.div>
    </motion.div>
  )
}

/* ===== 维度审核卡片 ===== */

/* ===== 助记 JSON 解析 ===== */

interface MnemonicData { formula: string; chant: string; script: string }

function parseMnemonicJson(content: string): MnemonicData | null {
  if (!content) return null
  try {
    const data = JSON.parse(content)
    if (data && typeof data === 'object' && 'formula' in data) return data as MnemonicData
  } catch { /* not JSON */ }
  return null
}

function isMnemonicDim(dim: string): boolean {
  return dim.startsWith('mnemonic_')
}

function buildMnemonicJson(formula: string, chant: string, script: string): string {
  return JSON.stringify({ formula, chant, script })
}

function ReviewDimensionCard({
  item, isLoading, regenResult, isEditing,
  editContent, editContentCn, editResult, editError, saving,
  onEditContentChange, onEditContentCnChange,
  onApprove, onRegenerate, onStartEdit, onCancelEdit, onSaveEdit,
}: {
  item: ReviewItem
  isLoading: boolean
  regenResult: { passed: boolean; message: string } | null
  isEditing: boolean
  editContent: string
  editContentCn: string
  editResult: { passed: boolean; message: string } | null
  editError: string
  saving: boolean
  onEditContentChange: (v: string) => void
  onEditContentCnChange: (v: string) => void
  onApprove: () => void
  onRegenerate: () => void
  onStartEdit: () => void
  onCancelEdit: () => void
  onSaveEdit: () => void
}) {
  const dim = item.content_item?.dimension ?? ''
  const dimLabel = DIMENSION_LABELS[dim] ?? dim
  const retryCount = item.content_item?.retry_count ?? 0
  const atLimit = retryCount >= 3
  const content = item.content_item?.content ?? ''
  const issueMsg = item.issues?.[0]?.message ?? ''
  const isMnemonic = isMnemonicDim(dim)
  const mnemonicData = isMnemonic ? parseMnemonicJson(content) : null

  // 助记编辑：拆分三个字段
  const [editFormula, setEditFormula] = useState('')
  const [editChant, setEditChant] = useState('')
  const [editScript, setEditScript] = useState('')

  const handleStartMnemonicEdit = () => {
    if (mnemonicData) {
      setEditFormula(mnemonicData.formula)
      setEditChant(mnemonicData.chant)
      setEditScript(mnemonicData.script)
    } else {
      setEditFormula('')
      setEditChant('')
      setEditScript('')
    }
    onStartEdit()
  }

  const handleMnemonicSave = () => {
    onEditContentChange(buildMnemonicJson(editFormula, editChant, editScript))
    // 延迟一帧让 state 更新后再保存
    setTimeout(() => onSaveEdit(), 0)
  }

  return (
    <div className={`bg-white rounded-2xl border p-4 space-y-3 transition-all ${
      isLoading ? 'border-blue-400 ring-1 ring-blue-200' : 'border-slate-200'
    }`}>
      {/* 维度标题 + retry */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="px-2 py-0.5 bg-rose-50 text-rose-600 text-[10px] font-bold rounded-lg border border-rose-100">
            {dimLabel}
          </span>
          <span className={`text-[10px] font-bold ${atLimit ? 'text-rose-500' : 'text-slate-400'}`}>
            {retryCount}/3
          </span>
        </div>
        {issueMsg && (
          <span className="flex items-center gap-1 text-[10px] text-rose-500">
            <AlertCircle size={10} />
            异常
          </span>
        )}
      </div>

      {/* 问题描述 */}
      {issueMsg && (
        <p className="text-xs text-rose-600/80 bg-rose-50/50 px-3 py-2 rounded-xl border border-rose-100/50 leading-relaxed">
          {issueMsg}
        </p>
      )}

      {/* 内容预览 / 编辑 */}
      {isEditing ? (
        isMnemonic ? (
          /* 助记编辑: 三个独立 textarea */
          <div className="space-y-2">
            <div>
              <label className="text-[10px] font-bold text-slate-400 uppercase">核心公式</label>
              <textarea value={editFormula} onChange={e => setEditFormula(e.target.value)} rows={2}
                className="w-full mt-1 px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm text-slate-900 focus:outline-none focus:border-blue-300 resize-none" />
            </div>
            <div>
              <label className="text-[10px] font-bold text-slate-400 uppercase">助记口诀</label>
              <textarea value={editChant} onChange={e => setEditChant(e.target.value)} rows={2}
                className="w-full mt-1 px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm text-slate-900 focus:outline-none focus:border-blue-300 resize-none" />
            </div>
            <div>
              <label className="text-[10px] font-bold text-slate-400 uppercase">老师话术</label>
              <textarea value={editScript} onChange={e => setEditScript(e.target.value)} rows={4}
                className="w-full mt-1 px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm text-slate-900 focus:outline-none focus:border-blue-300 resize-none" />
            </div>
            {editResult && (
              <div className={`text-xs px-3 py-2 rounded-xl text-center font-medium ${
                editResult.passed ? 'bg-green-50 text-green-600 border border-green-200' : 'bg-orange-50 text-orange-600 border border-orange-200'
              }`}>
                {editResult.message}
              </div>
            )}
            {editError && <p className="text-xs text-red-600 text-center">{editError}</p>}
            <div className="flex items-center gap-2">
              <button onClick={handleMnemonicSave} disabled={saving} className="flex-1 py-1.5 bg-yellow-50 hover:bg-yellow-100 text-yellow-700 border border-yellow-200 rounded-xl text-xs font-bold flex items-center justify-center gap-1 disabled:opacity-50">
                {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                保存
              </button>
              <button onClick={onCancelEdit} className="px-3 py-1.5 text-slate-400 hover:text-slate-600 text-xs font-bold">
                取消
              </button>
            </div>
          </div>
        ) : (
          /* 非助记编辑: 原有双 textarea */
          <div className="space-y-2">
            <textarea
              value={editContent}
              onChange={e => onEditContentChange(e.target.value)}
              rows={3}
              className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm text-slate-900 focus:outline-none focus:border-blue-300 resize-none"
            />
            <textarea
              value={editContentCn}
              onChange={e => onEditContentCnChange(e.target.value)}
              rows={2}
              placeholder="中文翻译（可选）"
              className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-700 focus:outline-none focus:border-blue-300 resize-none placeholder:text-slate-400"
            />
            {editResult && (
              <div className={`text-xs px-3 py-2 rounded-xl text-center font-medium ${
                editResult.passed ? 'bg-green-50 text-green-600 border border-green-200' : 'bg-orange-50 text-orange-600 border border-orange-200'
              }`}>
                {editResult.message}
              </div>
            )}
            {editError && <p className="text-xs text-red-600 text-center">{editError}</p>}
            <div className="flex items-center gap-2">
              <button onClick={onSaveEdit} disabled={saving} className="flex-1 py-1.5 bg-yellow-50 hover:bg-yellow-100 text-yellow-700 border border-yellow-200 rounded-xl text-xs font-bold flex items-center justify-center gap-1 disabled:opacity-50">
                {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                保存
              </button>
              <button onClick={onCancelEdit} className="px-3 py-1.5 text-slate-400 hover:text-slate-600 text-xs font-bold">
                取消
              </button>
            </div>
          </div>
        )
      ) : isMnemonic && mnemonicData ? (
        /* 助记预览: 结构化三段 */
        <div className="space-y-2 text-xs">
          <div className="flex items-start gap-2">
            <span className="shrink-0 px-1.5 py-0.5 bg-violet-50 text-violet-600 rounded font-bold text-[10px]">公式</span>
            <span className="text-slate-700">{mnemonicData.formula}</span>
          </div>
          <div className="flex items-start gap-2">
            <span className="shrink-0 px-1.5 py-0.5 bg-amber-50 text-amber-600 rounded font-bold text-[10px]">口诀</span>
            <span className="text-slate-700">{mnemonicData.chant}</span>
          </div>
          <div className="flex items-start gap-2">
            <span className="shrink-0 px-1.5 py-0.5 bg-emerald-50 text-emerald-600 rounded font-bold text-[10px]">话术</span>
            <span className="text-slate-500 line-clamp-2">{mnemonicData.script}</span>
          </div>
        </div>
      ) : (
        <p className="text-xs text-slate-500 italic line-clamp-2">{content || '暂无内容'}</p>
      )}

      {/* 重新生成结果 */}
      {regenResult && (
        <div className={`text-xs px-3 py-2 rounded-xl text-center font-medium ${
          regenResult.passed ? 'bg-green-50 text-green-600 border border-green-200' : 'bg-orange-50 text-orange-600 border border-orange-200'
        }`}>
          {regenResult.message}
        </div>
      )}

      {/* 操作按钮 */}
      {!isEditing && (
        <div className="flex items-center gap-2">
          <button onClick={onApprove} className="py-1.5 px-3 bg-green-50 hover:bg-green-100 text-green-700 border border-green-200 rounded-xl text-[11px] font-bold transition-all">
            通过
          </button>
          {!atLimit && (
            <button
              onClick={onRegenerate}
              disabled={isLoading}
              className="py-1.5 px-3 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-[11px] font-bold transition-all disabled:opacity-50 flex items-center gap-1"
            >
              {isLoading ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
              AI 修复
            </button>
          )}
          <button onClick={isMnemonic ? handleStartMnemonicEdit : onStartEdit} className="py-1.5 px-3 bg-slate-50 hover:bg-slate-100 text-slate-500 rounded-xl text-[11px] font-bold transition-all">
            <UserCog size={11} className="inline mr-1" />
            手动编辑
          </button>
        </div>
      )}
    </div>
  )
}

/* ===== 不适用助记维度区块 ===== */

function RejectedMnemonicsSection({ mnemonics, onRegenerated }: { mnemonics: any[]; onRegenerated: () => void }) {
  const [regenLoading, setRegenLoading] = useState<number | null>(null)
  const [regenMsg, setRegenMsg] = useState<{ id: number; ok: boolean; msg: string } | null>(null)

  const handleRegenerate = async (mn: any) => {
    setRegenLoading(mn.id)
    setRegenMsg(null)
    try {
      const res = await api.post<{ success: boolean; qc_passed: boolean; message: string }>(`/words/content-items/${mn.id}/regenerate`)
      setRegenMsg({ id: mn.id, ok: res.qc_passed, msg: res.message })
      setTimeout(() => { setRegenMsg(null); onRegenerated() }, 2000)
    } catch {
      setRegenMsg({ id: mn.id, ok: false, msg: '重新生成失败' })
      setTimeout(() => setRegenMsg(null), 3000)
    } finally {
      setRegenLoading(null)
    }
  }

  return (
    <div className="space-y-2 pt-2 border-t border-slate-100">
      <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest flex items-center gap-1">
        <Lightbulb size={11} /> 助记维度（不适用）
      </p>
      {mnemonics.map((mn: any) => {
        const typeLabel = DIMENSION_LABELS[mn.dimension] ?? mn.dimension
        return (
          <div key={mn.id} className="bg-slate-50 rounded-2xl p-3 border border-slate-100 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-[10px] px-2 py-0.5 bg-slate-200 text-slate-500 rounded-md font-bold">{typeLabel}</span>
              <span className="flex items-center gap-1 text-xs text-slate-400">
                <Ban size={11} /> 不适用
              </span>
            </div>
            <div className="flex items-center gap-2">
              {regenMsg?.id === mn.id && (
                <span className={`text-[10px] font-medium ${regenMsg.ok ? 'text-green-600' : 'text-orange-600'}`}>{regenMsg.msg}</span>
              )}
              <button
                onClick={() => handleRegenerate(mn)}
                disabled={regenLoading === mn.id}
                className="flex items-center gap-1 px-2.5 py-1 bg-blue-50 hover:bg-blue-100 text-blue-600 border border-blue-200 rounded-lg text-[10px] font-bold transition-all disabled:opacity-50"
              >
                {regenLoading === mn.id ? <Loader2 size={10} className="animate-spin" /> : <RefreshCw size={10} />}
                重新生成
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
