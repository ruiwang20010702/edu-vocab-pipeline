import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import {
  Search, RefreshCw, CheckCircle2, Loader2, X, PackagePlus,
  ArrowLeft, AlertCircle, Filter, ChevronDown, UserCog, Save,
  History, ChevronUp,
} from 'lucide-react'
import { api, ApiError } from '../lib/api'
import type { ReviewItem, ReviewBatch, BatchDetail } from '../types'

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
  mnemonic_root_affix: '助记',
  mnemonic_word_in_word: '助记',
  mnemonic_sound_meaning: '助记',
  mnemonic_exam_app: '助记',
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

export default function ReviewPage({ onBack }: Props) {
  const [items, setItems] = useState<ReviewItem[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [tab, setTab] = useState<Tab>('all')
  const [selectedItem, setSelectedItem] = useState<ReviewItem | null>(null)
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
      if (selectedItem?.id === id) setSelectedItem(null)
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
          if (selectedItem?.id === id) setSelectedItem(null)
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

  const canRetry = filtered.filter(i => (i.content_item?.retry_count ?? 0) < 3)
  const mustManual = filtered.filter(i => (i.content_item?.retry_count ?? 0) >= 3)

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
            <p className="text-sm text-white/70">{counts.total} 个异常项待处理</p>
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
              // 批量重新生成所有 can_retry 项
              canRetry.forEach(item => handleRegenerate(item.id))
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

      {/* Loading */}
      {loading ? (
        <div className="flex items-center justify-center h-40">
          <Loader2 size={32} className="animate-spin text-blue-600" />
        </div>
      ) : filtered.length === 0 ? (
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
        <div className="space-y-8">
          {/* 可 AI 修复 */}
          {(tab === 'all' || tab === 'can_retry') && canRetry.length > 0 && (
            <div className="space-y-4">
              <h3 className="text-sm font-bold text-white/70 uppercase tracking-widest">
                待修复（可 AI 修复）（{canRetry.length} 个）
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {canRetry.map(item => (
                  <WordCard
                    key={item.id}
                    item={item}
                    isLoading={actionLoading === item.id}
                    regenResult={regenResult?.id === item.id ? regenResult : null}
                    onRepair={() => handleRegenerate(item.id)}
                    onEdit={() => setSelectedItem(item)}
                  />
                ))}
              </div>
            </div>
          )}

          {/* 已达上限 */}
          {(tab === 'all' || tab === 'must_manual') && mustManual.length > 0 && (
            <div className="space-y-4">
              <h3 className="text-sm font-bold text-rose-300 uppercase tracking-widest">
                已达上限（必须人工修改）（{mustManual.length} 个）
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {mustManual.map(item => (
                  <WordCard
                    key={item.id}
                    item={item}
                    isLoading={actionLoading === item.id}
                    regenResult={regenResult?.id === item.id ? regenResult : null}
                    onRepair={() => handleRegenerate(item.id)}
                    onEdit={() => setSelectedItem(item)}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 详情弹窗 */}
      <AnimatePresence>
        {selectedItem && (
          <ReviewDetailModal
            item={selectedItem}
            onClose={() => setSelectedItem(null)}
            onApprove={handleApprove}
            onRegenerate={handleRegenerate}
            onSaved={loadItems}
          />
        )}
      </AnimatePresence>
    </div>
  )
}

/* ===== 卡片组件 ===== */

function WordCard({ item, isLoading, regenResult, onRepair, onEdit }: {
  item: ReviewItem
  isLoading: boolean
  regenResult: { passed: boolean; message: string } | null
  onRepair: () => void
  onEdit: () => void
}) {
  const dim = item.content_item?.dimension ?? ''
  const dimLabel = DIMENSION_LABELS[dim] ?? dim
  const retryCount = item.content_item?.retry_count ?? 0
  const atLimit = retryCount >= 3
  const issueMsg = item.issues?.[0]?.message ?? ''
  const content = item.content_item?.content ?? ''

  return (
    <motion.div
      layout
      className={`bg-white rounded-[24px] border p-5 space-y-4 transition-all ${
        isLoading ? 'border-blue-400 shadow-md ring-1 ring-blue-200' : 'border-white shadow-sm hover:border-blue-200 hover:shadow-md'
      }`}
    >
      {/* Header: word + retry */}
      <div className="flex items-start justify-between">
        <div className="space-y-1">
          <h3 className="text-lg font-bold text-slate-900">{item.word?.word}</h3>
          <p className="text-[10px] font-bold text-rose-600 uppercase tracking-tight flex items-center gap-1">
            <AlertCircle size={10} />
            {dimLabel} - {retryCount > 0 ? '修复失败' : '质检异常'}
          </p>
        </div>
        <span className={`text-[10px] font-bold ${atLimit ? 'text-rose-600' : 'text-slate-400'}`}>
          retry_count: {retryCount}/3
        </span>
      </div>

      {/* Issue */}
      {issueMsg && (
        <div className="p-3 bg-rose-50/50 rounded-xl border border-rose-100/50">
          <p className="text-xs text-rose-700/80 leading-relaxed line-clamp-2">{issueMsg}</p>
        </div>
      )}

      {/* Regen result */}
      {regenResult && (
        <div className={`text-xs px-3 py-2 rounded-xl text-center font-medium ${
          regenResult.passed ? 'bg-green-50 text-green-600 border border-green-200' : 'bg-orange-50 text-orange-600 border border-orange-200'
        }`}>
          {regenResult.message}
        </div>
      )}

      {/* Content preview */}
      <div className="space-y-1">
        <p className="text-[10px] font-bold text-slate-400 uppercase">当前内容预览</p>
        <p className="text-xs text-slate-500 line-clamp-2 italic">
          {content || '暂无预览内容'}
        </p>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 pt-2">
        {atLimit ? (
          <button
            onClick={onEdit}
            className="flex-1 flex items-center justify-center gap-2 py-2 bg-slate-900 text-white rounded-xl text-xs font-bold hover:bg-black transition-colors"
          >
            <UserCog size={14} />
            人工修改
          </button>
        ) : (
          <>
            <button
              onClick={onRepair}
              disabled={isLoading}
              className="flex-1 flex items-center justify-center gap-2 py-2 bg-blue-600 text-white rounded-xl text-xs font-bold hover:bg-blue-700 transition-all disabled:opacity-50 shadow-sm shadow-blue-200"
            >
              {isLoading ? (
                <><Loader2 size={14} className="animate-spin" /> 修复中...</>
              ) : (
                <><RefreshCw size={14} /> AI 修复</>
              )}
            </button>
            <button
              onClick={onEdit}
              className="px-4 py-2 bg-slate-50 text-slate-500 rounded-xl text-xs font-bold hover:bg-slate-100 transition-colors"
            >
              人工修改
            </button>
          </>
        )}
      </div>
    </motion.div>
  )
}

/* ===== 详情弹窗 ===== */

function ReviewDetailModal({
  item, onClose, onApprove, onRegenerate, onSaved,
}: {
  item: ReviewItem
  onClose: () => void
  onApprove: (id: number) => void
  onRegenerate: (id: number) => void
  onSaved: () => void
}) {
  const [editContent, setEditContent] = useState(item.content_item?.content ?? '')
  const [editContentCn, setEditContentCn] = useState(item.content_item?.content_cn ?? '')
  const [issues, setIssues] = useState(item.issues)
  const [saving, setSaving] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [regenMsg, setRegenMsg] = useState<{ passed: boolean; message: string } | null>(null)
  const [error, setError] = useState('')

  const handleSave = async () => {
    setSaving(true)
    setError('')
    try {
      await api.post(`/reviews/${item.id}/edit`, {
        content: editContent,
        content_cn: editContentCn || null,
      })
      onSaved()
      onClose()
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleRegen = async () => {
    setRegenerating(true)
    setRegenMsg(null)
    setError('')
    try {
      const res = await api.post<{
        success: boolean; qc_passed: boolean; retry_count: number; message: string
        new_content: string | null; new_content_cn: string | null
        new_issues: Array<{ rule_id: string; field: string; message: string }>
      }>(`/reviews/${item.id}/regenerate`)
      setRegenMsg({ passed: res.qc_passed, message: res.message })
      if (res.new_content !== null) setEditContent(res.new_content)
      if (res.new_content_cn !== null) setEditContentCn(res.new_content_cn)
      setIssues(res.new_issues.map((iss, i) => ({
        id: -(i + 1), content_item_id: item.content_item_id,
        rule_id: iss.rule_id, field: iss.field, message: iss.message, severity: 'error',
      })))
      if (res.qc_passed) {
        setTimeout(() => { onSaved(); onClose() }, 1500)
      } else {
        onSaved()
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : '重新生成失败')
    } finally {
      setRegenerating(false)
    }
  }

  const retryCount = item.content_item?.retry_count ?? 0

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
        className="bg-white rounded-[32px] shadow-2xl border border-slate-100 w-full max-w-lg max-h-[80vh] overflow-hidden flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
          <div className="space-y-1">
            <h3 className="text-2xl font-black text-slate-900">{item.word?.word}</h3>
            <div className="flex items-center gap-3 text-xs">
              <span className="text-slate-400">
                {DIMENSION_LABELS[item.content_item?.dimension ?? ''] ?? item.content_item?.dimension}
              </span>
              <span className="text-slate-300">|</span>
              <span className="text-slate-400">{item.reason}</span>
              {issues.length > 0 && (
                <span className="flex items-center gap-1 px-2 py-0.5 bg-rose-100 text-rose-700 text-[10px] font-bold rounded-lg">
                  <AlertCircle size={11} />
                  {issues.length} 项异常
                </span>
              )}
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-full transition-colors">
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          <div>
            <label className="text-[10px] font-bold text-slate-400 uppercase mb-1.5 block">内容</label>
            <textarea
              value={editContent}
              onChange={e => setEditContent(e.target.value)}
              rows={4}
              disabled={regenerating}
              className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-2xl text-slate-900 placeholder-slate-400 focus:outline-none focus:border-blue-300 transition-all resize-none disabled:opacity-50"
            />
          </div>

          <div>
            <label className="text-[10px] font-bold text-slate-400 uppercase mb-1.5 block">中文翻译</label>
            <textarea
              value={editContentCn}
              onChange={e => setEditContentCn(e.target.value)}
              rows={2}
              disabled={regenerating}
              className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-2xl text-slate-900 placeholder-slate-400 focus:outline-none focus:border-blue-300 transition-all resize-none disabled:opacity-50"
            />
          </div>

          {/* 重新生成状态 */}
          {regenerating && (
            <div className="flex items-center justify-center gap-2 text-blue-600 bg-blue-50 border border-blue-200 rounded-2xl px-4 py-3">
              <Loader2 size={16} className="animate-spin" />
              <span className="text-sm font-medium">正在重新生成并质检...</span>
            </div>
          )}

          {regenMsg && (
            <div className={`text-sm px-4 py-3 rounded-2xl text-center font-medium ${
              regenMsg.passed ? 'bg-green-50 text-green-600 border border-green-200' : 'bg-orange-50 text-orange-600 border border-orange-200'
            }`}>
              {regenMsg.message}
            </div>
          )}

          {/* 质检问题 */}
          {issues.length > 0 && !regenerating && (
            <div>
              <label className="text-[10px] font-bold text-slate-400 uppercase mb-2 block">质检问题</label>
              <div className="space-y-1">
                {issues.map((issue, i) => (
                  <div key={i} className="text-sm bg-red-50 text-red-600 border border-red-100 px-3 py-2 rounded-xl">
                    <span className="font-mono text-xs text-red-500 mr-2">[{issue.rule_id}]</span>
                    {issue.message}
                  </div>
                ))}
              </div>
            </div>
          )}

          {error && <p className="text-red-600 text-sm bg-red-50 border border-red-200 rounded-xl py-2 text-center">{error}</p>}
        </div>

        {/* Footer */}
        <div className="p-5 border-t border-slate-100 flex items-center gap-3 bg-slate-50/50">
          <button
            onClick={() => onApprove(item.id)}
            disabled={regenerating}
            className="flex-1 py-2.5 bg-green-50 hover:bg-green-100 text-green-700 border border-green-200 rounded-2xl transition-all text-sm font-bold disabled:opacity-50"
          >
            通过
          </button>
          {retryCount < 3 && (
            <button
              onClick={handleRegen}
              disabled={regenerating || saving}
              className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-2xl transition-all text-sm font-bold flex items-center justify-center gap-1.5 disabled:opacity-50 shadow-sm shadow-blue-200"
            >
              {regenerating ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
              {regenerating ? '重新生成中...' : `AI 修复 (${retryCount}/3)`}
            </button>
          )}
          <button
            onClick={handleSave}
            disabled={saving || regenerating}
            className="flex-1 py-2.5 bg-yellow-50 hover:bg-yellow-100 text-yellow-700 border border-yellow-200 rounded-2xl transition-all text-sm font-bold flex items-center justify-center gap-1.5 disabled:opacity-50"
          >
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
            保存修改
          </button>
        </div>
      </motion.div>
    </motion.div>
  )
}
