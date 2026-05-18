import { useState, useEffect, useCallback } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Package as PackageIcon, ChevronDown, ChevronRight, Loader2, RefreshCw, Hash, Calendar, CheckCircle2, Clock, AlertCircle, FileText } from 'lucide-react'
import { api, ApiError } from '../../lib/api'
import { useToast } from '../../components/Toast'
import type { BatchInfo } from '../../types'
import PackageRegenModal from './PackageRegenModal'

const STATUS_MAP: Record<string, { label: string; color: string; icon: typeof CheckCircle2 }> = {
  completed: { label: '已完成', color: 'emerald', icon: CheckCircle2 },
  processing: { label: '生产中', color: 'blue', icon: Loader2 },
  pending: { label: '待处理', color: 'slate', icon: Clock },
  failed: { label: '失败', color: 'rose', icon: AlertCircle },
}

function formatDate(dateStr: string) {
  const d = new Date(dateStr)
  return d.toLocaleDateString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
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

  // 首次展开时懒加载
  useEffect(() => {
    if (expanded && batches === null) void fetchBatches()
  }, [expanded, batches, fetchBatches])

  const count = batches?.length

  return (
    <section className="bg-white rounded-[24px] border border-slate-200 overflow-hidden">
      <button
        onClick={() => setExpanded(v => !v)}
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
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="border-t border-slate-100 overflow-hidden"
          >
            <div className="p-5">
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
                            <span className={`flex items-center gap-1 px-1.5 py-0.5 rounded bg-${st.color}-50 text-${st.color}-700 font-medium`}>
                              <Icon size={10} />{st.label}
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
            onClose={() => setActiveBatch(null)}
            onSuccess={fetchBatches}
          />
        )}
      </AnimatePresence>
    </section>
  )
}
