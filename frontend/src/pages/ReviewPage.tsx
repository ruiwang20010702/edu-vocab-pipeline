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
    } catch {
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
        const allReviews = await api.get<ReviewItem[]>('/reviews')
        const reviewMap = new Map(allReviews.map(r => [r.id, r]))

        // 从批次词汇中提取 review_id，匹配完整 ReviewItem
        const batchReviewIds = new Set(
          detail.words.flatMap(w => w.items.map(i => i.review_id))
        )
        setItems(allReviews.filter(r => batchReviewIds.has(r.id)))
      } else {
        // 无批次时加载全部待审
        const data = await api.get<ReviewItem[]>('/reviews')
        setItems(data)
      }
    } catch {
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
    } catch {
      // ignore
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
    } catch { /* ignore */ }
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
    } catch { /* ignore */ }
    finally { setActionLoading(null) }
  }

  const handleRegenerate = async (id: number) => {
    setActionLoading(id)
    try {
      await api.post(`/reviews/${id}/regenerate`)
      await loadItems()
    } catch { /* ignore */ }
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
      <div className="glass-card rounded-2xl p-4">
        {batchLoading ? (
          <div className="flex items-center gap-2 text-white/50">
            <Loader2 size={16} className="animate-spin" />
            <span className="text-sm">加载批次信息...</span>
          </div>
        ) : batch ? (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <PackagePlus size={18} className="text-blue-300" />
                <span className="text-white font-medium">当前批次 #{batch.id}</span>
              </div>
              <div className="flex items-center gap-3 text-sm">
                <span className="text-white/60">
                  进度: <span className="text-white">{batch.reviewed_count}/{batch.word_count}</span>
                </span>
                <span className={`px-2 py-0.5 rounded-lg text-xs ${
                  batch.status === 'completed' ? 'bg-green-400/20 text-green-200' : 'bg-blue-400/20 text-blue-200'
                }`}>
                  {batch.status === 'completed' ? '已完成' : '进行中'}
                </span>
              </div>
            </div>
            <button
              onClick={() => { setBatch(null); loadItems() }}
              className="text-sm text-white/40 hover:text-white/70 transition-colors"
            >
              查看全部待审
            </button>
          </div>
        ) : (
          <div className="flex items-center justify-between">
            <span className="text-white/50 text-sm">暂无进行中的批次</span>
            <button
              onClick={handleAssign}
              disabled={assignLoading}
              className="flex items-center gap-2 px-4 py-2 bg-blue-500/20 hover:bg-blue-500/30 text-blue-200 rounded-xl transition-all text-sm font-medium disabled:opacity-50"
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
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-white/40" size={18} />
          <input
            type="text"
            placeholder="搜索单词..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full pl-11 pr-4 py-3 glass-module rounded-2xl text-white placeholder-white/40 focus:outline-none focus:border-white/50 transition-all"
          />
        </div>
        <button onClick={loadItems} className="p-3 glass-module rounded-2xl text-white/60 hover:text-white transition-colors">
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
              tab === t.key ? 'bg-white/25 text-white' : 'text-white/50 hover:text-white/80 hover:bg-white/10'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 列表 */}
      {loading ? (
        <div className="flex items-center justify-center h-40">
          <Loader2 size={24} className="animate-spin text-white/50" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="glass-card rounded-3xl p-10 text-center text-white/50">
          {items.length === 0 ? '暂无待审核项目' : '没有匹配结果'}
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map(item => (
            <motion.div
              key={item.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass-card rounded-2xl p-4 cursor-pointer hover:bg-white/20 transition-all"
              onClick={() => setSelectedItem(item)}
            >
              <div className="flex items-center justify-between">
                <div>
                  <span className="font-bold text-white text-lg">{item.word?.word}</span>
                  <span className="ml-3 text-sm text-white/50">{item.content_item?.dimension}</span>
                  <span className="ml-2 text-xs text-white/40">重试 {item.content_item?.retry_count ?? 0}/3</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-1 rounded-lg text-xs ${
                    item.reason === 'layer1_failed' ? 'bg-red-400/20 text-red-200'
                    : item.reason === 'layer2_failed' ? 'bg-orange-400/20 text-orange-200'
                    : 'bg-blue-400/20 text-blue-200'
                  }`}>
                    {item.reason}
                  </span>
                  {actionLoading === item.id ? (
                    <Loader2 size={16} className="animate-spin text-white/50" />
                  ) : (
                    <>
                      <button
                        onClick={e => { e.stopPropagation(); handleApprove(item.id) }}
                        className="p-2 rounded-xl hover:bg-green-400/20 text-green-300 transition-colors"
                        title="通过"
                      >
                        <CheckCircle2 size={16} />
                      </button>
                      {item.content_item?.retry_count < 3 && (
                        <button
                          onClick={e => { e.stopPropagation(); handleRegenerate(item.id) }}
                          className="p-2 rounded-xl hover:bg-blue-400/20 text-blue-300 transition-colors"
                          title="重新生成"
                        >
                          <RefreshCw size={16} />
                        </button>
                      )}
                      <button
                        onClick={e => { e.stopPropagation(); setSelectedItem(item) }}
                        className="p-2 rounded-xl hover:bg-yellow-400/20 text-yellow-300 transition-colors"
                        title="手动编辑"
                      >
                        <Edit3 size={16} />
                      </button>
                      {batch && (
                        <button
                          onClick={e => { e.stopPropagation(); handleSkipWord(item.word_id) }}
                          className="p-2 rounded-xl hover:bg-white/10 text-white/40 transition-colors"
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
                    <span key={i} className="text-xs bg-white/10 text-white/60 px-2 py-0.5 rounded-lg">{issue.message}</span>
                  ))}
                  {item.issues.length > 3 && (
                    <span className="text-xs text-white/40">+{item.issues.length - 3}</span>
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
        className="glass-card rounded-3xl p-6 w-full max-w-lg max-h-[80vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xl font-bold text-white">{item.word?.word}</h3>
          <button onClick={onClose} className="text-white/40 hover:text-white/80">
            <X size={20} />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="text-sm text-white/60 mb-1 block">维度: {item.content_item?.dimension}</label>
            <label className="text-sm text-white/60 mb-1 block">原因: {item.reason}</label>
          </div>

          <div>
            <label className="text-sm text-white/60 mb-1 block">内容</label>
            <textarea
              value={editContent}
              onChange={e => setEditContent(e.target.value)}
              rows={4}
              className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-2xl text-white placeholder-white/40 focus:outline-none focus:border-white/50 transition-all resize-none"
            />
          </div>

          <div>
            <label className="text-sm text-white/60 mb-1 block">中文翻译</label>
            <textarea
              value={editContentCn}
              onChange={e => setEditContentCn(e.target.value)}
              rows={2}
              className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-2xl text-white placeholder-white/40 focus:outline-none focus:border-white/50 transition-all resize-none"
            />
          </div>

          {/* 问题列表 */}
          {item.issues.length > 0 && (
            <div>
              <label className="text-sm text-white/60 mb-2 block">质检问题</label>
              <div className="space-y-1">
                {item.issues.map((issue, i) => (
                  <div key={i} className="text-sm bg-red-400/10 text-red-200 px-3 py-2 rounded-xl">
                    <span className="font-mono text-xs text-red-300 mr-2">[{issue.rule_id}]</span>
                    {issue.message}
                  </div>
                ))}
              </div>
            </div>
          )}

          {error && <p className="text-red-200 text-sm bg-red-500/20 rounded-xl py-2 text-center">{error}</p>}

          <div className="flex gap-3">
            <button
              onClick={() => onApprove(item.id)}
              className="flex-1 py-2.5 bg-green-500/20 hover:bg-green-500/30 text-green-200 rounded-2xl transition-all text-sm font-medium"
            >
              通过
            </button>
            {item.content_item?.retry_count < 3 && (
              <button
                onClick={() => onRegenerate(item.id)}
                className="flex-1 py-2.5 bg-blue-500/20 hover:bg-blue-500/30 text-blue-200 rounded-2xl transition-all text-sm font-medium"
              >
                重新生成 ({item.content_item?.retry_count ?? 0}/3)
              </button>
            )}
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex-1 py-2.5 bg-yellow-500/20 hover:bg-yellow-500/30 text-yellow-200 rounded-2xl transition-all text-sm font-medium flex items-center justify-center gap-1 disabled:opacity-50"
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
