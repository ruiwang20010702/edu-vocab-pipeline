import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import {
  LayoutDashboard, CheckCircle2, AlertCircle, TrendingUp,
  Clock, Activity, PieChart, Loader2, ArrowRight, ArrowUpRight,
} from 'lucide-react'
import { api } from '../lib/api'
import type { DashboardStats, BatchInfo } from '../types'

interface Props {
  onViewBatch: (batchId: string, view: 'monitoring' | 'review') => void
}

/* ===== 维度映射与颜色 ===== */

const DIMENSION_LABELS: Record<string, string> = {
  phonetic: '语音 Sound',
  syllable: '音节 Syllables',
  meaning: '语义 Meaning',
  chunk: '语境 Context',
  sentence: '语境 Context',
  mnemonic_root_affix: '助记 Mnemonic',
  mnemonic_word_in_word: '助记 Mnemonic',
  mnemonic_sound_meaning: '助记 Mnemonic',
  mnemonic_exam_app: '助记 Mnemonic',
}

const ALL_DIMENSIONS = ['语音 Sound', '语义 Meaning', '音节 Syllables', '语境 Context', '助记 Mnemonic']

// 每个维度的完整规则列表 + 人类可读标签（field 与后端 rule_id 一一对应）
const DIMENSION_RULES: Record<string, { field: string; label: string }[]> = {
  '语音 Sound': [
    { field: 'P1', label: 'IPA 格式校验' },
    { field: 'P2', label: '音标-音节对齐校验' },
  ],
  '语义 Meaning': [
    { field: 'M3', label: '词性标签格式校验' },
    { field: 'M4', label: '词性换行分隔校验' },
    { field: 'M5', label: '义项分号分隔校验' },
    { field: 'M6', label: '禁止括号校验' },
    { field: 'M7', label: '词义-词性匹配（AI）' },
  ],
  '音节 Syllables': [
    { field: 'S1', label: '元音锚点校验' },
    { field: 'S2', label: '音节分隔符校验' },
    { field: 'S3', label: '原子单位完整性校验' },
    { field: 'S4', label: '单音节不切分校验' },
  ],
  '语境 Context': [
    { field: 'C1', label: '语块含目标词校验' },
    { field: 'C2', label: '语块长度校验' },
    { field: 'C3', label: '搭配合理性（AI）' },
    { field: 'C4', label: '语块禁止括号校验' },
    { field: 'C5', label: '中文独立成行校验' },
    { field: 'E6', label: '例句含目标词校验' },
    { field: 'E7', label: '例句长度校验' },
    { field: 'E8', label: '中文翻译非空校验' },
    { field: 'E1', label: '语法难度（AI）' },
    { field: 'E2', label: '主干结构（AI）' },
    { field: 'E3', label: '连接词限制（AI）' },
    { field: 'E4', label: '从句限制（AI）' },
    { field: 'E5', label: '禁区检测（AI）' },
    { field: 'E8_AI', label: '中文翻译语义对应（AI）' },
    { field: 'E9', label: '义项匹配（AI）' },
    { field: 'E10', label: '语言地道性（AI）' },
    { field: 'E11', label: '内容安全性（AI）' },
  ],
  '助记 Mnemonic': [
    { field: 'N1', label: '助记类型校验' },
    { field: 'N2', label: '助记结构完整性校验' },
    { field: 'N3', label: '公式符号校验' },
    { field: 'N4', label: '口诀字数校验' },
    { field: 'N5', label: '话术字数校验' },
    { field: 'N5_AI', label: '话术完整性（AI）' },
    { field: 'N6', label: '逻辑合理性（AI）' },
  ],
}

const DIMENSION_COLORS: Record<string, { bar: string; bg: string; text: string }> = {
  '语音 Sound': { bar: 'bg-blue-400', bg: 'bg-blue-50', text: 'text-blue-600' },
  '语义 Meaning': { bar: 'bg-emerald-500', bg: 'bg-emerald-50', text: 'text-emerald-600' },
  '音节 Syllables': { bar: 'bg-purple-500', bg: 'bg-purple-50', text: 'text-purple-600' },
  '语境 Context': { bar: 'bg-blue-600', bg: 'bg-blue-50', text: 'text-blue-700' },
  '助记 Mnemonic': { bar: 'bg-yellow-500', bg: 'bg-yellow-50', text: 'text-yellow-700' },
}

