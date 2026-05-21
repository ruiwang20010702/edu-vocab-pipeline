import { useState, useEffect, useCallback } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Package as PackageIcon, ChevronDown, ChevronRight, Loader2, RefreshCw, Hash, Calendar, CheckCircle2, Clock, AlertCircle, FileText, Wand2, X, AlertTriangle } from 'lucide-react'
import { api, ApiError } from '../../lib/api'
import { useToast } from '../../components/Toast'
import type { BatchInfo } from '../../types'
import PackageRegenModal from './PackageRegenModal'

// Tailwind v4 JIT 只扫字面量类名，禁止用字符串拼接构造 bg-${x}-50
const STATUS_MAP: Record<string, {
  label: string
  badgeCls: string
  iconCls: string
  icon: typeof CheckCircle2
}> = {
  completed: { label: '已完成', badgeCls: 'bg-emerald-50 text-emerald-700', iconCls: '', icon: CheckCircle2 },
  processing: { label: '生产中', badgeCls: 'bg-blue-50 text-blue-700', iconCls: 'animate-spin', icon: Loader2 },
  pending: { label: '待处理', badgeCls: 'bg-slate-50 text-slate-700', iconCls: '', icon: Clock },
  failed: { label: '失败', badgeCls: 'bg-rose-50 text-rose-700', iconCls: '', icon: AlertCircle },
}

