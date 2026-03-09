import { useState, useEffect } from 'react'
import { motion } from 'motion/react'
import { BookOpen, CheckCircle2, Clock, TrendingUp } from 'lucide-react'
import { api } from '../lib/api'
import type { DashboardStats, BatchInfo } from '../types'

interface Props {
  onViewBatch: (batchId: string, view: 'monitoring' | 'review') => void
}

export default function DashboardPage({ onViewBatch }: Props) {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [batches, setBatches] = useState<BatchInfo[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const [s, b] = await Promise.all([
          api.get<DashboardStats>('/stats'),
          api.get<BatchInfo[]>('/batches'),
        ])
        setStats(s)
        setBatches(b)
      } catch {
        // 后端尚未实现时 fallback
        setStats({ total_words: 0, approved_count: 0, pending_count: 0, rejected_count: 0, pass_rate: 0 })
        setBatches([])
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-2 border-white/30 border-t-white rounded-full animate-spin" />
      </div>
    )
  }

  const statCards = [
    { label: '词汇总量', value: stats?.total_words ?? 0, icon: BookOpen, color: 'from-blue-500/20 to-blue-600/20' },
    { label: '已通过', value: stats?.approved_count ?? 0, icon: CheckCircle2, color: 'from-green-500/20 to-green-600/20' },
    { label: '待审核', value: stats?.pending_count ?? 0, icon: Clock, color: 'from-yellow-500/20 to-yellow-600/20' },
    { label: '通过率', value: `${(stats?.pass_rate ?? 0).toFixed(1)}%`, icon: TrendingUp, color: 'from-purple-500/20 to-purple-600/20' },
  ]

  return (
    <div className="space-y-6">
      {/* 统计卡片 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {statCards.map((card, i) => (
          <motion.div
            key={card.label}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1 }}
            className={`glass-card rounded-3xl p-6 bg-gradient-to-br ${card.color} module-hover`}
          >
            <div className="flex items-center justify-between mb-3">
              <card.icon size={24} className="text-white/70" />
            </div>
            <p className="text-3xl font-bold text-white">{card.value}</p>
            <p className="text-sm text-white/60 mt-1">{card.label}</p>
          </motion.div>
        ))}
      </div>

      {/* 批次列表 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
        className="glass-card rounded-3xl p-6"
      >
        <h2 className="text-lg font-bold text-white mb-4">批次历史</h2>
        {batches.length === 0 ? (
          <p className="text-white/50 text-center py-8">暂无批次数据</p>
        ) : (
          <div className="space-y-3">
            {batches.map(batch => (
              <div
                key={batch.id}
                className="flex items-center justify-between p-4 rounded-2xl bg-white/5 hover:bg-white/10 transition-colors cursor-pointer"
                onClick={() => onViewBatch(batch.id, batch.status === 'completed' ? 'review' : 'monitoring')}
              >
                <div>
                  <p className="font-medium text-white">{batch.name}</p>
                  <p className="text-sm text-white/50">{batch.total_words} 词 · {batch.created_at}</p>
                </div>
                <div className="flex items-center gap-3">
                  {batch.pass_rate !== null && (
                    <span className="text-sm text-white/60">{batch.pass_rate.toFixed(1)}%</span>
                  )}
                  <StatusBadge status={batch.status} />
                </div>
              </div>
            ))}
          </div>
        )}
      </motion.div>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    pending: 'bg-gray-400/20 text-gray-200',
    processing: 'bg-blue-400/20 text-blue-200',
    completed: 'bg-green-400/20 text-green-200',
    failed: 'bg-red-400/20 text-red-200',
  }
  const labels: Record<string, string> = {
    pending: '待处理',
    processing: '处理中',
    completed: '已完成',
    failed: '失败',
  }
  return (
    <span className={`px-3 py-1 rounded-full text-xs font-medium ${styles[status] ?? styles.pending}`}>
      {labels[status] ?? status}
    </span>
  )
}