export default function DashboardPage({ onViewBatch }: Props) {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [batches, setBatches] = useState<BatchInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [activeDim, setActiveDim] = useState<any | null>(null)

  useEffect(() => {
    const load = async () => {
      try {
        const [s, b] = await Promise.all([
          api.get<DashboardStats>('/stats'),
          api.get<BatchInfo[]>('/batches'),
        ])
        setStats(s)
        setBatches(b)
      } catch (e) {
        console.error('加载仪表板数据失败', e)
        setStats({ total_words: 0, approved_count: 0, pending_count: 0, rejected_count: 0, pass_rate: 0, issues: [] })
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
        <Loader2 className="animate-spin text-blue-600" size={48} />
      </div>
    )
  }

  const statCards = [
    { label: '总词数', value: (stats?.total_words ?? 0).toLocaleString(), icon: LayoutDashboard, iconBg: 'bg-blue-50 text-blue-600', valueColor: 'text-blue-700' },
    { label: '已入库', value: (stats?.approved_count ?? 0).toLocaleString(), icon: CheckCircle2, iconBg: 'bg-emerald-50 text-emerald-600', valueColor: 'text-emerald-700' },
    { label: '待处理', value: (stats?.pending_count ?? 0).toLocaleString(), icon: AlertCircle, iconBg: 'bg-rose-50 text-rose-600', valueColor: 'text-rose-700' },
    { label: '整体合格率', value: `${(stats?.pass_rate ?? 0).toFixed(1)}%`, icon: TrendingUp, iconBg: 'bg-yellow-50 text-yellow-600', valueColor: 'text-yellow-700' },
  ]

  // 聚合 Bad Case 分类：按 field(rule_id) 索引
  const issueByField: Record<string, number> = {}
  for (const issue of stats?.issues ?? []) {
    issueByField[issue.field] = (issueByField[issue.field] ?? 0) + issue.count
  }

  const badCases = ALL_DIMENSIONS.map(dim => {
    const rules = DIMENSION_RULES[dim] ?? []
    const colors = DIMENSION_COLORS[dim] ?? DIMENSION_COLORS['语音 Sound']
    const fields = rules.map(r => ({
      field: r.field,
      label: r.label,
      count: issueByField[r.field] ?? 0,
    }))
    return {
      label: dim,
      value: fields.reduce((sum, f) => sum + f.count, 0),
      fields,
      color: colors.bar,
      colors,
    }
  })

  return (
    <div className="space-y-8">
      {/* Stat Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {statCards.map((stat, i) => (
          <motion.div
            key={stat.label}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1 }}
            className="bg-white p-6 rounded-[32px] shadow-sm border border-white space-y-4 relative overflow-hidden group hover:shadow-md transition-shadow"
          >
            <div className="absolute inset-0 card-shimmer opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
            <div className="relative z-10">
              <div className="flex items-center justify-between mb-4">
                <div className={`w-12 h-12 rounded-2xl flex items-center justify-center ${stat.iconBg}`}>
                  <stat.icon size={24} />
                </div>
                <button className="w-8 h-8 flex items-center justify-center rounded-full bg-slate-50 hover:bg-blue-600 hover:text-white transition-all text-slate-400">
                  <ArrowUpRight size={14} strokeWidth={2.5} />
                </button>
              </div>
              <div className="space-y-1">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">{stat.label}</p>
                <h3 className={`text-4xl font-black tracking-tight ${stat.valueColor}`}>{stat.value}</h3>
              </div>
            </div>
          </motion.div>
        ))}
      </div>

      {/* Batch History + Bad Cases */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Batch History */}
        <section className="lg:col-span-2 bg-white p-8 rounded-[32px] shadow-sm border border-white space-y-6">
          <h3 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <Clock size={20} className="text-blue-600" />
            批次生产历史
          </h3>
          <div className="space-y-4">
            {batches.map(batch => (
              <div
                key={batch.id}
                onClick={() => onViewBatch(batch.id, 'monitoring')}
                className="flex items-center justify-between p-4 bg-slate-50 rounded-2xl border border-slate-100 hover:bg-blue-50/50 hover:border-blue-200 transition-all cursor-pointer group"
              >
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 bg-white rounded-xl flex items-center justify-center text-blue-600 border border-slate-100 shadow-sm group-hover:bg-blue-600 group-hover:text-white transition-all">
                    <Activity size={20} />
                  </div>
                  <div>
                    <h4 className="font-bold text-sm group-hover:text-blue-600 transition-colors">{batch.name}</h4>
                    <p className="text-[10px] text-slate-400 uppercase tracking-wider">{new Date(batch.created_at).toLocaleString()}</p>
                  </div>
                </div>
                <div className="flex items-center gap-6">
                  <div className="text-right">
                    <p className="text-xs font-bold">{batch.total_words}</p>
                    <p className="text-[10px] text-slate-400 uppercase">总词数</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={e => { e.stopPropagation(); onViewBatch(batch.id, 'review') }}
                      className="px-3 py-1 bg-white rounded-lg border border-slate-100 text-[10px] font-bold text-slate-400 hover:text-blue-600 hover:border-blue-300 transition-all"
                    >
                      质检
                    </button>
                    <button className="p-2 bg-white rounded-lg border border-slate-100 text-slate-300 group-hover:text-blue-600 transition-colors">
                      <ArrowRight size={16} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
            {batches.length === 0 && (
              <div className="text-center py-10 text-slate-400 italic text-sm">
                暂无生产批次记录
              </div>
            )}
          </div>
        </section>

        {/* Bad Case Classification */}
        <section className="bg-white rounded-[32px] shadow-sm border border-white overflow-hidden relative" style={{ minHeight: 420 }}>
          <AnimatePresence mode="wait">
            {!activeDim ? (
              <motion.div
                key="list"
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.2 }}
                className="p-8 space-y-5"
              >
                <h3 className="text-xl font-bold text-slate-900 flex items-center gap-2">
                  <PieChart size={20} className="text-blue-600" />
                  Bad Case 分类
                </h3>
                <div className="space-y-3">
                  {badCases.map((item, i) => {
                    const maxValue = Math.max(...badCases.map(b => b.value), 1)
                    return (
                      <button
                        key={i}
                        onClick={() => setActiveDim(item)}
                        className="w-full p-3 flex items-center gap-3 rounded-2xl hover:bg-slate-50 transition-all group text-left"
                      >
                        <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${item.color}`} />
                        <div className="flex-1">
                          <div className="flex justify-between items-center mb-1.5">
                            <span className="text-xs font-bold text-slate-600 group-hover:text-slate-900 transition-colors">{item.label}</span>
                            <span className="text-sm font-black text-slate-900">{item.value}</span>
                          </div>
                          <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                            <motion.div
                              initial={{ width: 0 }}
                              animate={{ width: `${(item.value / maxValue) * 100}%` }}
                              transition={{ delay: i * 0.1 + 0.5, duration: 0.8 }}
                              className={`h-full rounded-full ${item.color}`}
                            />
                          </div>
                        </div>
                        <ArrowRight size={14} className="text-slate-300 shrink-0 group-hover:text-blue-500 group-hover:translate-x-0.5 transition-all" />
                      </button>
                    )
                  })}
                </div>
              </motion.div>
            ) : (
              <motion.div
                key="detail"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                transition={{ duration: 0.2 }}
                className="flex flex-col h-full"
              >
                {/* Detail header */}
                <div className={`px-6 py-5 flex items-center gap-3 ${activeDim.colors.bg}`}>
                  <button
                    onClick={() => setActiveDim(null)}
                    className="w-8 h-8 flex items-center justify-center rounded-xl hover:bg-white/60 transition-colors text-slate-500"
                  >
                    <ArrowRight className="rotate-180" size={16} />
                  </button>
                  <div className={`w-3 h-3 rounded-full ${activeDim.color}`} />
                  <div className="flex-1">
                    <h3 className={`text-sm font-bold ${activeDim.colors.text}`}>{activeDim.label}</h3>
                    <p className="text-[10px] text-slate-400 uppercase tracking-widest">原子标准明细</p>
                  </div>
                  <span className={`text-2xl font-black ${activeDim.colors.text}`}>{activeDim.value}</span>
                </div>

                {/* Rules list */}
                <div className="flex-1 p-5 space-y-2 overflow-y-auto">
                  {activeDim.fields.map((field: any, j: number) => (
                    <motion.div
                      key={j}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: j * 0.04 }}
                      className="flex items-center justify-between p-3.5 bg-slate-50 rounded-xl border border-slate-100 hover:bg-white hover:shadow-sm transition-all"
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div className={`w-1.5 h-6 rounded-full shrink-0 ${field.count > 0 ? activeDim.color : 'bg-slate-200'}`} />
                        <div className="min-w-0">
                          <p className={`text-xs leading-snug ${field.count > 0 ? 'text-slate-800 font-medium' : 'text-slate-400'}`}>
                            {field.label}
                          </p>
                          <p className="text-[10px] text-slate-400 mt-0.5 font-mono">{field.field}</p>
                        </div>
                      </div>
                      <div className={`shrink-0 ml-3 px-2.5 py-1 rounded-lg ${
                        field.count > 0 ? `${activeDim.colors.bg} ${activeDim.colors.text}` : 'bg-slate-100 text-slate-300'
                      }`}>
                        <span className="text-sm font-black">{field.count}</span>
                      </div>
                    </motion.div>
                  ))}
                </div>

                {/* Back button */}
                <div className="px-5 pb-5">
                  <button
                    onClick={() => setActiveDim(null)}
                    className="w-full py-3 bg-slate-50 text-slate-500 rounded-xl text-sm font-bold hover:bg-slate-100 transition-colors flex items-center justify-center gap-2"
                  >
                    <ArrowRight className="rotate-180" size={14} />
                    返回维度总览
                  </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </section>
      </div>
    </div>
  )
}
