import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { Search, RefreshCw, Edit3, CheckCircle2, Loader2, X, SkipForward, PackagePlus } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import type { ReviewItem, ReviewBatch, BatchDetail } from '../types'

interface Props {
  onBack: () => void
}

type Tab = 'all' | 'can_retry' | 'must_manual'

export default function ReviewPage({ onBack: _onBack }: Props) {
  const [items, setItems] = useState<ReviewItem[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [tab, setTab] = useState<Tab>('all')
  const [selectedItem, setSelectedItem] = useState<ReviewItem | null>(null)
  const [actionLoading, setActionLoading] = useState<number | null>(null)

  // 批次状态
  const [batch, setBatch] = useState<ReviewBatch | null>(null)
  const [batchLoading, setBatchLoading] = useState(true)
  const [assignLoading, setAssignLoading] = useState(false)

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
        // 有批次时从批次加载
        const detail = await api.get<BatchDetail>(`/batches/${batch.id}/words`)
        // 同时加载完整审核列表以获取嵌套对象
        const res = await api.get<{ items: ReviewItem[]; total: number }>('/reviews?limit=200')
        const allReviews = res.items ?? []

        // 从批次词汇中提取 review_id，匹配完整 ReviewItem
        const batchReviewIds = new Set(
          detail.words.flatMap(w => w.items.map(i => i.review_id))
        )
        setItems(allReviews.filter(r => batchReviewIds.has(r.id)))
      } else {
        // 无批次时加载全部待审
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

  const handleSkipWord = async (wordId: number) => {
    if (!batch) return
    setActionLoading(wordId)
    try {
      await api.post(`/batches/${batch.id}/words/${wordId}/skip`)
      setItems(prev => prev.filter(i => i.word_id !== wordId))
    } catch (e) { console.error('跳过单词失败', e) }
    finally { setActionLoading(null) }
  }

  const filtered = items.filter(item => {
    if (search && !item.word?.word.toLowerCase().includes(search.toLowerCase())) return false
    if (tab === 'can_retry' && item.content_item?.retry_count >= 3) return false
    if (tab === 'must_manual' && item.content_item?.retry_count < 3) return false
    return true
  })

  const handleApprove = async (id: number) => {
    setActionLoading(id)
    try {
      await api.post(`/reviews/${id}/approve`)
      setItems(prev => prev.filter(i => i.id !== id))
      if (selectedItem?.id === id) setSelectedItem(null)
    } catch (e) { console.error('审核通过失败', e) }
    finally { setActionLoading(null) }
  }

  const [regenResult, setRegenResult] = useState<{ id: number; passed: boolean; message: string } | null>(null)

  const handleRegenerate = async (id: number) => {
    setActionLoading(id)
    setRegenResult(null)
    try {
      const res = await api.post<{ success: boolean; qc_passed: boolean; retry_count: number; message: string }>(`/reviews/${id}/regenerate`)
      if (res.qc_passed) {
        // 质检通过 → 显示成功提示，移除项
        setRegenResult({ id, passed: true, message: res.message })
        setTimeout(() => {
          setItems(prev => prev.filter(i => i.id !== id))
          if (selectedItem?.id === id) setSelectedItem(null)
          setRegenResult(null)
        }, 1500)
      } else {
        // 质检失败 → 显示失败提示，刷新列表显示新内容
        setRegenResult({ id, passed: false, message: res.message })
        await loadItems()
        setTimeout(() => setRegenResult(null), 3000)
      }
    } catch (e) { console.error('重新生成失败', e) }
    finally { setActionLoading(null) }
  }

  const tabs: { key: Tab; label: string }[] = [
    { key: 'all', label: `全部 (${items.length})` },
    { key: 'can_retry', label: `可重试 (${items.filter(i => i.content_item?.retry_count < 3).length})` },
    { key: 'must_manual', label: `需手动 (${items.filter(i => i.content_item?.retry_count >= 3).length})` },
  ]

  return (
    <div className="space-y-4">
      {/* 批次面板 */}
      <div className="bg-white rounded-2xl border border-white shadow-sm p-4">
        {batchLoading ? (
          <div className="flex items-center gap-2 text-blue-600">
            <Loader2 size={16} className="animate-spin" />
            <span className="text-sm">加载批次信息...</span>
          </div>
        ) : batch ? (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <PackagePlus size={18} className="text-blue-600" />
                <span className="text-slate-900 font-medium">当前批次 #{batch.id}</span>
              </div>
              <div className="flex items-center gap-3 text-sm">
                <span className="text-slate-500">
                  进度: <span className="text-slate-900">{batch.reviewed_count}/{batch.word_count}</span>
                </span>
                <span className={`px-2 py-0.5 rounded-lg text-xs ${
                  batch.status === 'completed' ? 'bg-green-50 text-green-600' : 'bg-blue-50 text-blue-600'
                }`}>
                  {batch.status === 'completed' ? '已完成' : '进行中'}
                </span>
              </div>
            </div>
            <button
              onClick={() => { setBatch(null); loadItems() }}
              className="text-sm text-slate-300 hover:text-slate-500 transition-colors"
            >
              查看全部待审
            </button>
          </div>
        ) : (
          <div className="flex items-center justify-between">
            <span className="text-slate-400 text-sm">暂无进行中的批次</span>
            <button
              onClick={handleAssign}
              disabled={assignLoading}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl transition-all text-sm font-medium disabled:opacity-50"
            >
              {assignLoading ? <Loader2 size={14} className="animate-spin" /> : <PackagePlus size={14} />}
              领取批次
            </button>
          </div>
        )}
      </div>

      {/* 搜索 + 过滤 */}
      <div className="flex items-center gap-3">
        <div className="flex-1 relative">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-300" size={18} />
          <input
            type="text"
            placeholder="搜索单词..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full pl-11 pr-4 py-3 bg-white border border-slate-200 rounded-2xl text-slate-900 placeholder-slate-400 focus:outline-none focus:border-slate-300 transition-all"
          />
        </div>
        <button onClick={loadItems} className="p-3 bg-white border border-slate-200 rounded-2xl text-slate-500 hover:text-slate-900 transition-colors">
          <RefreshCw size={18} />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-2">
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 rounded-xl text-sm font-medium transition-all ${
              tab === t.key ? 'bg-blue-600 text-white' : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 列表 */}
      {loading ? (
        <div className="flex items-center justify-center h-40">
          <Loader2 size={24} className="animate-spin text-blue-600" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="bg-white rounded-[32px] border border-white shadow-sm p-10 text-center text-slate-400">
          {items.length === 0 ? '暂无待审核项目' : '没有匹配结果'}
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map(item => (
            <motion.div
              key={item.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="bg-white rounded-2xl border border-white shadow-sm p-4 cursor-pointer hover:bg-blue-50 transition-all"
              onClick={() => setSelectedItem(item)}
            >
              <div className="flex items-center justify-between">
                <div>
                  <span className="font-bold text-slate-900 text-lg">{item.word?.word}</span>
                  <span className="ml-3 text-sm text-slate-400">{item.content_item?.dimension}</span>
                  <span className="ml-2 text-xs text-slate-300">重试 {item.content_item?.retry_count ?? 0}/3</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-1 rounded-lg text-xs ${
                    item.reason === 'layer1_failed' ? 'bg-red-50 text-red-600'
                    : item.reason === 'layer2_failed' ? 'bg-orange-50 text-orange-600'
                    : 'bg-blue-50 text-blue-600'
                  }`}>
                    {item.reason}
                  </span>
                  {regenResult?.id === item.id && (
                    <span className={`text-xs px-2 py-1 rounded-lg ${
                      regenResult.passed ? 'bg-green-50 text-green-600' : 'bg-orange-50 text-orange-600'
                    }`}>
                      {regenResult.message}
                    </span>
                  )}
                  {actionLoading === item.id ? (
                    <Loader2 size={16} className="animate-spin text-blue-600" />
                  ) : (
                    <>
                      <button
                        onClick={e => { e.stopPropagation(); handleApprove(item.id) }}
                        className="p-2 rounded-xl hover:bg-green-50 text-green-600 transition-colors"
                        title="通过"
                      >
                        <CheckCircle2 size={16} />
                      </button>
                      {item.content_item?.retry_count < 3 && (
                        <button
                          onClick={e => { e.stopPropagation(); handleRegenerate(item.id) }}
                          className="p-2 rounded-xl hover:bg-blue-50 text-blue-600 transition-colors"
                          title="重新生成"
                        >
                          <RefreshCw size={16} />
                        </button>
                      )}
                      <button
                        onClick={e => { e.stopPropagation(); setSelectedItem(item) }}
                        className="p-2 rounded-xl hover:bg-yellow-50 text-yellow-600 transition-colors"
                        title="手动编辑"
                      >
                        <Edit3 size={16} />
                      </button>
                      {batch && (
                        <button
                          onClick={e => { e.stopPropagation(); handleSkipWord(item.word_id) }}
                          className="p-2 rounded-xl hover:bg-slate-50 text-slate-300 transition-colors"
                          title="跳过此词"
                        >
                          <SkipForward size={16} />
                        </button>
                      )}
                    </>
                  )}
                </div>
              </div>
              {item.issues.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {item.issues.slice(0, 3).map((issue, i) => (
                    <span key={i} className="text-xs bg-slate-100 text-slate-500 px-2 py-0.5 rounded-lg">{issue.message}</span>
                  ))}
                  {item.issues.length > 3 && (
                    <span className="text-xs text-slate-300">+{item.issues.length - 3}</span>
                  )}
                </div>
              )}
            </motion.div>
          ))}
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
  const [saving, setSaving] = useState(false)
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
        className="bg-white rounded-[32px] p-6 shadow-2xl border border-slate-100 w-full max-w-lg max-h-[80vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xl font-bold text-slate-900">{item.word?.word}</h3>
          <button onClick={onClose} className="text-slate-300 hover:text-slate-600">
            <X size={20} />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="text-sm text-slate-500 mb-1 block">维度: {item.content_item?.dimension}</label>
            <label className="text-sm text-slate-500 mb-1 block">原因: {item.reason}</label>
          </div>

          <div>
            <label className="text-sm text-slate-500 mb-1 block">内容</label>
            <textarea
              value={editContent}
              onChange={e => setEditContent(e.target.value)}
              rows={4}
              className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-2xl text-slate-900 placeholder-slate-400 focus:outline-none focus:border-slate-300 transition-all resize-none"
            />
          </div>

          <div>
            <label className="text-sm text-slate-500 mb-1 block">中文翻译</label>
            <textarea
              value={editContentCn}
              onChange={e => setEditContentCn(e.target.value)}
              rows={2}
              className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-2xl text-slate-900 placeholder-slate-400 focus:outline-none focus:border-slate-300 transition-all resize-none"
            />
          </div>

          {/* 问题列表 */}
          {item.issues.length > 0 && (
            <div>
              <label className="text-sm text-slate-500 mb-2 block">质检问题</label>
              <div className="space-y-1">
                {item.issues.map((issue, i) => (
                  <div key={i} className="text-sm bg-red-50 text-red-600 border border-red-100 px-3 py-2 rounded-xl">
                    <span className="font-mono text-xs text-red-500 mr-2">[{issue.rule_id}]</span>
                    {issue.message}
                  </div>
                ))}
              </div>
            </div>
          )}

          {error && <p className="text-red-600 text-sm bg-red-50 border border-red-200 rounded-xl py-2 text-center">{error}</p>}

          <div className="flex gap-3">
            <button
              onClick={() => onApprove(item.id)}
              className="flex-1 py-2.5 bg-green-50 hover:bg-green-100 text-green-700 border border-green-200 rounded-2xl transition-all text-sm font-medium"
            >
              通过
            </button>
            {item.content_item?.retry_count < 3 && (
              <button
                onClick={() => onRegenerate(item.id)}
                className="flex-1 py-2.5 bg-blue-50 hover:bg-blue-100 text-blue-700 border border-blue-200 rounded-2xl transition-all text-sm font-medium"
              >
                重新生成 ({item.content_item?.retry_count ?? 0}/3)
              </button>
            )}
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex-1 py-2.5 bg-yellow-50 hover:bg-yellow-100 text-yellow-700 border border-yellow-200 rounded-2xl transition-all text-sm font-medium flex items-center justify-center gap-1 disabled:opacity-50"
            >
              {saving && <Loader2 size={14} className="animate-spin" />}
              保存修改
            </button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  )
}
