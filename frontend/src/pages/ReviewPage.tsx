import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { AnimatePresence } from 'motion/react'
import {
  Search, RefreshCw, CheckCircle2, Loader2, X, PackagePlus,
  ArrowLeft, Filter, ChevronDown,
} from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { useToast } from '../components/Toast'
import type { ReviewItem, ReviewBatch, BatchDetail } from '../types'
import { usePolling } from '../hooks/usePolling'
import type { Tab } from './review/types'
import { FILTER_GROUPS } from './review/constants'
import { groupByWord } from './review/utils'
import { WordGroupCard } from './review/WordGroupCard'
import { WordReviewModal } from './review/WordReviewModal'

interface Props {
  onBack: () => void
}

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

  // 释放批次
  const [releaseLoading, setReleaseLoading] = useState(false)

  // 提示
  const [noBatchMsg, setNoBatchMsg] = useState('')

  // 一键AI修复
  const [batchFixing, setBatchFixing] = useState(false)

  // 已通过动画
  const [resolvedIds, setResolvedIds] = useState<Set<number>>(new Set())
  const { showToast } = useToast()

  // setTimeout 清理
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([])
  useEffect(() => {
    return () => { timersRef.current.forEach(clearTimeout) }
  }, [])
  const safeTimeout = useCallback((fn: () => void, ms: number) => {
    const id = setTimeout(() => {
      timersRef.current = timersRef.current.filter(t => t !== id)
      fn()
    }, ms)
    timersRef.current.push(id)
    return id
  }, [])

  const loadBatch = useCallback(async () => {
    setBatchLoading(true)
    try {
      const data = await api.get<ReviewBatch | null>('/batches/current')
      setBatch(data)
    } catch (e) {
      showToast('error', '加载批次信息失败')
      setBatch(null)
    } finally {
      setBatchLoading(false)
    }
  }, [])

  const loadItems = useCallback(async () => {
    // 没有批次时不加载审核项
    if (!batch) {
      setItems([])
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const detail = await api.get<BatchDetail>(`/batches/${batch.id}/words`)
      const res = await api.get<{ items: ReviewItem[]; total: number }>('/reviews?limit=200')
      const allReviews = res.items ?? []
      const batchReviewIds = new Set(
        detail.words.flatMap(w => w.items.map(i => i.review_id))
      )
      setItems(allReviews.filter(r => batchReviewIds.has(r.id)))
    } catch (e) {
      showToast('error', '加载审核列表失败')
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [batch])

  useEffect(() => { loadBatch() }, [loadBatch])
  useEffect(() => { if (!batchLoading) loadItems() }, [batchLoading, loadItems])

  // 静默轮询刷新：操作进行中时跳过，防止覆盖乐观更新
  const silentRefresh = useCallback(async () => {
    if (actionLoading !== null || batchFixing) return
    try {
      const data = await api.get<ReviewBatch | null>('/batches/current')
      setBatch(data)
      if (!data) { setItems([]); return }
      const detail = await api.get<BatchDetail>(`/batches/${data.id}/words`)
      const res = await api.get<{ items: ReviewItem[]; total: number }>('/reviews?limit=200')
      const batchReviewIds = new Set(detail.words.flatMap(w => w.items.map(i => i.review_id)))
      setItems((res.items ?? []).filter(r => batchReviewIds.has(r.id)))
    } catch { /* 静默失败 */ }
  }, [actionLoading, batchFixing])

  usePolling(silentRefresh, 10_000, !batchLoading && !loading && actionLoading === null && !batchFixing)

  const handleAssign = async () => {
    setAssignLoading(true)
    try {
      const data = await api.post<ReviewBatch | null>('/batches/assign')
      if (data) {
        await loadBatch()
      } else {
        setBatch(null)
      }
    } catch (e) {
      showToast('error', e instanceof ApiError ? e.detail : '领取批次失败')
    } finally {
      setAssignLoading(false)
    }
  }

  const handleReleaseBatch = async () => {
    if (!batch) return
    setReleaseLoading(true)
    try {
      await api.post(`/batches/${batch.id}/release`)
      setBatch(null)
      setItems([])
    } catch (e) {
      showToast('error', e instanceof ApiError ? e.detail : '释放批次失败')
    } finally {
      setReleaseLoading(false)
    }
  }

  const handleApprove = async (id: number) => {
    if (actionLoading !== null) return
    setActionLoading(id)
    try {
      await api.post(`/reviews/${id}/approve`)
      // 先标记为 resolved 播放动画，延迟后移除
      setResolvedIds(prev => new Set(prev).add(id))
      setActionLoading(null)
      loadBatch()
      safeTimeout(() => {
        setItems(prev => prev.filter(i => i.id !== id))
        setResolvedIds(prev => { const next = new Set(prev); next.delete(id); return next })
      }, 1200)
    } catch (e) {
      showToast('error', e instanceof ApiError ? e.detail : '审核通过失败')
      setActionLoading(null)
    }
  }

  const handleRegenerate = async (id: number) => {
    // F-H2: 防止重复提交 — actionLoading 非 null 时拒绝新请求
    if (actionLoading !== null) return
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
        loadBatch()
        safeTimeout(() => {
          setItems(prev => prev.filter(i => i.id !== id))
          setResolvedIds(prev => { const next = new Set(prev); next.delete(id); return next })
          setRegenResult(null)
        }, 1500)
      } else {
        // 就地更新 items：用响应中的 new_issues + new_content 替换旧数据，避免额外 API 调用的时序问题
        setItems(prev => prev.map(item =>
          item.id === id
            ? {
                ...item,
                content_item: item.content_item ? {
                  ...item.content_item,
                  content: res.new_content ?? item.content_item.content,
                  content_cn: res.new_content_cn ?? item.content_item.content_cn,
                  retry_count: res.retry_count,
                } : item.content_item,
                issues: res.new_issues.map((iss, idx) => ({
                  id: -(idx + 1),
                  content_item_id: item.content_item_id,
                  rule_id: iss.rule_id,
                  field: iss.field,
                  message: iss.message,
                  severity: 'error',
                })),
              }
            : item
        ))
        setRegenResult({ id, passed: false, message: res.message })
        safeTimeout(() => setRegenResult(null), 3000)
      }
    } catch (e) { showToast('error', e instanceof ApiError ? e.detail : '重新生成失败') }
    finally { setActionLoading(null) }
  }

  // 过滤
  const filtered = useMemo(() => items.filter(item => {
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
  }), [items, search, tab, filterDim])

  const wordGroups = useMemo(() => groupByWord(filtered), [filtered])

  // 从实时数据派生当前选中的 group（而非快照）
  const allWordGroups = useMemo(() => groupByWord(items), [items])
  const selectedWordGroup = selectedWordId !== null
    ? allWordGroups.find(g => g.word_id === selectedWordId) ?? null
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
              <button
                onClick={handleReleaseBatch}
                disabled={releaseLoading}
                className="text-slate-300 hover:text-red-500 ml-1 transition-colors"
                title="释放批次"
              >
                {releaseLoading ? <Loader2 size={12} className="animate-spin" /> : <X size={12} />}
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

              // 静默版 regenerate：不设 actionLoading 锁，不弹 toast，支持并发
              const handleRegenerateSilent = async (id: number) => {
                const res = await api.post<{
                  success: boolean; qc_passed: boolean; retry_count: number; message: string
                  new_content: string | null; new_content_cn: string | null
                  new_issues: Array<{ rule_id: string; field: string; message: string }>
                }>(`/reviews/${id}/regenerate`)
                if (res.qc_passed) {
                  setResolvedIds(prev => new Set(prev).add(id))
                  safeTimeout(() => {
                    setItems(prev => prev.filter(i => i.id !== id))
                    setResolvedIds(prev => { const next = new Set(prev); next.delete(id); return next })
                  }, 1500)
                } else {
                  setItems(prev => prev.map(item =>
                    item.id === id
                      ? {
                          ...item,
                          content_item: item.content_item ? {
                            ...item.content_item,
                            content: res.new_content ?? item.content_item.content,
                            content_cn: res.new_content_cn ?? item.content_item.content_cn,
                            retry_count: res.retry_count,
                          } : item.content_item,
                          issues: res.new_issues.map((iss, idx) => ({
                            id: -(idx + 1),
                            content_item_id: item.content_item_id,
                            rule_id: iss.rule_id,
                            field: iss.field,
                            message: iss.message,
                            severity: 'error',
                          })),
                        }
                      : item
                  ))
                }
              }

              // 分批并发，每批 5 个，防止一次性打过多请求
              const BATCH_SIZE = 5
              let succeeded = 0
              let failed = 0
              for (let i = 0; i < canRetryItems.length; i += BATCH_SIZE) {
                const batch = canRetryItems.slice(i, i + BATCH_SIZE)
                const results = await Promise.allSettled(
                  batch.map(item => handleRegenerateSilent(item.id))
                )
                succeeded += results.filter(r => r.status === 'fulfilled').length
                failed += results.filter(r => r.status === 'rejected').length
              }

              loadBatch()
              if (failed > 0) {
                showToast('warning', `AI修复完成: ${succeeded} 成功, ${failed} 失败`)
              } else if (succeeded > 0) {
                showToast('success', `AI修复完成: ${succeeded} 项已处理`)
              }
              setBatchFixing(false)
            }}
            disabled={!batch || counts.can_retry === 0 || actionLoading !== null || batchFixing}
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
      ) : !batch ? (
        <div className="text-center py-20 space-y-4">
          <div className="w-20 h-20 bg-blue-50 text-blue-500 rounded-full flex items-center justify-center mx-auto">
            <PackagePlus size={40} />
          </div>
          <h3 className="text-2xl font-bold text-white">请先领取批次</h3>
          <p className="text-white/60">领取一批待审核的单词后即可开始审核</p>
          <button
            onClick={handleAssign}
            disabled={assignLoading}
            className="px-6 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-bold hover:bg-blue-700 transition-all disabled:opacity-50 shadow-lg shadow-blue-600/20"
          >
            {assignLoading ? <Loader2 size={14} className="animate-spin inline mr-1.5" /> : <PackagePlus size={14} className="inline mr-1.5" />}
            领取批次
          </button>
          {noBatchMsg && (
            <p className="text-sm text-yellow-200 mt-2">{noBatchMsg}</p>
          )}
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
          {filterDim ? (
            <button onClick={() => setFilterDim('')} className="px-4 py-2 bg-white/20 text-white rounded-xl text-sm font-medium hover:bg-white/30 transition-all">
              清除筛选
            </button>
          ) : (
            <button
              onClick={async () => {
                setAssignLoading(true)
                setNoBatchMsg('')
                try {
                  // 释放当前批次（可能已自动完成，忽略错误），不提前清空 batch 避免 UI 闪跳
                  if (batch) {
                    try { await api.post(`/batches/${batch.id}/release`) } catch {}
                  }
                  const data = await api.post<ReviewBatch | null>('/batches/assign')
                  if (!data) {
                    setBatch(null)
                    setNoBatchMsg('暂无新的待审核批次')
                    safeTimeout(() => setNoBatchMsg(''), 3000)
                  } else {
                    await loadBatch()
                  }
                } catch (e) {
                  showToast('error', e instanceof ApiError ? e.detail : '领取批次失败')
                } finally {
                  setAssignLoading(false)
                }
              }}
              disabled={assignLoading}
              className="px-6 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-bold hover:bg-blue-700 transition-all disabled:opacity-50 shadow-lg shadow-blue-600/20"
            >
              {assignLoading ? <Loader2 size={14} className="animate-spin inline mr-1.5" /> : <PackagePlus size={14} className="inline mr-1.5" />}
              领取下一批次
            </button>
          )}
          {noBatchMsg && (
            <p className="text-sm text-yellow-200 mt-2">{noBatchMsg}</p>
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
