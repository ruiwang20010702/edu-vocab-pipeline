import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import {
  Search, RefreshCw, CheckCircle2, Loader2, X, PackagePlus,
  ArrowLeft, AlertCircle, Filter, ChevronDown, UserCog, Save,
  BookOpen, Layers, Volume2, Lightbulb, Ban,
} from 'lucide-react'
import { api, ApiError } from '../lib/api'
import type { ReviewItem, ReviewBatch, BatchDetail, WordDetail, ContentItem } from '../types'

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

/* ===== 质检结果展示 ===== */

type QcIssue = { rule_id: string; field: string; message: string }

function QcResultBanner({ passed, message, issues }: { passed: boolean; message: string; issues?: QcIssue[] }) {
  return (
    <div className={`text-xs px-3 py-2 rounded-xl font-medium ${passed ? 'bg-green-50 text-green-600 border border-green-200 text-center' : 'bg-orange-50 text-orange-600 border border-orange-200'}`}>
      <div className={passed ? '' : 'font-bold mb-1'}>{message}</div>
      {!passed && issues && issues.length > 0 && (
        <ul className="space-y-0.5 text-left">
          {issues.map((iss, i) => (
            <li key={i}>[{iss.rule_id}] {iss.message}</li>
          ))}
        </ul>
      )}
    </div>
  )
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

  // 一键AI修复
  const [batchFixing, setBatchFixing] = useState(false)

  // 已通过动画
  const [resolvedIds, setResolvedIds] = useState<Set<number>>(new Set())

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
      // 先标记为 resolved 播放动画，延迟后移除
      setResolvedIds(prev => new Set(prev).add(id))
      setActionLoading(null)
      setTimeout(() => {
        setItems(prev => prev.filter(i => i.id !== id))
        setResolvedIds(prev => { const next = new Set(prev); next.delete(id); return next })
      }, 1200)
    } catch (e) {
      console.error('审核通过失败', e)
      setActionLoading(null)
    }
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
        setResolvedIds(prev => new Set(prev).add(id))
        setTimeout(() => {
          setItems(prev => prev.filter(i => i.id !== id))
          setResolvedIds(prev => { const next = new Set(prev); next.delete(id); return next })
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

          {/* 一键AI修复按钮 */}
          <button
            onClick={async () => {
              setBatchFixing(true)
              const canRetryItems = filtered.filter(i => (i.content_item?.retry_count ?? 0) < 3)
              for (const item of canRetryItems) {
                await handleRegenerate(item.id)
              }
              setBatchFixing(false)
            }}
            disabled={counts.can_retry === 0 || actionLoading !== null || batchFixing}
            className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 text-white rounded-xl text-sm font-bold hover:bg-blue-700 transition-all disabled:opacity-40 shadow-lg shadow-blue-600/20 hover:-translate-y-0.5 active:scale-95"
          >
            {batchFixing ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            一键AI修复 ({counts.can_retry})
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
        <div className={`grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 transition-opacity ${batchFixing ? 'opacity-50 pointer-events-none' : ''}`}>
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
            resolvedIds={resolvedIds}
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
  group, onClose, onApprove, onRegenerate, onSaved, actionLoading, regenResult, resolvedIds,
}: {
  group: WordGroup
  onClose: () => void
  onApprove: (id: number) => void
  onRegenerate: (id: number) => void
  onSaved: () => void
  actionLoading: number | null
  regenResult: { id: number; passed: boolean; message: string } | null
  resolvedIds: Set<number>
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
  const [editResult, setEditResult] = useState<{ passed: boolean; message: string; issues?: Array<{ rule_id: string; field: string; message: string }> } | null>(null)

  // 直接编辑（非审核项，走 manual-edit API）
  const [directEditId, setDirectEditId] = useState<number | null>(null)
  const [directEditContent, setDirectEditContent] = useState('')
  const [directEditContentCn, setDirectEditContentCn] = useState('')
  const [directEditSaving, setDirectEditSaving] = useState(false)
  const [directEditMsg, setDirectEditMsg] = useState<{ ok: boolean; text: string; issues?: Array<{ rule_id: string; field: string; message: string }> } | null>(null)

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

  const startDirectEdit = (contentItem: { id: number; content: string; content_cn?: string | null }) => {
    setDirectEditId(contentItem.id)
    setDirectEditContent(contentItem.content)
    setDirectEditContentCn(contentItem.content_cn ?? '')
    setDirectEditMsg(null)
  }

  const cancelDirectEdit = () => {
    setDirectEditId(null)
    setDirectEditMsg(null)
  }

  const handleDirectEditSave = async (contentItemId: number, body: { content: string; content_cn?: string }) => {
    setDirectEditSaving(true)
    setDirectEditMsg(null)
    try {
      const res = await api.post<{ success: boolean; qc_passed: boolean; message: string; new_issues?: Array<{ rule_id: string; field: string; message: string }> }>(
        `/words/content-items/${contentItemId}/manual-edit`, body,
      )
      setDirectEditMsg({ ok: res.qc_passed, text: res.message, issues: res.new_issues })
      setTimeout(() => {
        setDirectEditMsg(null)
        cancelDirectEdit()
        // 刷新 wordDetail
        api.get<WordDetail>(`/words/${group.word_id}`)
          .then(data => setWordDetail(data))
          .catch(() => {})
        onSaved()
      }, 1500)
    } catch {
      setDirectEditMsg({ ok: false, text: '保存失败' })
      setTimeout(() => setDirectEditMsg(null), 3000)
    } finally {
      setDirectEditSaving(false)
    }
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
        setEditResult({ passed: false, message: res.message, issues: res.new_issues })
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
                      {(wordDetail.syllable?.content || wordDetail.phonetics[0].syllables) && (
                        <>
                          <span className="text-xs text-slate-400">·</span>
                          <span className="text-sm text-slate-500">{wordDetail.syllable?.content ?? wordDetail.phonetics[0].syllables}</span>
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
              {/* 义项头 */}
              {currentMeaning && (
                <div className="flex items-center gap-2">
                  <BookOpen size={14} className="text-blue-500" />
                  <span className="text-xs font-bold text-blue-600 uppercase bg-blue-50 px-2 py-0.5 rounded">{currentMeaning.pos}</span>
                  <span className="text-sm font-medium text-slate-900">{currentMeaning.definition}</span>
                </div>
              )}

              {/* 语块 — 完整展示 */}
              {currentMeaning && (() => {
                const chunk = currentMeaning.chunk
                const reviewItem = currentItems.find(i => i.content_item?.dimension === 'chunk')
                if (!chunk) return null
                return (
                  <ContentDimensionCard
                    icon={<Layers size={13} className="text-violet-400" />}
                    label="语块"
                    content={chunk}
                    reviewItem={reviewItem}
                    actionLoading={actionLoading}
                    resolvedIds={resolvedIds}
                    regenResult={regenResult}
                    editingId={editingId}
                    editContent={editContent}
                    editContentCn={editContentCn}
                    editResult={editResult}
                    editError={editError}
                    saving={saving}
                    onEditContentChange={setEditContent}
                    onEditContentCnChange={setEditContentCn}
                    onApprove={onApprove}
                    onRegenerate={onRegenerate}
                    onStartEdit={startEdit}
                    onCancelEdit={cancelEdit}
                    onSaveEdit={handleSaveEdit}
                    directEditId={directEditId}
                    directEditContent={directEditContent}
                    directEditContentCn={directEditContentCn}
                    directEditSaving={directEditSaving}
                    directEditMsg={directEditMsg}
                    onStartDirectEdit={startDirectEdit}
                    onCancelDirectEdit={cancelDirectEdit}
                    onDirectEditContentChange={setDirectEditContent}
                    onDirectEditContentCnChange={setDirectEditContentCn}
                    onDirectEditSave={handleDirectEditSave}
                  />
                )
              })()}

              {/* 例句 — 完整展示 */}
              {currentMeaning && (() => {
                const sentence = currentMeaning.sentence
                const reviewItem = currentItems.find(i => i.content_item?.dimension === 'sentence')
                if (!sentence) return null
                return (
                  <ContentDimensionCard
                    icon={<Volume2 size={13} className="text-emerald-400" />}
                    label="例句"
                    content={sentence}
                    reviewItem={reviewItem}
                    actionLoading={actionLoading}
                    resolvedIds={resolvedIds}
                    regenResult={regenResult}
                    editingId={editingId}
                    editContent={editContent}
                    editContentCn={editContentCn}
                    editResult={editResult}
                    editError={editError}
                    saving={saving}
                    onEditContentChange={setEditContent}
                    onEditContentCnChange={setEditContentCn}
                    onApprove={onApprove}
                    onRegenerate={onRegenerate}
                    onStartEdit={startEdit}
                    onCancelEdit={cancelEdit}
                    onSaveEdit={handleSaveEdit}
                    directEditId={directEditId}
                    directEditContent={directEditContent}
                    directEditContentCn={directEditContentCn}
                    directEditSaving={directEditSaving}
                    directEditMsg={directEditMsg}
                    onStartDirectEdit={startDirectEdit}
                    onCancelDirectEdit={cancelDirectEdit}
                    onDirectEditContentChange={setDirectEditContent}
                    onDirectEditContentCnChange={setDirectEditContentCn}
                    onDirectEditSave={handleDirectEditSave}
                  />
                )
              })()}

              {/* 助记 — 全部 4 种类型 */}
              {currentMeaning && (currentMeaning.mnemonics ?? []).length > 0 && (
                <MnemonicReviewSection
                  mnemonics={currentMeaning.mnemonics ?? []}
                  reviewItems={currentItems.filter(i => i.content_item?.dimension?.startsWith('mnemonic_'))}
                  actionLoading={actionLoading}
                  resolvedIds={resolvedIds}
                  regenResult={regenResult}
                  editingId={editingId}
                  editContent={editContent}
                  editContentCn={editContentCn}
                  editResult={editResult}
                  editError={editError}
                  saving={saving}
                  onEditContentChange={setEditContent}
                  onEditContentCnChange={setEditContentCn}
                  onApprove={onApprove}
                  onRegenerate={onRegenerate}
                  onStartEdit={startEdit}
                  onCancelEdit={cancelEdit}
                  onSaveEdit={handleSaveEdit}
                  onRegenerated={() => {
                    api.get<WordDetail>(`/words/${group.word_id}`)
                      .then(data => setWordDetail(data))
                      .catch(() => {})
                  }}
                  directEditId={directEditId}
                  directEditContent={directEditContent}
                  directEditSaving={directEditSaving}
                  directEditMsg={directEditMsg}
                  onStartDirectEdit={startDirectEdit}
                  onCancelDirectEdit={cancelDirectEdit}
                  onDirectEditContentChange={setDirectEditContent}
                  onDirectEditSave={handleDirectEditSave}
                />
              )}

              {/* 词级维度（音节等） */}
              {wordLevelItems.length > 0 && meaningIdx === 0 && (
                <div className="space-y-3 pt-2 border-t border-slate-100">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">词级维度</p>
                  <AnimatePresence>
                  {wordLevelItems.map(item => (
                    <ReviewDimensionCard
                      key={item.id}
                      item={item}
                      isLoading={actionLoading === item.id}
                      isResolved={resolvedIds.has(item.id)}
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
                  </AnimatePresence>
                </div>
              )}
            </div>
          </>
        )}
      </motion.div>
    </motion.div>
  )
}

/* ===== 内容维度完整展示卡片（语块/例句） ===== */

const STATUS_BADGE: Record<string, { bg: string; text: string; label: string }> = {
  approved: { bg: 'bg-green-50 border-green-200', text: 'text-green-600', label: '已通过' },
  rejected: { bg: 'bg-slate-50 border-slate-200', text: 'text-slate-400', label: '不适用' },
  layer1_failed: { bg: 'bg-rose-50 border-rose-200', text: 'text-rose-600', label: '异常' },
  layer2_failed: { bg: 'bg-rose-50 border-rose-200', text: 'text-rose-600', label: '异常' },
  layer1_passed: { bg: 'bg-blue-50 border-blue-200', text: 'text-blue-600', label: '质检中' },
  layer2_passed: { bg: 'bg-blue-50 border-blue-200', text: 'text-blue-600', label: '质检中' },
  pending: { bg: 'bg-slate-50 border-slate-200', text: 'text-slate-400', label: '待处理' },
}

function ContentDimensionCard({
  icon, label, content, reviewItem,
  actionLoading, resolvedIds, regenResult,
  editingId, editContent, editContentCn, editResult, editError, saving,
  onEditContentChange, onEditContentCnChange,
  onApprove, onRegenerate, onStartEdit, onCancelEdit, onSaveEdit,
  directEditId, directEditContent, directEditContentCn, directEditSaving, directEditMsg,
  onStartDirectEdit, onCancelDirectEdit, onDirectEditContentChange, onDirectEditContentCnChange, onDirectEditSave,
}: {
  icon: React.ReactNode
  label: string
  content: any
  reviewItem?: ReviewItem
  actionLoading: number | null
  resolvedIds: Set<number>
  regenResult: { id: number; passed: boolean; message: string } | null
  editingId: number | null
  editContent: string
  editContentCn: string
  editResult: { passed: boolean; message: string; issues?: QcIssue[] } | null
  editError: string
  saving: boolean
  onEditContentChange: (v: string) => void
  onEditContentCnChange: (v: string) => void
  onApprove: (id: number) => void
  onRegenerate: (id: number) => void
  onStartEdit: (item: ReviewItem) => void
  onCancelEdit: () => void
  onSaveEdit: (id: number) => void
  directEditId: number | null
  directEditContent: string
  directEditContentCn: string
  directEditSaving: boolean
  directEditMsg: { ok: boolean; text: string; issues?: QcIssue[] } | null
  onStartDirectEdit: (ci: { id: number; content: string; content_cn?: string | null }) => void
  onCancelDirectEdit: () => void
  onDirectEditContentChange: (v: string) => void
  onDirectEditContentCnChange: (v: string) => void
  onDirectEditSave: (id: number, body: { content: string; content_cn?: string }) => void
}) {
  const status = content.qc_status ?? 'pending'
  const badge = STATUS_BADGE[status] ?? STATUS_BADGE.pending
  const hasIssue = !!reviewItem
  const isDirectEditing = directEditId === content.id

  return (
    <div className={`rounded-2xl border p-4 space-y-2 ${hasIssue ? 'bg-white border-rose-200' : 'bg-slate-50 border-slate-100'}`}>
      {/* 标题行 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {icon}
          <span className="text-xs font-bold text-slate-700">{label}</span>
        </div>
        <span className={`flex items-center gap-1 text-[10px] font-bold ${badge.text}`}>
          {status === 'approved' && <CheckCircle2 size={10} />}
          {hasIssue && <AlertCircle size={10} />}
          {badge.label}
        </span>
      </div>

      {/* 异常提示 */}
      {reviewItem?.issues?.[0]?.message && (
        <p className="text-xs text-rose-600/80 bg-rose-50/50 px-3 py-2 rounded-xl border border-rose-100/50 leading-relaxed">
          {reviewItem.issues[0].message}
        </p>
      )}

      {/* 内容 — 双击编辑 */}
      {isDirectEditing ? (
        <div className="space-y-2">
          <textarea value={directEditContent} onChange={e => onDirectEditContentChange(e.target.value)} rows={2}
            className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm text-slate-900 focus:outline-none focus:border-blue-300 resize-none" />
          <textarea value={directEditContentCn} onChange={e => onDirectEditContentCnChange(e.target.value)} rows={1} placeholder="中文翻译（可选）"
            className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-700 focus:outline-none focus:border-blue-300 resize-none placeholder:text-slate-400" />
          {directEditMsg && <QcResultBanner passed={directEditMsg.ok} message={directEditMsg.text} issues={directEditMsg.issues} />}
          <div className="flex items-center gap-2">
            <button onClick={() => onDirectEditSave(content.id, { content: directEditContent, content_cn: directEditContentCn || undefined })} disabled={directEditSaving || !directEditContent.trim()}
              className="flex-1 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-600 border border-blue-200 rounded-xl text-xs font-bold flex items-center justify-center gap-1 disabled:opacity-50">
              {directEditSaving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />} 保存并质检
            </button>
            <button onClick={onCancelDirectEdit} className="px-3 py-1.5 text-slate-400 hover:text-slate-600 text-xs font-bold">取消</button>
          </div>
        </div>
      ) : content.content && (
        <div
          className="space-y-1 rounded-lg px-1 -mx-1 cursor-text hover:bg-blue-50/50 transition-colors"
          onDoubleClick={() => onStartDirectEdit(content)}
          title="双击编辑"
        >
          <p className="text-sm text-slate-800">{content.content}</p>
          {content.content_cn && <p className="text-xs text-slate-500">{content.content_cn}</p>}
        </div>
      )}

      {/* 有审核项 → 展示审核按钮 */}
      {reviewItem && (
        <ReviewDimensionCard
          item={reviewItem}
          isLoading={actionLoading === reviewItem.id}
          isResolved={resolvedIds.has(reviewItem.id)}
          regenResult={regenResult?.id === reviewItem.id ? regenResult : null}
          isEditing={editingId === reviewItem.id}
          editContent={editContent}
          editContentCn={editContentCn}
          editResult={editResult}
          editError={editError}
          saving={saving}
          onEditContentChange={onEditContentChange}
          onEditContentCnChange={onEditContentCnChange}
          onApprove={() => onApprove(reviewItem.id)}
          onRegenerate={() => onRegenerate(reviewItem.id)}
          onStartEdit={() => onStartEdit(reviewItem)}
          onCancelEdit={onCancelEdit}
          onSaveEdit={() => onSaveEdit(reviewItem.id)}
          embedded
        />
      )}
    </div>
  )
}

/* ===== 助记完整审核区块 ===== */

const ALL_MNEMONIC_DIMS = [
  'mnemonic_root_affix', 'mnemonic_word_in_word',
  'mnemonic_sound_meaning', 'mnemonic_exam_app',
] as const

function MnemonicReviewSection({
  mnemonics, reviewItems, actionLoading, resolvedIds, regenResult,
  editingId, editContent, editContentCn, editResult, editError, saving,
  onEditContentChange, onEditContentCnChange,
  onApprove, onRegenerate, onStartEdit, onCancelEdit, onSaveEdit,
  onRegenerated,
  directEditId, directEditContent, directEditSaving, directEditMsg,
  onStartDirectEdit, onCancelDirectEdit, onDirectEditContentChange, onDirectEditSave,
}: {
  mnemonics: any[]
  reviewItems: ReviewItem[]
  actionLoading: number | null
  resolvedIds: Set<number>
  regenResult: { id: number; passed: boolean; message: string } | null
  editingId: number | null
  editContent: string
  editContentCn: string
  editResult: { passed: boolean; message: string; issues?: QcIssue[] } | null
  editError: string
  saving: boolean
  onEditContentChange: (v: string) => void
  onEditContentCnChange: (v: string) => void
  onApprove: (id: number) => void
  onRegenerate: (id: number) => void
  onStartEdit: (item: ReviewItem) => void
  onCancelEdit: () => void
  onSaveEdit: (id: number) => void
  onRegenerated: () => void
  directEditId: number | null
  directEditContent: string
  directEditSaving: boolean
  directEditMsg: { ok: boolean; text: string; issues?: QcIssue[] } | null
  onStartDirectEdit: (ci: { id: number; content: string; content_cn?: string | null }) => void
  onCancelDirectEdit: () => void
  onDirectEditContentChange: (v: string) => void
  onDirectEditSave: (id: number, body: { content: string; content_cn?: string }) => void
}) {
  const mnMap = new Map<string, any>()
  for (const mn of mnemonics) mnMap.set(mn.dimension, mn)

  const reviewMap = new Map<string, ReviewItem>()
  for (const ri of reviewItems) {
    if (ri.content_item?.dimension) reviewMap.set(ri.content_item.dimension, ri)
  }

  // 分类：有内容的（通过/异常）和 rejected 的
  const rejectedMns = ALL_MNEMONIC_DIMS
    .map(d => mnMap.get(d))
    .filter(mn => mn && (mn.qc_status === 'rejected' || !mn.content))

  return (
    <div className="space-y-3 pt-2 border-t border-slate-100">
      <div className="flex items-center gap-1.5">
        <Lightbulb size={13} className="text-yellow-500" />
        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">助记（4 种类型）</span>
      </div>

      {ALL_MNEMONIC_DIMS.map(dim => {
        const mn = mnMap.get(dim)
        if (!mn) return null
        const typeLabel = DIMENSION_LABELS[dim] ?? dim
        const isRejected = mn.qc_status === 'rejected' || !mn.content
        const reviewItem = reviewMap.get(dim)

        if (isRejected) return null // 下面统一渲染 rejected

        // 有内容的助记
        const parsed = parseMnemonicJson(mn.content)
        const status = mn.qc_status ?? 'pending'
        const badge = STATUS_BADGE[status] ?? STATUS_BADGE.pending
        const hasIssue = !!reviewItem

        return (
          <div key={dim} className={`rounded-2xl border p-4 space-y-2 ${hasIssue ? 'bg-white border-rose-200' : 'bg-yellow-50/60 border-yellow-100'}`}>
            <div className="flex items-center justify-between">
              <span className={`text-[10px] px-2 py-0.5 rounded-md font-bold ${hasIssue ? 'bg-rose-50 text-rose-600' : 'bg-yellow-100 text-yellow-700'}`}>{typeLabel}</span>
              <span className={`flex items-center gap-1 text-[10px] font-bold ${badge.text}`}>
                {status === 'approved' && <CheckCircle2 size={10} />}
                {hasIssue && <AlertCircle size={10} />}
                {badge.label}
              </span>
            </div>

            {/* 异常提示 */}
            {reviewItem?.issues?.[0]?.message && (
              <p className="text-xs text-rose-600/80 bg-rose-50/50 px-3 py-2 rounded-xl border border-rose-100/50 leading-relaxed">
                {reviewItem.issues[0].message}
              </p>
            )}

            {/* 助记内容 — 双击编辑 */}
            {directEditId === mn.id ? (
              <MnemonicDirectEditForm
                mnId={mn.id}
                initialContent={mn.content}
                directEditContent={directEditContent}
                directEditSaving={directEditSaving}
                directEditMsg={directEditMsg}
                onDirectEditContentChange={onDirectEditContentChange}
                onDirectEditSave={onDirectEditSave}
                onCancelDirectEdit={onCancelDirectEdit}
              />
            ) : parsed ? (
              <div
                className="space-y-2 text-xs rounded-lg px-1 -mx-1 cursor-text hover:bg-blue-50/50 transition-colors"
                onDoubleClick={() => onStartDirectEdit(mn)}
                title="双击编辑"
              >
                {parsed.formula && (
                  <div className="flex items-start gap-2">
                    <span className="shrink-0 px-1.5 py-0.5 bg-violet-50 text-violet-600 rounded font-bold text-[10px]">公式</span>
                    <span className="text-slate-700">{parsed.formula}</span>
                  </div>
                )}
                {parsed.chant && (
                  <div className="flex items-start gap-2">
                    <span className="shrink-0 px-1.5 py-0.5 bg-amber-50 text-amber-600 rounded font-bold text-[10px]">口诀</span>
                    <span className="text-slate-700">{parsed.chant}</span>
                  </div>
                )}
                {parsed.script && (
                  <div className="flex items-start gap-2">
                    <span className="shrink-0 px-1.5 py-0.5 bg-emerald-50 text-emerald-600 rounded font-bold text-[10px]">话术</span>
                    <span className="text-slate-500">{parsed.script}</span>
                  </div>
                )}
              </div>
            ) : (
              <p
                className="text-xs text-slate-500 italic rounded-lg px-1 -mx-1 cursor-text hover:bg-blue-50/50 transition-colors"
                onDoubleClick={() => onStartDirectEdit(mn)}
                title="双击编辑"
              >{mn.content || '暂无内容'}</p>
            )}

            {/* 有审核项 → 审核按钮 */}
            {reviewItem && (
              <ReviewDimensionCard
                item={reviewItem}
                isLoading={actionLoading === reviewItem.id}
                isResolved={resolvedIds.has(reviewItem.id)}
                regenResult={regenResult?.id === reviewItem.id ? regenResult : null}
                isEditing={editingId === reviewItem.id}
                editContent={editContent}
                editContentCn={editContentCn}
                editResult={editResult}
                editError={editError}
                saving={saving}
                onEditContentChange={onEditContentChange}
                onEditContentCnChange={onEditContentCnChange}
                onApprove={() => onApprove(reviewItem.id)}
                onRegenerate={() => onRegenerate(reviewItem.id)}
                onStartEdit={() => onStartEdit(reviewItem)}
                onCancelEdit={onCancelEdit}
                onSaveEdit={() => onSaveEdit(reviewItem.id)}
                embedded
              />
            )}
          </div>
        )
      })}

      {/* Rejected 助记维度 */}
      {rejectedMns.length > 0 && (
        <RejectedMnemonicsSection mnemonics={rejectedMns} onRegenerated={onRegenerated} />
      )}
    </div>
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
  item, isLoading, isResolved, regenResult, isEditing,
  editContent, editContentCn, editResult, editError, saving,
  onEditContentChange, onEditContentCnChange,
  onApprove, onRegenerate, onStartEdit, onCancelEdit, onSaveEdit,
  embedded = false,
}: {
  item: ReviewItem
  isLoading: boolean
  isResolved: boolean
  regenResult: { passed: boolean; message: string } | null
  isEditing: boolean
  editContent: string
  editContentCn: string
  editResult: { passed: boolean; message: string; issues?: QcIssue[] } | null
  editError: string
  saving: boolean
  onEditContentChange: (v: string) => void
  onEditContentCnChange: (v: string) => void
  onApprove: () => void
  onRegenerate: () => void
  onStartEdit: () => void
  onCancelEdit: () => void
  onSaveEdit: () => void
  embedded?: boolean
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

  // 编辑表单（共享：embedded 和独立模式都用）
  const editForm = isEditing ? (
    isMnemonic ? (
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
        {editResult && <QcResultBanner passed={editResult.passed} message={editResult.message} issues={editResult.issues} />}
        {editError && <p className="text-xs text-red-600 text-center">{editError}</p>}
        <div className="flex items-center gap-2">
          <button onClick={handleMnemonicSave} disabled={saving} className="flex-1 py-1.5 bg-yellow-50 hover:bg-yellow-100 text-yellow-700 border border-yellow-200 rounded-xl text-xs font-bold flex items-center justify-center gap-1 disabled:opacity-50">
            {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />} 保存
          </button>
          <button onClick={onCancelEdit} className="px-3 py-1.5 text-slate-400 hover:text-slate-600 text-xs font-bold">取消</button>
        </div>
      </div>
    ) : (
      <div className="space-y-2">
        <textarea value={editContent} onChange={e => onEditContentChange(e.target.value)} rows={3}
          className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm text-slate-900 focus:outline-none focus:border-blue-300 resize-none" />
        <textarea value={editContentCn} onChange={e => onEditContentCnChange(e.target.value)} rows={2} placeholder="中文翻译（可选）"
          className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-700 focus:outline-none focus:border-blue-300 resize-none placeholder:text-slate-400" />
        {editResult && <QcResultBanner passed={editResult.passed} message={editResult.message} issues={editResult.issues} />}
        {editError && <p className="text-xs text-red-600 text-center">{editError}</p>}
        <div className="flex items-center gap-2">
          <button onClick={onSaveEdit} disabled={saving} className="flex-1 py-1.5 bg-yellow-50 hover:bg-yellow-100 text-yellow-700 border border-yellow-200 rounded-xl text-xs font-bold flex items-center justify-center gap-1 disabled:opacity-50">
            {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />} 保存
          </button>
          <button onClick={onCancelEdit} className="px-3 py-1.5 text-slate-400 hover:text-slate-600 text-xs font-bold">取消</button>
        </div>
      </div>
    )
  ) : null

  const actionButtons = !isEditing ? (
    <div className="flex items-center gap-2 pt-1">
      <button onClick={onApprove} className="py-1.5 px-3 bg-green-50 hover:bg-green-100 text-green-700 border border-green-200 rounded-xl text-[11px] font-bold transition-all">
        通过
      </button>
      {!atLimit && (
        <button onClick={onRegenerate} disabled={isLoading}
          className="py-1.5 px-3 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-[11px] font-bold transition-all disabled:opacity-50 flex items-center gap-1">
          {isLoading ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
          AI 修复
        </button>
      )}
      <button onClick={isMnemonic ? handleStartMnemonicEdit : onStartEdit} className="py-1.5 px-3 bg-slate-50 hover:bg-slate-100 text-slate-500 rounded-xl text-[11px] font-bold transition-all">
        <UserCog size={11} className="inline mr-1" /> 手动编辑
      </button>
      <span className={`text-[10px] font-bold ml-auto ${atLimit ? 'text-rose-500' : 'text-slate-400'}`}>{retryCount}/3</span>
    </div>
  ) : null

  const regenResultBanner = regenResult ? (
    <div className={`text-xs px-3 py-2 rounded-xl text-center font-medium ${regenResult.passed ? 'bg-green-50 text-green-600 border border-green-200' : 'bg-orange-50 text-orange-600 border border-orange-200'}`}>
      {regenResult.message}
    </div>
  ) : null

  // embedded 模式：只渲染操作按钮和编辑表单，不渲染外层卡片
  if (embedded) {
    return (
      <div className="relative space-y-2">
        <AnimatePresence>
          {isResolved && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="absolute inset-0 z-10 bg-gradient-to-br from-green-50/95 to-emerald-50/95 backdrop-blur-[2px] rounded-xl flex items-center justify-center"
            >
              <motion.div
                initial={{ scale: 0, rotate: -180 }}
                animate={{ scale: 1, rotate: 0 }}
                transition={{ type: 'spring', stiffness: 260, damping: 20 }}
                className="flex flex-col items-center gap-2"
              >
                <div className="w-10 h-10 bg-green-500 rounded-full flex items-center justify-center shadow-lg shadow-green-200">
                  <CheckCircle2 size={22} className="text-white" />
                </div>
                <span className="text-xs font-bold text-green-700">已通过</span>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
        {editForm}
        {regenResultBanner}
        {actionButtons}
      </div>
    )
  }

  // 独立模式：完整卡片（用于词级维度等）
  return (
    <motion.div
      layout
      exit={{ opacity: 0, scale: 0.9, y: -10, transition: { duration: 0.4 } }}
      className={`relative bg-white rounded-2xl border p-4 space-y-3 transition-all overflow-hidden ${
        isResolved ? 'border-green-400 ring-2 ring-green-200' : isLoading ? 'border-blue-400 ring-1 ring-blue-200' : 'border-slate-200'
      }`}
    >
      <AnimatePresence>
        {isResolved && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="absolute inset-0 z-10 bg-gradient-to-br from-green-50/95 to-emerald-50/95 backdrop-blur-[2px] flex items-center justify-center"
          >
            <motion.div
              initial={{ scale: 0, rotate: -180 }}
              animate={{ scale: 1, rotate: 0 }}
              transition={{ type: 'spring', stiffness: 260, damping: 20 }}
              className="flex flex-col items-center gap-2"
            >
              <div className="w-12 h-12 bg-green-500 rounded-full flex items-center justify-center shadow-lg shadow-green-200">
                <CheckCircle2 size={28} className="text-white" />
              </div>
              <span className="text-sm font-bold text-green-700">已通过</span>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* 维度标题 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="px-2 py-0.5 bg-rose-50 text-rose-600 text-[10px] font-bold rounded-lg border border-rose-100">{dimLabel}</span>
          <span className={`text-[10px] font-bold ${atLimit ? 'text-rose-500' : 'text-slate-400'}`}>{retryCount}/3</span>
        </div>
        {issueMsg && <span className="flex items-center gap-1 text-[10px] text-rose-500"><AlertCircle size={10} /> 异常</span>}
      </div>

      {issueMsg && (
        <p className="text-xs text-rose-600/80 bg-rose-50/50 px-3 py-2 rounded-xl border border-rose-100/50 leading-relaxed">{issueMsg}</p>
      )}

      {/* 内容预览 */}
      {!isEditing && (isMnemonic && mnemonicData ? (
        <div className="space-y-2 text-xs">
          <div className="flex items-start gap-2"><span className="shrink-0 px-1.5 py-0.5 bg-violet-50 text-violet-600 rounded font-bold text-[10px]">公式</span><span className="text-slate-700">{mnemonicData.formula}</span></div>
          <div className="flex items-start gap-2"><span className="shrink-0 px-1.5 py-0.5 bg-amber-50 text-amber-600 rounded font-bold text-[10px]">口诀</span><span className="text-slate-700">{mnemonicData.chant}</span></div>
          <div className="flex items-start gap-2"><span className="shrink-0 px-1.5 py-0.5 bg-emerald-50 text-emerald-600 rounded font-bold text-[10px]">话术</span><span className="text-slate-500 line-clamp-2">{mnemonicData.script}</span></div>
        </div>
      ) : !isEditing && (
        <p className="text-xs text-slate-500 italic line-clamp-2">{content || '暂无内容'}</p>
      ))}

      {editForm}
      {regenResultBanner}
      {actionButtons}
    </motion.div>
  )
}

/* ===== 助记直接编辑表单 ===== */

function MnemonicDirectEditForm({
  mnId, initialContent, directEditContent, directEditSaving, directEditMsg,
  onDirectEditContentChange, onDirectEditSave, onCancelDirectEdit,
}: {
  mnId: number
  initialContent: string
  directEditContent: string
  directEditSaving: boolean
  directEditMsg: { ok: boolean; text: string; issues?: QcIssue[] } | null
  onDirectEditContentChange: (v: string) => void
  onDirectEditSave: (id: number, body: { content: string }) => void
  onCancelDirectEdit: () => void
}) {
  const parsed = parseMnemonicJson(initialContent)
  const [formula, setFormula] = useState(parsed?.formula ?? '')
  const [chant, setChant] = useState(parsed?.chant ?? '')
  const [script, setScript] = useState(parsed?.script ?? '')

  const handleSave = () => {
    const content = buildMnemonicJson(formula, chant, script)
    onDirectEditSave(mnId, { content })
  }

  return (
    <div className="space-y-2">
      <div>
        <label className="text-[10px] font-bold text-slate-400 uppercase">核心公式</label>
        <textarea value={formula} onChange={e => setFormula(e.target.value)} rows={2}
          className="w-full mt-1 px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm text-slate-900 focus:outline-none focus:border-blue-300 resize-none" />
      </div>
      <div>
        <label className="text-[10px] font-bold text-slate-400 uppercase">助记口诀</label>
        <textarea value={chant} onChange={e => setChant(e.target.value)} rows={2}
          className="w-full mt-1 px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm text-slate-900 focus:outline-none focus:border-blue-300 resize-none" />
      </div>
      <div>
        <label className="text-[10px] font-bold text-slate-400 uppercase">老师话术</label>
        <textarea value={script} onChange={e => setScript(e.target.value)} rows={3}
          className="w-full mt-1 px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm text-slate-900 focus:outline-none focus:border-blue-300 resize-none" />
      </div>
      {directEditMsg && <QcResultBanner passed={directEditMsg.ok} message={directEditMsg.text} issues={directEditMsg.issues} />}
      <div className="flex items-center gap-2">
        <button onClick={handleSave} disabled={directEditSaving || !formula.trim()}
          className="flex-1 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-600 border border-blue-200 rounded-xl text-xs font-bold flex items-center justify-center gap-1 disabled:opacity-50">
          {directEditSaving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />} 保存并质检
        </button>
        <button onClick={onCancelDirectEdit} className="px-3 py-1.5 text-slate-400 hover:text-slate-600 text-xs font-bold">取消</button>
      </div>
    </div>
  )
}

/* ===== 不适用助记维度区块 ===== */

function RejectedMnemonicsSection({ mnemonics, onRegenerated }: { mnemonics: any[]; onRegenerated: () => void }) {
  const [regenLoading, setRegenLoading] = useState<number | null>(null)
  const [regenMsg, setRegenMsg] = useState<{ id: number; ok: boolean; msg: string; issues?: QcIssue[] } | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editFormula, setEditFormula] = useState('')
  const [editChant, setEditChant] = useState('')
  const [editScript, setEditScript] = useState('')
  const [saving, setSaving] = useState(false)

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

  const startEdit = (mn: any) => {
    setEditingId(mn.id)
    setEditFormula('')
    setEditChant('')
    setEditScript('')
    setRegenMsg(null)
  }

  const handleSaveEdit = async (mn: any) => {
    setSaving(true)
    setRegenMsg(null)
    try {
      const content = JSON.stringify({ formula: editFormula, chant: editChant, script: editScript })
      const res = await api.post<{ success: boolean; qc_passed: boolean; message: string; new_issues?: QcIssue[] }>(`/words/content-items/${mn.id}/manual-edit`, { content })
      setRegenMsg({ id: mn.id, ok: res.qc_passed, msg: res.message, issues: res.new_issues })
      if (res.qc_passed) {
        setTimeout(() => { setRegenMsg(null); setEditingId(null); onRegenerated() }, 1500)
      } else {
        setTimeout(() => setRegenMsg(null), 3000)
      }
    } catch {
      setRegenMsg({ id: mn.id, ok: false, msg: '保存失败' })
      setTimeout(() => setRegenMsg(null), 3000)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-2 pt-2 border-t border-slate-100">
      <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest flex items-center gap-1">
        <Lightbulb size={11} /> 助记维度（不适用）
      </p>
      {mnemonics.map((mn: any) => {
        const typeLabel = DIMENSION_LABELS[mn.dimension] ?? mn.dimension
        const isEditing = editingId === mn.id

        if (isEditing) {
          return (
            <div key={mn.id} className="bg-white rounded-2xl p-4 border border-blue-200 space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-[10px] px-2 py-0.5 bg-blue-100 text-blue-600 rounded-md font-bold">{typeLabel}</span>
                <span className="text-[10px] text-slate-400">手动编辑</span>
              </div>
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
                <textarea value={editScript} onChange={e => setEditScript(e.target.value)} rows={3}
                  className="w-full mt-1 px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm text-slate-900 focus:outline-none focus:border-blue-300 resize-none" />
              </div>
              {regenMsg?.id === mn.id && <QcResultBanner passed={regenMsg.ok} message={regenMsg.msg} issues={regenMsg.issues} />}
              <div className="flex items-center gap-2">
                <button onClick={() => handleSaveEdit(mn)} disabled={saving || !editFormula.trim()}
                  className="flex-1 py-1.5 bg-yellow-50 hover:bg-yellow-100 text-yellow-700 border border-yellow-200 rounded-xl text-xs font-bold flex items-center justify-center gap-1 disabled:opacity-50">
                  {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                  保存并质检
                </button>
                <button onClick={() => setEditingId(null)} className="px-3 py-1.5 text-slate-400 hover:text-slate-600 text-xs font-bold">取消</button>
              </div>
            </div>
          )
        }

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
              <button
                onClick={() => startEdit(mn)}
                className="flex items-center gap-1 px-2.5 py-1 bg-slate-50 hover:bg-slate-100 text-slate-500 border border-slate-200 rounded-lg text-[10px] font-bold transition-all"
              >
                <UserCog size={10} />
                手动编辑
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
