import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { Activity, CheckCircle2, AlertCircle, Clock, Loader2, ArrowRight, Database } from 'lucide-react'
import { api } from '../lib/api'
import type { BatchInfo } from '../types'

interface Props {
  batchId: string | null
  onGoToReview: () => void
}

const WORDS_POOL = ['empathy', 'absorb', 'invisible', 'education', 'vocabulary', 'dynamic', 'future', 'learning']

export default function MonitoringPage({ batchId, onGoToReview }: Props) {
  const [batch, setBatch] = useState<BatchInfo | null>(null)
  const [logs, setLogs] = useState<string[]>([])
  const [activeWord, setActiveWord] = useState('')
  const [activeGate, setActiveGate] = useState(1)
  const pollingRef = useRef<ReturnType<typeof setInterval>>(undefined)

  useEffect(() => {
    if (!batchId) return
    setBatch(null)

    const now = () => new Date().toLocaleTimeString()
    setLogs([
      `[${now()}] 启动生产批次 #${batchId}`,
      `[${now()}] 正在加载 AI 模型...`,
      `[${now()}] 批次策略: 逐词生成 + 质检`,
    ])

    const poll = async () => {
      try {
        const b = await api.get<BatchInfo>(`/batches/info/${batchId}`)
        setBatch(b)

        const p = b.total_words > 0 ? Math.round((b.processed_words / b.total_words) * 100) : 0
        if (p < 100) {
          setActiveWord(WORDS_POOL[Math.floor(Math.random() * WORDS_POOL.length)])
          setActiveGate(Math.floor(Math.random() * 3) + 1)
        }

        if (b.status === 'completed' || b.status === 'failed') {
          setLogs(prev => [...prev, `[${now()}] 生产${b.status === 'completed' ? '完成' : '异常终止'}`])
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
  const isRunning = batch != null && batch.status !== 'completed' && batch.status !== 'failed'
  const approved = batch?.processed_words ?? 0
  const failedCount = batch?.failed_count ?? 0
  const passRate = batch?.pass_rate != null ? Math.round(batch.pass_rate) : 0

  if (!batchId) {
    return (
      <div className="bg-white rounded-[32px] p-10 text-center border border-white shadow-sm">
        <Activity size={48} className="mx-auto text-slate-300 mb-4" />
        <p className="text-slate-400">请先在「词表导入」页面创建生产任务</p>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {/* ===== 上半区: 内容工厂 ===== */}
      <section className="bg-white rounded-[32px] p-10 border border-white relative overflow-hidden shadow-lg">
        {/* 装饰 */}
        <div className="absolute top-0 left-0 w-full h-[2px] bg-slate-100" />
        <div className="absolute -right-20 -top-20 w-64 h-64 bg-slate-50/50 rounded-full blur-3xl" />
        <div className="absolute -left-20 -bottom-20 w-64 h-64 bg-slate-50/50 rounded-full blur-3xl" />

        <div className="relative z-10 space-y-10">
          {/* 顶部状态栏 */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 bg-blue-600 rounded-2xl flex items-center justify-center text-white shadow-lg shadow-blue-200">
                <Activity size={24} className={isRunning ? 'animate-pulse' : ''} />
              </div>
              <div>
                <h2 className="text-2xl font-bold tracking-tight text-slate-900">
                  {isRunning ? '内容工厂正在运转...' : progress >= 100 ? '生产任务已完成' : '等待启动...'}
                </h2>
                {batch && (
                  <p className="text-xs font-bold text-blue-600 uppercase tracking-widest">
                    批次: {batch.name || batchId}
                  </p>
                )}
              </div>
            </div>
            <div className="text-right">
              <p className="text-3xl font-black text-blue-600">{progress}%</p>
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-[0.2em]">Overall Progress</p>
            </div>
          </div>

          {/* 主面板: 左 Pipeline + 右 Stats */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            {/* 左侧: Pipeline 动画 + 进度条 */}
            <div className="lg:col-span-2 space-y-8">
              {/* 流水线可视化 */}
              <div className="relative h-48 bg-slate-50 rounded-[32px] border border-slate-100 flex items-center justify-center overflow-hidden">
                <AnimatePresence mode="wait">
                  {isRunning ? (
                    <motion.div
                      key={activeWord}
                      initial={{ x: -100, opacity: 0, scale: 0.8 }}
                      animate={{ x: 0, opacity: 1, scale: 1 }}
                      exit={{ x: 100, opacity: 0, scale: 0.8 }}
                      className="flex flex-col items-center gap-4"
                    >
                      <div className="px-8 py-4 bg-white rounded-2xl shadow-xl border border-slate-100 flex items-center gap-4">
                        <span className="text-3xl font-black text-slate-900">{activeWord}</span>
                        <div className="h-8 w-px bg-slate-200" />
                        <div className="flex flex-col">
                          <span className="text-[10px] font-bold text-slate-400 uppercase">Processing</span>
                          <div className="flex gap-1">
                            {[1, 2, 3].map(g => (
                              <div
                                key={g}
                                className={`w-2 h-2 rounded-full transition-colors duration-300 ${
                                  activeGate >= g ? 'bg-blue-500' : 'bg-slate-200'
                                }`}
                              />
                            ))}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 text-blue-600 text-xs font-bold uppercase tracking-widest">
                        <Loader2 size={14} className="animate-spin" />
                        Gate {activeGate} 质量校验中...
                      </div>
                    </motion.div>
                  ) : progress >= 100 ? (
                    <motion.div
                      initial={{ opacity: 0, scale: 0.9 }}
                      animate={{ opacity: 1, scale: 1 }}
                      className="text-center space-y-2"
                    >
                      <div className="w-16 h-16 bg-emerald-500 text-white rounded-full flex items-center justify-center mx-auto mb-4 shadow-lg shadow-emerald-200">
                        <CheckCircle2 size={32} />
                      </div>
                      <h3 className="text-xl font-bold text-slate-900">全量生产完毕</h3>
                      <p className="text-sm text-slate-400">所有内容已通过质检</p>
                    </motion.div>
                  ) : (
                    <p className="text-slate-400">等待数据...</p>
                  )}
                </AnimatePresence>

                {/* 传送带装饰 */}
                {isRunning && (
                  <div className="absolute bottom-0 left-0 w-full h-2 bg-blue-100">
                    <motion.div
                      animate={{ x: [-20, 0] }}
                      transition={{ repeat: Infinity, duration: 0.5, ease: 'linear' }}
                      className="h-full w-[120%] bg-[repeating-linear-gradient(90deg,#3B82F6_0px,#3B82F6_2px,transparent_2px,transparent_20px)] opacity-20"
                    />
                  </div>
                )}
              </div>

              {/* 进度条 */}
              <div className="space-y-4">
                <div className="h-3 bg-slate-100 rounded-full overflow-hidden p-0.5 border border-slate-200">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${progress}%` }}
                    className="h-full bg-gradient-to-r from-blue-400 to-blue-600 rounded-full relative"
                  >
                    <div className="absolute inset-0 bg-[linear-gradient(45deg,rgba(255,255,255,0.1)_25%,transparent_25%,transparent_50%,rgba(255,255,255,0.1)_50%,rgba(255,255,255,0.1)_75%,transparent_75%,transparent)] bg-[length:20px_20px] animate-[progress-stripe_1s_linear_infinite]" />
                  </motion.div>
                </div>
                <div className="flex justify-between items-center px-2">
                  <div className="flex gap-8">
                    <div className="flex flex-col">
                      <span className="text-[10px] font-bold text-slate-400 uppercase">已入库</span>
                      <span className="text-lg font-black text-emerald-600">{approved}</span>
                    </div>
                    <div className="flex flex-col">
                      <span className="text-[10px] font-bold text-slate-400 uppercase">待修复</span>
                      <span className="text-lg font-black text-rose-600">{failedCount}</span>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="text-[10px] font-bold text-slate-400 uppercase">预计耗时</span>
                    <p className="text-sm font-bold text-slate-500">
                      ~ {batch ? Math.ceil((batch.total_words - batch.processed_words) * 0.2) : 0}s
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* 右侧: Stats Bento */}
            <div className="grid grid-cols-1 gap-4">
              <div className="p-6 bg-blue-50/50 rounded-[24px] border border-blue-100 flex flex-col justify-between">
                <span className="text-[10px] font-bold text-blue-600/60 uppercase tracking-widest">总生产任务</span>
                <div className="flex items-end justify-between">
                  <h4 className="text-4xl font-black text-blue-700">{batch?.total_words ?? 0}</h4>
                  <div className="p-2 bg-white rounded-xl border border-blue-100">
                    <Database size={20} className="text-blue-600" />
                  </div>
                </div>
              </div>
              <div className="p-6 bg-emerald-50/50 rounded-[24px] border border-emerald-100 flex flex-col justify-between">
                <span className="text-[10px] font-bold text-emerald-600/60 uppercase tracking-widest">当前合格率</span>
                <div className="flex items-end justify-between">
                  <h4 className="text-4xl font-black text-emerald-600">{passRate}%</h4>
                  <div className="p-2 bg-white rounded-xl border border-emerald-100">
                    <CheckCircle2 size={20} className="text-emerald-600" />
                  </div>
                </div>
              </div>
              <div className="p-6 bg-rose-50/50 rounded-[24px] border border-rose-100 flex flex-col justify-between">
                <span className="text-[10px] font-bold text-rose-600/60 uppercase tracking-widest">异常拦截</span>
                <div className="flex items-end justify-between">
                  <h4 className="text-4xl font-black text-rose-600">{failedCount}</h4>
                  <div className="p-2 bg-white rounded-xl border border-rose-100">
                    <AlertCircle size={20} className="text-rose-600" />
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* 操作区 */}
          <AnimatePresence>
            {failedCount > 0 && !isRunning && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="w-full max-w-2xl mx-auto p-6 bg-rose-50 border border-rose-100 rounded-[32px] flex items-center justify-between gap-6 shadow-xl shadow-rose-100"
              >
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 bg-rose-100 rounded-2xl flex items-center justify-center text-rose-600">
                    <AlertCircle size={24} />
                  </div>
                  <div>
                    <h4 className="font-bold text-rose-900">检测到 {failedCount} 个质量异常</h4>
                    <p className="text-xs text-rose-600/70">建议前往修复队列处理</p>
                  </div>
                </div>
                <button
                  onClick={onGoToReview}
                  className="px-6 py-3 bg-rose-600 text-white rounded-2xl font-bold hover:bg-rose-700 transition-all flex items-center gap-2 shadow-lg shadow-rose-200 shrink-0"
                >
                  前往质检审核
                  <ArrowRight size={18} />
                </button>
              </motion.div>
            )}
          </AnimatePresence>

          {failedCount === 0 && progress >= 100 && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center">
              <button
                onClick={onGoToReview}
                className="bg-blue-600 text-white px-12 py-4 rounded-2xl font-bold flex items-center gap-3 hover:bg-blue-700 transition-all shadow-xl shadow-blue-200 mx-auto"
              >
                进入质检审核
                <ArrowRight size={20} />
              </button>
            </motion.div>
          )}
        </div>
      </section>

      {/* ===== 下半区: 系统运行日志 ===== */}
      <section className="bg-white rounded-[32px] border border-white overflow-hidden shadow-sm">
        <div className="px-8 py-6 border-b border-slate-100 flex items-center justify-between">
          <h3 className="font-bold text-xl text-slate-900 flex items-center gap-2">
            <Clock size={20} className="text-blue-600" />
            系统运行日志
          </h3>
          <div className="flex items-center gap-2">
            {isRunning && <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />}
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Live Stream</span>
          </div>
        </div>
        <div className="p-8 h-64 overflow-y-auto font-mono text-xs space-y-3 bg-slate-50/50">
          {logs.map((log, i) => (
            <div key={i} className="flex gap-4">
              <span className="text-slate-300 shrink-0">{i + 1}.</span>
              <p className="text-slate-500">{log}</p>
            </div>
          ))}
          {isRunning && (
            <div className="flex gap-4 text-blue-600">
              <span className="text-blue-300 shrink-0">{logs.length + 1}.</span>
              <p className="flex items-center gap-2">
                <Loader2 size={12} className="animate-spin" />
                正在执行 Gate {activeGate} 深度语义校验...
              </p>
            </div>
          )}
        </div>
      </section>

      <style>{`
        @keyframes progress-stripe {
          from { background-position: 0 0; }
          to { background-position: 20px 0; }
        }
      `}</style>
    </div>
  )
}