function formatDate(dateStr: string) {
  const d = new Date(dateStr)
  return d.toLocaleDateString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

interface BackfillPreview {
  packages: { package_id: number; name: string; status: string; missing: number }[]
  total_missing: number   // 按包累加（含跨包重复）
  unique_missing: number  // 去重后真实缺失项数
}

export default function PackagePanel() {
  const { showToast } = useToast()
  const [expanded, setExpanded] = useState(false)
  const [batches, setBatches] = useState<BatchInfo[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [activeBatch, setActiveBatch] = useState<BatchInfo | null>(null)

  const fetchBatches = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.get<BatchInfo[]>('/batches')
      setBatches(data)
    } catch (e) {
      showToast('error', e instanceof ApiError ? e.detail : '加载词包列表失败')
    } finally {
      setLoading(false)
    }
  }, [showToast])

  // 稳定 onClose 引用，避免 PackageRegenModal 内部 keydown listener 每帧重挂载
  const closeModal = useCallback(() => setActiveBatch(null), [])

  // 一键补全缺失字段
  const [backfillOpen, setBackfillOpen] = useState(false)
  const [backfillPreview, setBackfillPreview] = useState<BackfillPreview | null>(null)
  const [backfillLoading, setBackfillLoading] = useState(false)
  const [backfillSubmitting, setBackfillSubmitting] = useState(false)

  const openBackfill = async () => {
    setBackfillOpen(true)
    setBackfillLoading(true)
    setBackfillPreview(null)
    try {
      const data = await api.get<BackfillPreview>('/batches/backfill-missing-fields/preview')
      setBackfillPreview(data)
    } catch (e) {
      showToast('error', e instanceof ApiError ? e.detail : '预览失败')
      setBackfillOpen(false)
    } finally {
      setBackfillLoading(false)
    }
  }

  const confirmBackfill = async () => {
    setBackfillSubmitting(true)
    try {
      const r = await api.post<{ scheduled: boolean; packages: number; total_missing: number; unique_missing: number }>(
        '/batches/backfill-missing-fields', {},
      )
      if (r.scheduled) {
        showToast('success', `已开始后台补全 ${r.packages} 个词包（去重后约 ${r.unique_missing} 条），可在列表看各包状态`)
      } else {
        showToast('warning', '没有需要补全的缺失字段项')
      }
      setBackfillOpen(false)
      void fetchBatches()
    } catch (e) {
      showToast('error', e instanceof ApiError ? e.detail : '触发失败')
    } finally {
      setBackfillSubmitting(false)
    }
  }

  // 首次展开时懒加载
  useEffect(() => {
    if (expanded && batches === null) void fetchBatches()
  }, [expanded, batches, fetchBatches])

  const count = batches?.length

  return (
    <section className="bg-white rounded-[24px] border border-slate-200 overflow-hidden">
      <button
        onClick={() => setExpanded(v => !v)}
        aria-expanded={expanded}
        aria-controls="package-panel-body"
        className="w-full flex items-center justify-between px-5 py-3 hover:bg-slate-50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-blue-50 text-blue-600 rounded-xl flex items-center justify-center">
            <PackageIcon size={18} />
          </div>
          <div className="text-left">
            <h3 className="font-bold text-sm text-slate-900">
              词包总览{count !== undefined ? `（${count} 个）` : ''}
            </h3>
            <p className="text-[11px] text-slate-400">展开后可选词包重新生产指定维度</p>
          </div>
        </div>
        {expanded
          ? <ChevronDown size={18} className="text-slate-400" />
          : <ChevronRight size={18} className="text-slate-400" />}
      </button>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            id="package-panel-body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="border-t border-slate-100 overflow-hidden"
          >
            <div className="p-5">
              {/* 一键补全缺失字段（全局） */}
              <div className="mb-4 flex items-center justify-between gap-3 p-3 rounded-2xl bg-blue-50/50 border border-blue-100">
                <div className="text-xs text-slate-600 min-w-0">
                  <span className="font-bold text-blue-800">一键补全缺失字段</span>
                  <span className="ml-1 text-slate-500">扫描所有词包，重生缺 extension_words / exam_sentence 的项（跳过 false 词，跨包去重）</span>
                </div>
                <button
                  onClick={openBackfill}
                  disabled={backfillLoading || backfillSubmitting}
                  className="shrink-0 px-3 py-2 text-xs font-bold rounded-xl flex items-center gap-1.5 bg-blue-600 text-white hover:bg-blue-700 transition-colors disabled:opacity-50"
                >
                  <Wand2 size={12} />
                  一键补全
                </button>
              </div>
              {loading && batches === null ? (
                <div className="flex items-center justify-center py-10 text-slate-400 gap-2">
                  <Loader2 size={18} className="animate-spin" />
                  <span className="text-sm">正在加载词包列表...</span>
                </div>
              ) : !batches || batches.length === 0 ? (
                <div className="text-center py-10 text-slate-400">
                  <FileText size={32} className="mx-auto mb-2 text-slate-300" />
                  <p className="text-sm">暂无词包</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                  {batches.map(b => {
                    const st = STATUS_MAP[b.status] ?? STATUS_MAP.pending
                    const Icon = st.icon
                    const canRegen = b.status !== 'processing'
                    return (
                      <div
                        key={b.id}
                        className="p-4 bg-slate-50 rounded-2xl border border-slate-100 flex items-center gap-3"
                      >
                        <div className="w-10 h-10 bg-white rounded-xl flex items-center justify-center text-blue-600 shadow-sm border border-slate-100 shrink-0">
                          <FileText size={18} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <h4 className="font-bold text-sm text-slate-900 truncate">{b.name}</h4>
                          <div className="flex items-center gap-3 mt-1 text-[11px] text-slate-500">
                            <span className="flex items-center gap-1">
                              <Hash size={10} />{b.total_words} 词
                            </span>
                            <span className="flex items-center gap-1">
                              <Calendar size={10} />{formatDate(b.created_at)}
                            </span>
                            <span className={`flex items-center gap-1 px-1.5 py-0.5 rounded font-medium ${st.badgeCls}`}>
                              <Icon size={10} className={st.iconCls} />{st.label}
                            </span>
                          </div>
                        </div>
                        <button
                          onClick={() => canRegen && setActiveBatch(b)}
                          disabled={!canRegen}
                          title={canRegen ? '选择维度重新生产' : '生产中，暂不可重生'}
                          className={`shrink-0 px-3 py-2 text-xs font-bold rounded-xl flex items-center gap-1.5 transition-colors ${
                            canRegen
                              ? 'bg-rose-50 text-rose-700 border border-rose-200 hover:bg-rose-100'
                              : 'bg-slate-100 text-slate-400 border border-slate-200 cursor-not-allowed'
                          }`}
                        >
                          <RefreshCw size={12} />
                          重新生产
                        </button>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {activeBatch && (
          <PackageRegenModal
            batch={activeBatch}
            onClose={closeModal}
            onSuccess={fetchBatches}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {backfillOpen && (
          <div
            className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm"
            onClick={() => { if (!backfillSubmitting) setBackfillOpen(false) }}
          >
            <motion.div
              role="dialog"
              aria-modal="true"
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              onClick={e => e.stopPropagation()}
              className="bg-white w-full max-w-md rounded-[28px] shadow-2xl overflow-hidden"
            >
              <div className="p-5 border-b border-slate-100 flex items-center justify-between bg-blue-50/50">
                <div className="flex items-center gap-2.5">
                  <div className="w-9 h-9 bg-blue-600 text-white rounded-xl flex items-center justify-center">
                    <Wand2 size={18} />
                  </div>
                  <h3 className="font-bold text-base text-slate-900">一键补全缺失字段</h3>
                </div>
                <button
                  onClick={() => setBackfillOpen(false)}
                  disabled={backfillSubmitting}
                  className="p-2 hover:bg-slate-100 rounded-full disabled:opacity-50"
                >
                  <X size={18} />
                </button>
              </div>

              <div className="p-5 space-y-4">
                {backfillLoading ? (
                  <div className="flex items-center gap-2 text-slate-500 text-sm py-4">
                    <Loader2 size={16} className="animate-spin" /> 正在扫描缺失项...
                  </div>
                ) : !backfillPreview || backfillPreview.unique_missing === 0 ? (
                  <p className="text-sm text-slate-500 py-2">没有需要补全的缺失字段项 🎉</p>
                ) : (
                  <>
                    <div className="text-sm text-slate-700">
                      将对 <strong className="text-blue-700">{backfillPreview.packages.length}</strong> 个词包补全，
                      去重后实际约 <strong className="text-rose-700">{backfillPreview.unique_missing}</strong> 条
                      <span className="text-xs text-slate-400">（下列按包明细含跨包重复，合计 {backfillPreview.total_missing} 条）</span>：
                    </div>
                    <div className="max-h-48 overflow-y-auto rounded-xl border border-slate-100 divide-y divide-slate-50">
                      {backfillPreview.packages.map(p => (
                        <div key={p.package_id} className="flex items-center justify-between px-3 py-2 text-xs">
                          <span className="text-slate-700 truncate">{p.name}</span>
                          <span className="text-slate-500 shrink-0 ml-2">{p.missing} 条</span>
                        </div>
                      ))}
                    </div>
                    <div className="flex items-start gap-2 p-3 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-900">
                      <AlertTriangle size={14} className="shrink-0 mt-0.5" />
                      <span>仅重生缺字段项，不动 false 词与已正确项。后台顺序处理，各包状态会依次变化。</span>
                    </div>
                  </>
                )}
              </div>

              <div className="p-5 border-t border-slate-100 bg-slate-50/50 flex justify-end gap-3">
                <button
                  onClick={() => setBackfillOpen(false)}
                  disabled={backfillSubmitting}
                  className="px-4 py-2 text-sm font-bold text-slate-600 hover:bg-slate-100 rounded-xl disabled:opacity-50"
                >
                  取消
                </button>
                <button
                  onClick={confirmBackfill}
                  disabled={backfillSubmitting || backfillLoading || !backfillPreview || backfillPreview.unique_missing === 0}
                  className="px-5 py-2 text-sm font-bold rounded-xl bg-blue-600 text-white hover:bg-blue-700 flex items-center gap-2 disabled:bg-slate-200 disabled:text-slate-400"
                >
                  {backfillSubmitting ? <><Loader2 size={16} className="animate-spin" /> 触发中</> : <>开始补全</>}
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </section>
  )
}
