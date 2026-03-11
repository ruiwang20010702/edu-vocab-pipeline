import { motion } from 'motion/react'
import { DIMENSION_LABELS } from './constants'
import type { WordGroup } from './types'

export function WordGroupCard({ group, onOpen }: { group: WordGroup; onOpen: () => void }) {
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
