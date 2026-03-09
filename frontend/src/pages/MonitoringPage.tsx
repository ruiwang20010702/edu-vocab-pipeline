import { useState, useEffect, useRef, } from 'react'
import { motion } from 'motion/react'
import { Activity, CheckCircle2, XCircle, ArrowRight } from 'lucide-react'
import { api } from '../lib/api'
import type { BatchInfo } from '../types'

interface Props {
  batchId: string | null
  onGoToReview: () => void
}

export default function MonitoringPage({ batchId, onGoToReview }: Props) {
  const [batch, setBatch] = useState<BatchInfo | null>(null)
  const pollingRef = useRef<ReturnType<typeof setInterval>>(undefined)

  useEffect(() => {
    if (!batchId) return

    const poll = async () => {
      try {
        const b = await api.get<BatchInfo>(`/batches/info/${batchId}`)
        setBatch(b)
        if (b.status === 'completed' || b.status === 'failed') {
          clearInterval(pollingRef.current)
        }
      } catch (e) {
        console.error('轮询批次状态失败', e)
      }
    }

    poll()
    pollingRef.current = setInterval(poll, 3000)
    return () => clearInterval(pollingRef.current)
  }, [batchId])

  const progress = batch ? Math.round((batch.processed_words / Math.max(batch.total_words, 1)) * 100) : 0

  return (
    <div className="space-y-6">
      {!batchId ? (
        <div className="glass-card rounded-3xl p-10 text-center">
          <Activity size={48} className="mx-auto text-white/30 mb-4" />
          <p className="text-white/50">请先在「词表导入」页面创建生产任务</p>
        </div>
      ) : (
        <>
          {/* 进度 */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass-card rounded-3xl p-6"
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-white">生产进度</h2>
              <span className="text-white/60 text-sm">{batch?.name ?? ''}</span>
            </div>

            {/* 进度条 */}
            <div className="w-full h-4 bg-white/10 rounded-full overflow-hidden mb-2">
              <motion.div
                className="h-full bg-gradient-to-r from-blue-400 to-green-400 rounded-full"
                initial={{ width: 0 }}
                animate={{ width: `${progress}%` }}
                transition={{ duration: 0.5 }}
              />
            </div>
            <div className="flex items-center justify-between text-sm text-white/60">
              <span>{batch?.processed_words ?? 0} / {batch?.total_words ?? 0} 词</span>
              <span>{progress}%</span>
            </div>

            {/* 流水线动画 */}
            <div className="flex items-center justify-center gap-4 mt-6 text-sm">
              <PipelineStage label="导入" done={progress > 0} active={progress > 0 && progress < 30} />
              <ArrowRight size={16} className="text-white/30" />
              <PipelineStage label="生成" done={progress >= 30} active={progress >= 30 && progress < 70} />
              <ArrowRight size={16} className="text-white/30" />
              <PipelineStage label="Layer1 质检" done={progress >= 70} active={progress >= 70 && progress < 90} />
              <ArrowRight size={16} className="text-white/30" />
              <PipelineStage label="Layer2 AI" done={progress >= 90} active={progress >= 90 && progress < 100} />
              <ArrowRight size={16} className="text-white/30" />
              <PipelineStage label="完成" done={progress === 100} active={false} />
            </div>
          </motion.div>

          {/* 统计 */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <StatCard label="处理词数" value={batch?.processed_words ?? 0} icon={Activity} />
            <StatCard label="通过率" value={batch?.pass_rate !== null ? `${(batch?.pass_rate ?? 0).toFixed(1)}%` : '-'} icon={CheckCircle2} />
            <StatCard label="异常数" value={batch ? batch.total_words - batch.processed_words : '-'} icon={XCircle} />
          </div>

          {/* 完成后入口 */}
          {batch?.status === 'completed' && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center">
              <button
                onClick={onGoToReview}
                className="px-8 py-3 bg-white/25 hover:bg-white/35 text-white font-semibold rounded-2xl transition-all border border-white/30"
              >
                前往质检审核 →
              </button>
            </motion.div>
          )}
        </>
      )}
    </div>
  )
}

function PipelineStage({ label, done, active }: { label: string; done: boolean; active: boolean }) {
  return (
    <div className={`px-4 py-2 rounded-xl text-center transition-all ${
      done ? 'bg-green-400/20 text-green-200' : active ? 'bg-blue-400/20 text-blue-200 animate-pulse' : 'bg-white/5 text-white/30'
    }`}>
      {label}
    </div>
  )
}

function StatCard({ label, value, icon: Icon }: { label: string; value: string | number; icon: React.ComponentType<{ size: number; className?: string }> }) {
  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass-card rounded-3xl p-5">
      <Icon size={20} className="text-white/50 mb-2" />
      <p className="text-2xl font-bold text-white">{value}</p>
      <p className="text-sm text-white/50">{label}</p>
    </motion.div>
  )
}
