import { useState, useMemo, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import {
  RefreshCw, CheckCircle2, Loader2, AlertCircle, Save,
  Lightbulb, Ban,
} from 'lucide-react'
import { api } from '../../lib/api'
import type { ReviewItem } from '../../types'
import type { QcIssue } from './types'
import { DIMENSION_LABELS, STATUS_BADGE, ALL_MNEMONIC_DIMS } from './constants'
import { parseMnemonicJson, isMnemonicDim, buildMnemonicJson } from './utils'
import { QcResultBanner } from './QcResultBanner'
import { useReviewEdit } from './ReviewContext'

/* ===== 助记三字段编辑 ===== */

function MnemonicEditFields({
  formula, chant, script,
  onFormulaChange, onChantChange, onScriptChange,
  scriptRows = 3,
}: {
  formula: string; chant: string; script: string
  onFormulaChange: (v: string) => void
  onChantChange: (v: string) => void
  onScriptChange: (v: string) => void
  scriptRows?: number
}) {
  return (
    <>
      <div>
        <label className="text-[10px] font-bold text-slate-400 uppercase">核心公式</label>
        <textarea value={formula} onChange={e => onFormulaChange(e.target.value)} rows={2}
          className="w-full mt-1 px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm text-slate-900 focus:outline-none focus:border-blue-300 resize-none" />
      </div>
      <div>
        <label className="text-[10px] font-bold text-slate-400 uppercase">助记口诀</label>
        <textarea value={chant} onChange={e => onChantChange(e.target.value)} rows={2}
          className="w-full mt-1 px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm text-slate-900 focus:outline-none focus:border-blue-300 resize-none" />
      </div>
      <div>
        <label className="text-[10px] font-bold text-slate-400 uppercase">老师话术</label>
        <textarea value={script} onChange={e => onScriptChange(e.target.value)} rows={scriptRows}
          className="w-full mt-1 px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm text-slate-900 focus:outline-none focus:border-blue-300 resize-none" />
      </div>
    </>
  )
}

/* ===== 维度审核卡片 ===== */

export function ReviewDimensionCard({
  item, isLoading, isResolved, regenResult,
  onApprove, onRegenerate,
  embedded = false,
}: {
  item: ReviewItem
  isLoading: boolean
  isResolved: boolean
  regenResult: { passed: boolean; message: string } | null
  onApprove: () => void
  onRegenerate: () => void
  embedded?: boolean
}) {
  const dim = item.content_item?.dimension ?? ''
  const dimLabel = DIMENSION_LABELS[dim] ?? dim
  const retryCount = item.content_item?.retry_count ?? 0
  const atLimit = retryCount >= 3
  const content = item.content_item?.content ?? ''
  const issueMsg = item.issues?.[0]?.message ?? ''

  const actionButtons = (
    <div className="flex items-center gap-2 pt-1">
      <button onClick={onApprove} disabled={isLoading} className="py-1.5 px-3 bg-green-50 hover:bg-green-100 text-green-700 border border-green-200 rounded-xl text-[11px] font-bold transition-all disabled:opacity-50">
        通过
      </button>
      {!atLimit && (
        <button onClick={onRegenerate} disabled={isLoading}
          className="py-1.5 px-3 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-[11px] font-bold transition-all disabled:opacity-50 flex items-center gap-1">
          {isLoading ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
          AI 修复
        </button>
      )}
      <span className={`text-[10px] font-bold ml-auto ${atLimit ? 'text-rose-500' : 'text-slate-400'}`}>{retryCount}/3</span>
    </div>
  )

  const regenResultBanner = regenResult ? (
    <div className={`text-xs px-3 py-2 rounded-xl text-center font-medium ${regenResult.passed ? 'bg-green-50 text-green-600 border border-green-200' : 'bg-orange-50 text-orange-600 border border-orange-200'}`}>
      {regenResult.message}
    </div>
  ) : null

  // embedded 模式：只渲染操作按钮和编辑表单，不渲染外层卡片
  if (embedded) {
    return (
      <div className="relative space-y-2">
        <AnimatePresence>
          {isResolved && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="absolute inset-0 z-10 bg-gradient-to-br from-green-50/95 to-emerald-50/95 backdrop-blur-[2px] rounded-xl flex items-center justify-center"
            >
              <motion.div
                initial={{ scale: 0, rotate: -180 }}
                animate={{ scale: 1, rotate: 0 }}
                transition={{ type: 'spring', stiffness: 260, damping: 20 }}
                className="flex flex-col items-center gap-2"
              >
                <div className="w-10 h-10 bg-green-500 rounded-full flex items-center justify-center shadow-lg shadow-green-200">
                  <CheckCircle2 size={22} className="text-white" />
                </div>
                <span className="text-xs font-bold text-green-700">已通过</span>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
        {regenResultBanner}
        {actionButtons}
      </div>
    )
  }

  // 独立模式：完整卡片（用于词级维度等）
  return (
    <motion.div
      layout
      exit={{ opacity: 0, scale: 0.9, y: -10, transition: { duration: 0.4 } }}
      className={`relative bg-white rounded-2xl border p-4 space-y-3 transition-all overflow-hidden ${
        isResolved ? 'border-green-400 ring-2 ring-green-200' : isLoading ? 'border-blue-400 ring-1 ring-blue-200' : 'border-slate-200'
      }`}
    >
      <AnimatePresence>
        {isResolved && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="absolute inset-0 z-10 bg-gradient-to-br from-green-50/95 to-emerald-50/95 backdrop-blur-[2px] flex items-center justify-center"
          >
            <motion.div
              initial={{ scale: 0, rotate: -180 }}
              animate={{ scale: 1, rotate: 0 }}
              transition={{ type: 'spring', stiffness: 260, damping: 20 }}
              className="flex flex-col items-center gap-2"
            >
              <div className="w-12 h-12 bg-green-500 rounded-full flex items-center justify-center shadow-lg shadow-green-200">
                <CheckCircle2 size={28} className="text-white" />
              </div>
              <span className="text-sm font-bold text-green-700">已通过</span>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* 维度标题 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="px-2 py-0.5 bg-rose-50 text-rose-600 text-[10px] font-bold rounded-lg border border-rose-100">{dimLabel}</span>
          <span className={`text-[10px] font-bold ${atLimit ? 'text-rose-500' : 'text-slate-400'}`}>{retryCount}/3</span>
        </div>
        {issueMsg && <span className="flex items-center gap-1 text-[10px] text-rose-500"><AlertCircle size={10} /> 异常</span>}
      </div>

      {issueMsg && (
        <p className="text-xs text-rose-600/80 bg-rose-50/50 px-3 py-2 rounded-xl border border-rose-100/50 leading-relaxed">{issueMsg}</p>
      )}

      {/* 内容预览 */}
      {isMnemonicDim(dim) && parseMnemonicJson(content) ? (
        <div className="space-y-2 text-xs">
          <div className="flex items-start gap-2"><span className="shrink-0 px-1.5 py-0.5 bg-violet-50 text-violet-600 rounded font-bold text-[10px]">公式</span><span className="text-slate-700">{parseMnemonicJson(content)!.formula}</span></div>
          <div className="flex items-start gap-2"><span className="shrink-0 px-1.5 py-0.5 bg-amber-50 text-amber-600 rounded font-bold text-[10px]">口诀</span><span className="text-slate-700">{parseMnemonicJson(content)!.chant}</span></div>
          <div className="flex items-start gap-2"><span className="shrink-0 px-1.5 py-0.5 bg-emerald-50 text-emerald-600 rounded font-bold text-[10px]">话术</span><span className="text-slate-500 line-clamp-2">{parseMnemonicJson(content)!.script}</span></div>
        </div>
      ) : (
        <p className="text-xs text-slate-500 italic line-clamp-2">{content || '暂无内容'}</p>
      )}

      {regenResultBanner}
      {actionButtons}
    </motion.div>
  )
}

/* ===== 内容维度完整展示卡片（语块/例句） ===== */

export function ContentDimensionCard({
  icon, label, content, reviewItem,
  actionLoading, resolvedIds, regenResult,
  onApprove, onRegenerate,
}: {
  icon: React.ReactNode
  label: string
  content: any
  reviewItem?: ReviewItem
  actionLoading: number | null
  resolvedIds: Set<number>
  regenResult: { id: number; passed: boolean; message: string } | null
  onApprove: (id: number) => void
  onRegenerate: (id: number) => void
}) {
  const {
    directEditId, directEditContent, directEditContentCn, directEditSaving, directEditMsg,
    startDirectEdit, cancelDirectEdit, setDirectEditContent, setDirectEditContentCn, handleDirectEditSave,
  } = useReviewEdit()

  const status = content.qc_status ?? 'pending'
  const badge = STATUS_BADGE[status] ?? STATUS_BADGE.pending
  const hasIssue = !!reviewItem
  const isDirectEditing = directEditId === content.id

  return (
    <div className={`rounded-2xl border p-4 space-y-2 ${hasIssue ? 'bg-white border-rose-200' : 'bg-slate-50 border-slate-100'}`}>
      {/* 标题行 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {icon}
          <span className="text-xs font-bold text-slate-700">{label}</span>
        </div>
        <span className={`flex items-center gap-1 text-[10px] font-bold ${badge.text}`}>
          {status === 'approved' && <CheckCircle2 size={10} />}
          {hasIssue && <AlertCircle size={10} />}
          {badge.label}
        </span>
      </div>

      {/* 异常提示 */}
      {reviewItem?.issues?.[0]?.message && (
        <p className="text-xs text-rose-600/80 bg-rose-50/50 px-3 py-2 rounded-xl border border-rose-100/50 leading-relaxed">
          {reviewItem.issues[0].message}
        </p>
      )}

      {/* 内容 — 双击编辑 */}
      {isDirectEditing ? (
        <div className="space-y-2">
          <textarea value={directEditContent} onChange={e => setDirectEditContent(e.target.value)} rows={2}
            className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm text-slate-900 focus:outline-none focus:border-blue-300 resize-none" />
          <textarea value={directEditContentCn} onChange={e => setDirectEditContentCn(e.target.value)} rows={1} placeholder="中文翻译（可选）"
            className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-700 focus:outline-none focus:border-blue-300 resize-none placeholder:text-slate-400" />
          {directEditMsg && <QcResultBanner passed={directEditMsg.ok} message={directEditMsg.text} issues={directEditMsg.issues} />}
          <div className="flex items-center gap-2">
            <button onClick={() => handleDirectEditSave(content.id, { content: directEditContent, content_cn: directEditContentCn || undefined })} disabled={directEditSaving || !directEditContent.trim()}
              className="flex-1 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-600 border border-blue-200 rounded-xl text-xs font-bold flex items-center justify-center gap-1 disabled:opacity-50">
              {directEditSaving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />} 保存并质检
            </button>
            {directEditMsg && !directEditMsg.ok && (
              <button onClick={() => handleDirectEditSave(content.id, { content: directEditContent, content_cn: directEditContentCn || undefined, force_approve: true })} disabled={directEditSaving}
                className="py-1.5 px-3 bg-green-50 hover:bg-green-100 text-green-700 border border-green-200 rounded-xl text-xs font-bold flex items-center justify-center gap-1 disabled:opacity-50">
                <CheckCircle2 size={12} /> 强制通过
              </button>
            )}
            <button onClick={cancelDirectEdit} className="px-3 py-1.5 text-slate-400 hover:text-slate-600 text-xs font-bold">取消</button>
          </div>
        </div>
      ) : content.content && (
        <div
          className="space-y-1 rounded-lg px-1 -mx-1 cursor-text hover:bg-blue-50/50 transition-colors"
          onDoubleClick={() => startDirectEdit(content)}
          title="双击编辑"
        >
          <p className="text-sm text-slate-800">{content.content}</p>
          {content.content_cn && <p className="text-xs text-slate-500">{content.content_cn}</p>}
        </div>
      )}

      {/* 有审核项 → 展示审核按钮 */}
      {reviewItem && (
        <ReviewDimensionCard
          item={reviewItem}
          isLoading={actionLoading === reviewItem.id}
          isResolved={resolvedIds.has(reviewItem.id)}
          regenResult={regenResult?.id === reviewItem.id ? regenResult : null}
          onApprove={() => onApprove(reviewItem.id)}
          onRegenerate={() => onRegenerate(reviewItem.id)}
          embedded
        />
      )}
    </div>
  )
}

/* ===== 助记直接编辑表单 ===== */

function MnemonicDirectEditForm({
  mnId, initialContent, directEditSaving, directEditMsg,
  onDirectEditSave, onCancelDirectEdit,
}: {
  mnId: number
  initialContent: string
  directEditSaving: boolean
  directEditMsg: { ok: boolean; text: string; issues?: QcIssue[] } | null
  onDirectEditSave: (id: number, body: { content: string; force_approve?: boolean }) => void
  onCancelDirectEdit: () => void
}) {
  const parsed = parseMnemonicJson(initialContent)
  const [formula, setFormula] = useState(parsed?.formula ?? '')
  const [chant, setChant] = useState(parsed?.chant ?? '')
  const [script, setScript] = useState(parsed?.script ?? '')

  const handleSave = (forceApprove?: boolean) => {
    const content = buildMnemonicJson(formula, chant, script)
    onDirectEditSave(mnId, { content, force_approve: forceApprove })
  }

  return (
    <div className="space-y-2">
      <MnemonicEditFields
        formula={formula} chant={chant} script={script}
        onFormulaChange={setFormula} onChantChange={setChant} onScriptChange={setScript}
      />
      {directEditMsg && <QcResultBanner passed={directEditMsg.ok} message={directEditMsg.text} issues={directEditMsg.issues} />}
      <div className="flex items-center gap-2">
        <button onClick={() => handleSave()} disabled={directEditSaving || !formula.trim()}
          className="flex-1 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-600 border border-blue-200 rounded-xl text-xs font-bold flex items-center justify-center gap-1 disabled:opacity-50">
          {directEditSaving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />} 保存并质检
        </button>
        {directEditMsg && !directEditMsg.ok && (
          <button onClick={() => handleSave(true)} disabled={directEditSaving}
            className="py-1.5 px-3 bg-green-50 hover:bg-green-100 text-green-700 border border-green-200 rounded-xl text-xs font-bold flex items-center justify-center gap-1 disabled:opacity-50">
            <CheckCircle2 size={12} /> 强制通过
          </button>
        )}
        <button onClick={onCancelDirectEdit} className="px-3 py-1.5 text-slate-400 hover:text-slate-600 text-xs font-bold">取消</button>
      </div>
    </div>
  )
}

/* ===== 助记完整审核区块 ===== */

export function MnemonicReviewSection({
  mnemonics, reviewItems, actionLoading, resolvedIds, regenResult,
  onApprove, onRegenerate, onRegenerated,
}: {
  mnemonics: any[]
  reviewItems: ReviewItem[]
  actionLoading: number | null
  resolvedIds: Set<number>
  regenResult: { id: number; passed: boolean; message: string } | null
  onApprove: (id: number) => void
  onRegenerate: (id: number) => void
  onRegenerated: () => void
}) {
  const {
    directEditId, directEditSaving, directEditMsg,
    startDirectEdit, cancelDirectEdit, handleDirectEditSave,
  } = useReviewEdit()

  const mnMap = useMemo(() => {
    const m = new Map<string, any>()
    for (const mn of mnemonics) m.set(mn.dimension, mn)
    return m
  }, [mnemonics])

  const reviewMap = useMemo(() => {
    const m = new Map<string, ReviewItem>()
    for (const ri of reviewItems) {
      if (ri.content_item?.dimension) m.set(ri.content_item.dimension, ri)
    }
    return m
  }, [reviewItems])

  // 分类：有内容的（通过/异常）和 rejected 的
  const rejectedMns = ALL_MNEMONIC_DIMS
    .map(d => mnMap.get(d))
    .filter(mn => mn && (mn.qc_status === 'rejected' || !mn.content))

  return (
    <div className="space-y-3 pt-2 border-t border-slate-100">
      <div className="flex items-center gap-1.5">
        <Lightbulb size={13} className="text-yellow-500" />
        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">助记（4 种类型）</span>
      </div>

      {ALL_MNEMONIC_DIMS.map(dim => {
        const mn = mnMap.get(dim)
        if (!mn) return null
        const typeLabel = DIMENSION_LABELS[dim] ?? dim
        const isRejected = mn.qc_status === 'rejected' || !mn.content
        const reviewItem = reviewMap.get(dim)

        if (isRejected) return null // 下面统一渲染 rejected

        // 有内容的助记
        const parsed = parseMnemonicJson(mn.content)
        const status = mn.qc_status ?? 'pending'
        const badge = STATUS_BADGE[status] ?? STATUS_BADGE.pending
        const hasIssue = !!reviewItem

        return (
          <div key={dim} className={`rounded-2xl border p-4 space-y-2 ${hasIssue ? 'bg-white border-rose-200' : 'bg-yellow-50/60 border-yellow-100'}`}>
            <div className="flex items-center justify-between">
              <span className={`text-[10px] px-2 py-0.5 rounded-md font-bold ${hasIssue ? 'bg-rose-50 text-rose-600' : 'bg-yellow-100 text-yellow-700'}`}>{typeLabel}</span>
              <span className={`flex items-center gap-1 text-[10px] font-bold ${badge.text}`}>
                {status === 'approved' && <CheckCircle2 size={10} />}
                {hasIssue && <AlertCircle size={10} />}
                {badge.label}
              </span>
            </div>

            {/* 异常提示 */}
            {reviewItem?.issues?.[0]?.message && (
              <p className="text-xs text-rose-600/80 bg-rose-50/50 px-3 py-2 rounded-xl border border-rose-100/50 leading-relaxed">
                {reviewItem.issues[0].message}
              </p>
            )}

            {/* 助记内容 — 双击编辑 */}
            {directEditId === mn.id ? (
              <MnemonicDirectEditForm
                mnId={mn.id}
                initialContent={mn.content}
                directEditSaving={directEditSaving}
                directEditMsg={directEditMsg}
                onDirectEditSave={handleDirectEditSave}
                onCancelDirectEdit={cancelDirectEdit}
              />
            ) : parsed ? (
              <div
                className="space-y-2 text-xs rounded-lg px-1 -mx-1 cursor-text hover:bg-blue-50/50 transition-colors"
                onDoubleClick={() => startDirectEdit(mn)}
                title="双击编辑"
              >
                {parsed.formula && (
                  <div className="flex items-start gap-2">
                    <span className="shrink-0 px-1.5 py-0.5 bg-violet-50 text-violet-600 rounded font-bold text-[10px]">公式</span>
                    <span className="text-slate-700">{parsed.formula}</span>
                  </div>
                )}
                {parsed.chant && (
                  <div className="flex items-start gap-2">
                    <span className="shrink-0 px-1.5 py-0.5 bg-amber-50 text-amber-600 rounded font-bold text-[10px]">口诀</span>
                    <span className="text-slate-700">{parsed.chant}</span>
                  </div>
                )}
                {parsed.script && (
                  <div className="flex items-start gap-2">
                    <span className="shrink-0 px-1.5 py-0.5 bg-emerald-50 text-emerald-600 rounded font-bold text-[10px]">话术</span>
                    <span className="text-slate-500">{parsed.script}</span>
                  </div>
                )}
              </div>
            ) : (
              <p
                className="text-xs text-slate-500 italic rounded-lg px-1 -mx-1 cursor-text hover:bg-blue-50/50 transition-colors"
                onDoubleClick={() => startDirectEdit(mn)}
                title="双击编辑"
              >{mn.content || '暂无内容'}</p>
            )}

            {/* 有审核项 → 审核按钮 */}
            {reviewItem && (
              <ReviewDimensionCard
                item={reviewItem}
                isLoading={actionLoading === reviewItem.id}
                isResolved={resolvedIds.has(reviewItem.id)}
                regenResult={regenResult?.id === reviewItem.id ? regenResult : null}
                onApprove={() => onApprove(reviewItem.id)}
                onRegenerate={() => onRegenerate(reviewItem.id)}
                embedded
              />
            )}
          </div>
        )
      })}

      {/* Rejected 助记维度 */}
      {rejectedMns.length > 0 && (
        <RejectedMnemonicsSection mnemonics={rejectedMns} onRegenerated={onRegenerated} />
      )}
    </div>
  )
}

/* ===== 不适用助记维度区块 ===== */

function RejectedMnemonicsSection({ mnemonics, onRegenerated }: { mnemonics: any[]; onRegenerated: () => void }) {
  const [regenLoading, setRegenLoading] = useState<number | null>(null)
  const [regenMsg, setRegenMsg] = useState<{ id: number; ok: boolean; msg: string; issues?: QcIssue[] } | null>(null)
  const [regenCount, setRegenCount] = useState<Map<number, number>>(new Map())
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editFormula, setEditFormula] = useState('')
  const [editChant, setEditChant] = useState('')
  const [editScript, setEditScript] = useState('')
  const [saving, setSaving] = useState(false)

  // setTimeout 清理
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([])
  useEffect(() => {
    return () => { timersRef.current.forEach(clearTimeout) }
  }, [])
  const safeTimeout = (fn: () => void, ms: number) => {
    const id = setTimeout(() => {
      timersRef.current = timersRef.current.filter(t => t !== id)
      fn()
    }, ms)
    timersRef.current.push(id)
    return id
  }

  const handleRegenerate = async (mn: any) => {
    setRegenLoading(mn.id)
    setRegenMsg(null)
    const count = (regenCount.get(mn.id) ?? 0) + 1
    setRegenCount(new Map(regenCount).set(mn.id, count))
    try {
      const res = await api.post<{ success: boolean; qc_passed: boolean; message: string }>(`/words/content-items/${mn.id}/regenerate`)
      const msg = res.qc_passed ? res.message : `第 ${count} 次尝试：${res.message}`
      setRegenMsg({ id: mn.id, ok: res.qc_passed, msg })
      safeTimeout(() => { setRegenMsg(null); onRegenerated() }, 2000)
    } catch {
      setRegenMsg({ id: mn.id, ok: false, msg: `第 ${count} 次尝试：重新生成失败` })
      safeTimeout(() => setRegenMsg(null), 3000)
    } finally {
      setRegenLoading(null)
    }
  }

  const startEdit = (mn: any) => {
    setEditingId(mn.id)
    setEditFormula('')
    setEditChant('')
    setEditScript('')
    setRegenMsg(null)
  }

  const handleSaveEdit = async (mn: any, forceApprove?: boolean) => {
    setSaving(true)
    setRegenMsg(null)
    try {
      const content = JSON.stringify({ formula: editFormula, chant: editChant, script: editScript })
      const res = await api.post<{ success: boolean; qc_passed: boolean; message: string; new_issues?: QcIssue[] }>(`/words/content-items/${mn.id}/manual-edit`, { content, force_approve: forceApprove })
      setRegenMsg({ id: mn.id, ok: res.qc_passed, msg: res.message, issues: res.new_issues })
      if (res.qc_passed) {
        safeTimeout(() => { setRegenMsg(null); setEditingId(null); onRegenerated() }, 1500)
      }
      // QC 未通过 → 保持编辑框打开
    } catch {
      setRegenMsg({ id: mn.id, ok: false, msg: '保存失败' })
      safeTimeout(() => setRegenMsg(null), 3000)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-2 pt-2 border-t border-slate-100">
      <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest flex items-center gap-1">
        <Lightbulb size={11} /> 助记维度（不适用）
      </p>
      {mnemonics.map((mn: any) => {
        const typeLabel = DIMENSION_LABELS[mn.dimension] ?? mn.dimension
        const isEditing = editingId === mn.id

        if (isEditing) {
          return (
            <div key={mn.id} className="bg-white rounded-2xl p-4 border border-blue-200 space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-[10px] px-2 py-0.5 bg-blue-100 text-blue-600 rounded-md font-bold">{typeLabel}</span>
                <span className="text-[10px] text-slate-400">手动编辑</span>
              </div>
              <MnemonicEditFields
                formula={editFormula} chant={editChant} script={editScript}
                onFormulaChange={setEditFormula} onChantChange={setEditChant} onScriptChange={setEditScript}
              />
              {regenMsg && regenMsg.id === mn.id && <QcResultBanner passed={regenMsg.ok} message={regenMsg.msg} issues={regenMsg.issues} />}
              <div className="flex items-center gap-2">
                <button onClick={() => handleSaveEdit(mn)} disabled={saving || !editFormula.trim()}
                  className="flex-1 py-1.5 bg-yellow-50 hover:bg-yellow-100 text-yellow-700 border border-yellow-200 rounded-xl text-xs font-bold flex items-center justify-center gap-1 disabled:opacity-50">
                  {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                  保存并质检
                </button>
                {regenMsg && regenMsg.id === mn.id && !regenMsg.ok && (
                  <button onClick={() => handleSaveEdit(mn, true)} disabled={saving}
                    className="py-1.5 px-3 bg-green-50 hover:bg-green-100 text-green-700 border border-green-200 rounded-xl text-xs font-bold flex items-center justify-center gap-1 disabled:opacity-50">
                    <CheckCircle2 size={12} /> 强制通过
                  </button>
                )}
                <button onClick={() => setEditingId(null)} className="px-3 py-1.5 text-slate-400 hover:text-slate-600 text-xs font-bold">取消</button>
              </div>
            </div>
          )
        }

        return (
          <div key={mn.id} className="bg-slate-50 rounded-2xl p-3 border border-slate-100 flex items-center justify-between cursor-pointer" onDoubleClick={() => startEdit(mn)} title="双击编辑">
            <div className="flex items-center gap-2">
              <span className="text-[10px] px-2 py-0.5 bg-slate-200 text-slate-500 rounded-md font-bold">{typeLabel}</span>
              <span className="flex items-center gap-1 text-xs text-slate-400">
                <Ban size={11} /> 不适用
              </span>
            </div>
            <div className="flex items-center gap-2">
              {regenMsg && regenMsg.id === mn.id && (
                <span className={`text-[10px] font-medium ${regenMsg.ok ? 'text-green-600' : 'text-orange-600'}`}>{regenMsg.msg}</span>
              )}
              <button
                onClick={() => handleRegenerate(mn)}
                disabled={regenLoading === mn.id}
                className="flex items-center gap-1 px-2.5 py-1 bg-blue-50 hover:bg-blue-100 text-blue-600 border border-blue-200 rounded-lg text-[10px] font-bold transition-all disabled:opacity-50"
              >
                {regenLoading === mn.id ? <Loader2 size={10} className="animate-spin" /> : <RefreshCw size={10} />}
                重新生成
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
