import { useState, useEffect, useMemo, useRef } from 'react'
import { motion } from 'motion/react'
import { X, AlertTriangle, RefreshCw, Loader2, Sparkles, CheckSquare, Square } from 'lucide-react'
import { api, ApiError } from '../../lib/api'
import { useToast } from '../../components/Toast'
import type { BatchInfo } from '../../types'
import {
  DIMENSION_LABELS,
  ALL_MNEMONIC_DIMS,
  BASIC_REGENERATABLE_DIMS,
  REGENERATABLE_DIMS,
  type RegenerableDim,
} from '../review/constants'

interface Props {
  batch: BatchInfo
  onClose: () => void
  onSuccess: () => void
}

interface PreviewStats {
  content_items: number
  review_items: number
  distinct_words: number
  by_dimension: Record<string, number>
}

const ARM_RESET_MS = 5000

export default function PackageRegenModal({ batch, onClose, onSuccess }: Props) {
  const { showToast } = useToast()
  // 默认选中助记 4 维度（最常用：prompt 升级后重灌助记）
  const [selected, setSelected] = useState<Set<RegenerableDim>>(
    () => new Set<RegenerableDim>(ALL_MNEMONIC_DIMS),
  )
  const [preview, setPreview] = useState<PreviewStats | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [confirmArmed, setConfirmArmed] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const armTimerRef = useRef<number | null>(null)

  // 维度选择变化时，重置确认态 + 300ms 防抖触发 dry-run preview
  useEffect(() => {
    setConfirmArmed(false)
    if (armTimerRef.current) {
      window.clearTimeout(armTimerRef.current)
      armTimerRef.current = null
    }

    if (selected.size === 0) {
      setPreview(null)
      setPreviewError(null)
      return
    }

    const ctrl = new AbortController()
    setPreviewLoading(true)
    setPreviewError(null)
    const timer = window.setTimeout(() => {
      api.post<PreviewStats>(
        `/batches/${batch.id}/produce/preview`,
        { dimensions: [...selected] },
        { signal: ctrl.signal },
      )
        .then(stats => {
          // race guard：旧请求 fulfilled 时若用户已切维度，本次响应已 stale
          if (ctrl.signal.aborted) return
          setPreview(stats)
        })
        .catch(err => {
          if (ctrl.signal.aborted) return
          setPreview(null)
          setPreviewError(err instanceof ApiError ? err.detail : '预览失败')
        })
        .finally(() => {
          if (!ctrl.signal.aborted) setPreviewLoading(false)
        })
    }, 300)

    return () => {
      ctrl.abort()
      window.clearTimeout(timer)
    }
  }, [selected, batch.id])

  // 确认按钮 5 秒回退
  const armConfirm = () => {
    setConfirmArmed(true)
    if (armTimerRef.current) window.clearTimeout(armTimerRef.current)
    armTimerRef.current = window.setTimeout(() => {
      setConfirmArmed(false)
      armTimerRef.current = null
    }, ARM_RESET_MS)
  }

  useEffect(() => () => {
    if (armTimerRef.current) window.clearTimeout(armTimerRef.current)
  }, [])

  // ESC 关闭（提交中不响应）
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !submitting) onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [submitting, onClose])

  const toggle = (dim: RegenerableDim) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(dim)) next.delete(dim); else next.add(dim)
      return next
    })
  }

  const selectMnemonic = () => setSelected(new Set<RegenerableDim>(ALL_MNEMONIC_DIMS))
  const selectAll = () => setSelected(new Set<RegenerableDim>(REGENERATABLE_DIMS))
  const clearAll = () => setSelected(new Set<RegenerableDim>())

  const submit = async () => {
    if (selected.size === 0 || submitting) return
    if (!confirmArmed) {
      armConfirm()
      return
    }
    setSubmitting(true)
    try {
      await api.post(`/batches/${batch.id}/produce`, { dimensions: [...selected] })
      showToast('success', `已进入生产队列：${preview?.content_items ?? 0} 条 ContentItem`)
      onSuccess()
      onClose()
    } catch (e) {
      const detail = e instanceof ApiError ? e.detail : '触发重生失败'
      if (e instanceof ApiError && e.status === 409) {
        showToast('warning', `该批次正在生产中：${detail}`)
      } else {
        showToast('error', detail)
      }
      setSubmitting(false)
    }
  }

  const isBlocked = batch.status === 'processing'
  // preview 失败时允许提交（后端会兜底校验），避免瞬时网络错误永久 block 用户
  const canSubmit = !isBlocked && selected.size > 0 && !submitting
    && (preview !== null || previewError !== null)

  const isAllMnemonic = useMemo(() => {
    return ALL_MNEMONIC_DIMS.every(d => selected.has(d)) && selected.size === ALL_MNEMONIC_DIMS.length
  }, [selected])

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm"
      onClick={() => { if (!submitting) onClose() }}
    >
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-labelledby="regen-modal-title"
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        onClick={e => e.stopPropagation()}
        className="bg-white w-full max-w-2xl rounded-[32px] shadow-2xl overflow-hidden flex flex-col"
      >
        {/* 头部 */}
        <div className="p-6 border-b border-slate-100 flex items-center justify-between bg-rose-50/50">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-rose-600 text-white rounded-xl flex items-center justify-center shadow-lg shadow-rose-200">
              <RefreshCw size={20} />
            </div>
            <div>
              <h3 id="regen-modal-title" className="font-bold text-xl text-slate-900">重新生产 · {batch.name}</h3>
              <p className="text-xs text-slate-500">共 {batch.total_words} 词 · 状态 {batch.status}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-full transition-colors">
            <X size={20} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* 一键按钮 */}
          <div className="flex flex-wrap gap-2">
            <button
              onClick={selectMnemonic}
              className={`px-3 py-1.5 text-xs font-bold rounded-full border transition-colors flex items-center gap-1.5 ${
                isAllMnemonic
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white text-blue-700 border-blue-200 hover:bg-blue-50'
              }`}
            >
              <Sparkles size={12} />
              助记 4 维度
            </button>
            <button onClick={selectAll} className="px-3 py-1.5 text-xs font-bold rounded-full border bg-white text-slate-700 border-slate-200 hover:bg-slate-50">
              全选（7 维）
            </button>
            <button onClick={clearAll} className="px-3 py-1.5 text-xs font-bold rounded-full border bg-white text-slate-500 border-slate-200 hover:bg-slate-50">
              清空
            </button>
          </div>

          {/* 维度多选 */}
          <DimGroup title="基础" dims={BASIC_REGENERATABLE_DIMS} selected={selected} onToggle={toggle} />
          <DimGroup title="助记" dims={ALL_MNEMONIC_DIMS} selected={selected} onToggle={toggle} />

          {/* 预览数字 */}
          <div className="p-4 rounded-2xl border border-slate-200 bg-slate-50">
            {previewLoading ? (
              <div className="flex items-center gap-2 text-slate-500 text-sm">
                <Loader2 size={14} className="animate-spin" />
                正在计算受影响项...
              </div>
            ) : previewError ? (
              <div className="space-y-1">
                <p className="text-sm text-rose-600">预览失败：{previewError}</p>
                <p className="text-xs text-slate-500">仍可提交，后端会对维度做完整校验</p>
              </div>
            ) : selected.size === 0 ? (
              <p className="text-sm text-slate-400">请至少选择一个维度</p>
            ) : preview ? (
              <div className="space-y-1.5 text-sm text-slate-700">
                <div>
                  将重置 <strong className="text-rose-700">{preview.distinct_words}</strong> 词 ×{' '}
                  <strong className="text-rose-700">{Object.keys(preview.by_dimension).length}</strong> 维度 ={' '}
                  <strong className="text-rose-700">{preview.content_items}</strong> 条 ContentItem
                </div>
                {preview.review_items > 0 && (
                  <div className="text-xs text-slate-500">
                    级联删除 {preview.review_items} 条审核记录
                  </div>
                )}
              </div>
            ) : null}
          </div>

          {/* 覆盖警告 */}
          <div className="p-4 rounded-2xl border border-amber-200 bg-amber-50 flex items-start gap-3">
            <AlertTriangle size={18} className="text-amber-600 shrink-0 mt-0.5" />
            <div className="text-xs text-amber-900 leading-relaxed">
              <strong>已审核通过的内容也会被覆盖。</strong>所选维度的所有 ContentItem 将清空内容并重新走生成 → 质检流水线。请确认 prompt 已升级到目标版本。
            </div>
          </div>

          {/* processing 时禁用提示 */}
          {isBlocked && (
            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-600">
              该批次正在生产中，需等当前生产完成后才能触发重生。
            </div>
          )}
        </div>

        {/* 底部按钮 */}
        <div className="p-6 border-t border-slate-100 bg-slate-50/50 flex justify-end gap-3">
          <button
            onClick={onClose}
            disabled={submitting}
            className="px-5 py-2.5 text-sm font-bold text-slate-600 hover:bg-slate-100 rounded-xl transition-colors disabled:opacity-50"
          >
            取消
          </button>
          <button
            onClick={submit}
            disabled={!canSubmit}
            className={`px-6 py-2.5 text-sm font-bold rounded-xl transition-all flex items-center gap-2 shadow-lg ${
              !canSubmit
                ? 'bg-slate-200 text-slate-400 cursor-not-allowed shadow-none'
                : confirmArmed
                  ? 'bg-rose-600 text-white hover:bg-rose-700 shadow-rose-200'
                  : 'bg-blue-600 text-white hover:bg-blue-700 shadow-blue-200'
            }`}
          >
            {submitting ? (
              <><Loader2 size={16} className="animate-spin" /> 提交中</>
            ) : confirmArmed ? (
              <>确认 — 将覆盖 {preview?.content_items ?? 0} 条</>
            ) : (
              <><RefreshCw size={16} /> 重新生产...</>
            )}
          </button>
        </div>
      </motion.div>
    </div>
  )
}

interface DimGroupProps {
  title: string
  dims: readonly RegenerableDim[]
  selected: Set<RegenerableDim>
  onToggle: (dim: RegenerableDim) => void
}

function DimGroup({ title, dims, selected, onToggle }: DimGroupProps) {
  return (
    <div>
      <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2">{title}</p>
      <div className="grid grid-cols-2 gap-2">
        {dims.map(dim => {
          const isOn = selected.has(dim)
          const Icon = isOn ? CheckSquare : Square
          return (
            <button
              key={dim}
              onClick={() => onToggle(dim)}
              className={`flex items-center gap-2 px-3 py-2.5 rounded-xl border text-sm transition-colors ${
                isOn
                  ? 'bg-blue-50 text-blue-900 border-blue-300'
                  : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
              }`}
            >
              <Icon size={16} className={isOn ? 'text-blue-600' : 'text-slate-400'} />
              <span className="font-medium">{DIMENSION_LABELS[dim] ?? dim}</span>
              <span className="ml-auto text-[10px] text-slate-400 font-mono">{dim}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
