import { useState, useEffect } from 'react'
import { motion } from 'motion/react'
import { X, Clock, ChevronRight, FileText, CheckCircle2, Loader2, Hash, Calendar, AlertCircle } from 'lucide-react'
import { api } from '../lib/api'
import type { BatchInfo } from '../types'

interface Props {
  onClose: () => void
  onSelectBatch: (batchId: string) => void
}

const STATUS_MAP: Record<string, { label: string; color: string; icon: typeof CheckCircle2 }> = {
  completed: { label: '已完成', color: 'emerald', icon: CheckCircle2 },
  processing: { label: '生产中', color: 'blue', icon: Loader2 },
  pending: { label: '待处理', color: 'slate', icon: Clock },
  failed: { label: '失败', color: 'rose', icon: AlertCircle },
}

export default function BatchHistoryModal({ onClose, onSelectBatch }: Props) {
  const [batches, setBatches] = useState<BatchInfo[]>([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    api.get<BatchInfo[]>('/batches')
      .then(setBatches)
      .catch(err => console.error('加载历史批次失败', err))
      .finally(() => setIsLoading(false))
  }, [])

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr)
    return d.toLocaleDateString('zh-CN', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    })
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        className="bg-white w-full max-w-3xl max-h-[80vh] rounded-[32px] shadow-2xl overflow-hidden flex flex-col"
      >
        <div className="p-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-blue-600 text-white rounded-xl flex items-center justify-center shadow-lg shadow-blue-200">
              <Clock size={20} />
            </div>
            <div>
              <h3 className="font-bold text-xl text-slate-900">导入历史</h3>
              <p className="text-xs text-slate-400">历史上传的词表批次记录</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-full transition-colors">
            <X size={20} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-20 space-y-4">
              <Loader2 className="animate-spin text-blue-600" size={32} />
              <p className="text-sm text-slate-400">正在加载历史记录...</p>
            </div>
          ) : batches.length === 0 ? (
            <div className="text-center py-20 space-y-4">
              <div className="w-16 h-16 bg-slate-50 text-slate-300 rounded-full flex items-center justify-center mx-auto">
                <FileText size={32} />
              </div>
              <p className="text-slate-400">暂无上传历史</p>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="grid grid-cols-12 gap-3 px-4 py-2 text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                <div className="col-span-4">批次名称</div>
                <div className="col-span-3">上传时间</div>
                <div className="col-span-2 text-center">单词数</div>
                <div className="col-span-2 text-center">状态</div>
                <div className="col-span-1" />
              </div>
              {batches.map((batch) => {
                const st = STATUS_MAP[batch.status] ?? STATUS_MAP.pending
                const Icon = st.icon
                return (
                  <button
                    key={batch.id}
                    onClick={() => onSelectBatch(batch.id)}
                    className="w-full grid grid-cols-12 gap-3 items-center p-4 bg-slate-50 hover:bg-blue-50 rounded-2xl border border-slate-100 hover:border-blue-200 transition-all group"
                  >
                    <div className="col-span-4 flex items-center gap-3 text-left min-w-0">
                      <div className="w-10 h-10 bg-white rounded-xl flex items-center justify-center text-blue-600 shadow-sm border border-slate-100 shrink-0">
                        <FileText size={18} />
                      </div>
                      <div className="min-w-0">
                        <h4 className="font-bold text-sm text-slate-900 group-hover:text-blue-600 transition-colors truncate">
                          {batch.name}
                        </h4>
                        <p className="text-[10px] text-slate-400 font-mono truncate">#{batch.id}</p>
                      </div>
                    </div>
                    <div className="col-span-3 text-left">
                      <span className="text-xs text-slate-500 flex items-center gap-1.5">
                        <Calendar size={12} className="text-slate-400 shrink-0" />
                        {formatDate(batch.created_at)}
                      </span>
                    </div>
                    <div className="col-span-2 text-center">
                      <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-blue-50 text-blue-700 text-xs font-bold rounded-lg">
                        <Hash size={11} />
                        {batch.total_words} 词
                      </span>
                    </div>
                    <div className="col-span-2 text-center">
                      <span className={`inline-flex items-center gap-1 px-2.5 py-1 bg-${st.color}-50 text-${st.color}-700 text-xs font-medium rounded-lg`}>
                        <Icon size={11} />
                        {st.label}
                      </span>
                    </div>
                    <div className="col-span-1 text-right">
                      <ChevronRight size={18} className="text-slate-300 group-hover:text-blue-600 group-hover:translate-x-1 transition-all inline-block" />
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>
      </motion.div>
    </div>
  )
}
