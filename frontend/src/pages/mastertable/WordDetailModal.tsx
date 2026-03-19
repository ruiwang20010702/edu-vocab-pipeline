import { useState, useEffect, useRef, useCallback } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import {
  X, Loader2, CheckCircle2, BookOpen, Lightbulb,
  Layers, Volume2, GraduationCap, Ban,
  ChevronDown, AlertCircle, Save, XCircle,
} from 'lucide-react'
import type { WordDetail, ContentItem } from '../../types'
import { api } from '../../lib/api'
import { ALL_MNEMONIC_DIMS, MNEMONIC_TYPE_LABELS } from '../review/constants'
import { parseMnemonic, buildMnemonicJson } from '../review/utils'

interface QcIssue { rule_id: string; field: string; message: string }
type EditResult = { ok: boolean; text: string; issues?: QcIssue[] } | null

/** 通用的保存+质检 hook */
function useContentEdit(itemId: number, onSaved: () => void) {
  const [saving, setSaving] = useState(false)
  const [result, setResult] = useState<EditResult>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  useEffect(() => () => {
    if (timerRef.current) clearTimeout(timerRef.current)
  }, [])

  const save = useCallback(async (
    body: { content: string; content_cn?: string; force_approve?: boolean },
    onClose: () => void,
  ) => {
    setSaving(true)
    setResult(null)
    try {
      const res = await api.post<{
        qc_passed: boolean; message: string
        new_issues?: QcIssue[]
      }>(
        `/words/content-items/${itemId}/manual-edit`, body,
      )
      setResult({ ok: res.qc_passed, text: res.message, issues: res.new_issues })
      if (res.qc_passed) {
        timerRef.current = setTimeout(() => {
          setResult(null)
          onClose()
          onSaved()
        }, 1500)
      }
    } catch (err: any) {
      setResult({ ok: false, text: err?.message ?? '保存失败' })
    } finally {
      setSaving(false)
    }
  }, [itemId, onSaved])

  return { saving, result, setResult, save }
}

/** 将质检问题按 content_item_id 归类到义项 */
function groupIssuesByMeaning(
  issues: WordDetail['issues'],
  meanings: WordDetail['meanings'],
  _syllable?: ContentItem,
) {
  const meaningIssuesMap = new Map<number, typeof issues>()
  const wordLevelIssues: typeof issues = []
  const itemToMeaning = new Map<number, number>()
  meanings.forEach((m, idx) => {
    if (m.chunk?.id) itemToMeaning.set(m.chunk.id, idx)
    if (m.sentence?.id) itemToMeaning.set(m.sentence.id, idx)
    for (const mn of (m.mnemonics ?? [])) {
      if (mn.id) itemToMeaning.set(mn.id, idx)
    }
  })
  for (const issue of issues) {
    const mIdx = itemToMeaning.get(issue.content_item_id)
    if (mIdx !== undefined) {
      const arr = meaningIssuesMap.get(mIdx) ?? []
      arr.push(issue)
      meaningIssuesMap.set(mIdx, arr)
    } else {
      wordLevelIssues.push(issue)
    }
  }
  return { meaningIssuesMap, wordLevelIssues }
}

/** 保存/强制通过按钮行 */
function SaveRow({ saving, result, onSave, onForceApprove, onCancel }: {
  saving: boolean
  result: EditResult
  onSave: () => void
  onForceApprove: () => void
  onCancel: () => void
}) {
  return (
    <div className="flex items-center gap-2 flex-wrap mt-2">
      <button
        onClick={onSave}
        disabled={saving}
        className="flex items-center gap-1 px-2.5 py-1 bg-blue-50 hover:bg-blue-100 text-blue-600 border border-blue-200 rounded-lg text-xs font-bold disabled:opacity-50"
      >
        {saving ? <Loader2 size={11} className="animate-spin" /> : <Save size={11} />} 保存并质检
      </button>
      {result && !result.ok && (
        <button
          onClick={onForceApprove}
          disabled={saving}
          className="flex items-center gap-1 px-2.5 py-1 bg-green-50 hover:bg-green-100 text-green-700 border border-green-200 rounded-lg text-xs font-bold disabled:opacity-50"
        >
          <CheckCircle2 size={11} /> 强制通过
        </button>
      )}
      <button onClick={onCancel} className="text-xs text-slate-400 hover:text-slate-600 font-bold">取消</button>
      {result && (
        <div className="w-full mt-1">
          <span className={`flex items-center gap-1 text-xs font-bold ${result.ok ? 'text-emerald-600' : 'text-rose-500'}`}>
            {result.ok ? <CheckCircle2 size={11} /> : <XCircle size={11} />} {result.text}
          </span>
          {!result.ok && result.issues && result.issues.length > 0 && (
            <ul className="mt-1 space-y-0.5">
              {result.issues.map((iss, i) => (
                <li key={i} className="text-xs text-rose-600/80 bg-rose-50/50 px-2.5 py-1.5 rounded-lg border border-rose-100/50">
                  <span className="font-bold text-rose-500">{iss.rule_id}</span> {iss.message}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

/** 可双击编辑的语块/例句 */
function EditableContentItem({
  item, label, icon, contentClass, hasCn, onSaved, editable = true,
}: {
  item: ContentItem
  label: string
  icon: React.ReactNode
  contentClass: string
  hasCn?: boolean
  onSaved: () => void
  editable?: boolean
}) {
  const [editing, setEditing] = useState(false)
  const [editContent, setEditContent] = useState(item.content)
  const [editContentCn, setEditContentCn] = useState(item.content_cn ?? '')
  const { saving, result, save } = useContentEdit(item.id, onSaved)

  useEffect(() => { setEditContent(item.content); setEditContentCn(item.content_cn ?? '') }, [item.content, item.content_cn])

  const cancel = () => { setEditContent(item.content); setEditContentCn(item.content_cn ?? ''); setEditing(false) }

  if (editing) {
    return (
      <div className="flex items-start gap-2">
        {icon}
        <div className="flex-1 space-y-1.5">
          <p className="text-[10px] font-bold text-slate-400 uppercase mb-0.5">{label}</p>
          <textarea
            value={editContent}
            onChange={e => setEditContent(e.target.value)}
            disabled={saving}
            rows={2}
            className="w-full text-sm bg-white border border-blue-300 rounded-lg px-2 py-1 outline-none focus:ring-1 focus:ring-blue-400 resize-none"
          />
          {hasCn && (
            <textarea
              value={editContentCn}
              onChange={e => setEditContentCn(e.target.value)}
              disabled={saving}
              rows={1}
              placeholder="中文翻译"
              className="w-full text-xs text-slate-500 bg-white border border-blue-200 rounded-lg px-2 py-1 outline-none focus:ring-1 focus:ring-blue-400 resize-none"
            />
          )}
          <SaveRow
            saving={saving}
            result={result}
            onSave={() => save({ content: editContent, content_cn: hasCn ? editContentCn : undefined }, cancel)}
            onForceApprove={() => save({ content: editContent, content_cn: hasCn ? editContentCn : undefined, force_approve: true }, cancel)}
            onCancel={cancel}
          />
        </div>
      </div>
    )
  }

  return (
    <div
      className={`flex items-start gap-2 rounded-lg px-1 -mx-1 transition-colors ${editable ? 'cursor-pointer hover:bg-blue-50/50' : ''}`}
      onDoubleClick={editable ? () => setEditing(true) : undefined}
      title={editable ? '双击编辑' : undefined}
    >
      {icon}
      <div className="flex-1">
        <p className="text-[10px] font-bold text-slate-400 uppercase mb-0.5">{label}</p>
        <p className={contentClass}>{item.content}</p>
        {hasCn && item.content_cn && <p className="text-xs text-slate-500 mt-0.5">{item.content_cn}</p>}
      </div>
    </div>
  )
}

function CollapsibleIssues({ issues, label }: { issues: WordDetail['issues']; label: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="pt-2 border-t border-slate-200/60">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-2 w-full text-left group"
      >
        <AlertCircle size={13} className="text-red-400 shrink-0" />
        <span className="text-[10px] font-bold text-red-400 uppercase">{label} ({issues.length})</span>
        <ChevronDown size={13} className={`text-slate-400 ml-auto transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="space-y-1 mt-2">
              {issues.map((issue, i) => (
                <div key={i} className="text-sm bg-red-50 text-red-600 border border-red-100 px-3 py-2 rounded-xl">
                  {issue.message}
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

/** 单条助记编辑器 */
function MnemonicItemEditor({ mn, onSaved, editable = true }: { mn: any; onSaved: () => void; editable?: boolean }) {
  const parsed = parseMnemonic(mn.content)
  const [editing, setEditing] = useState(false)
  const [formula, setFormula] = useState(parsed.formula)
  const [chant, setChant] = useState(parsed.chant)
  const [script, setScript] = useState(parsed.script)
  const { saving, result, save } = useContentEdit(mn.id, onSaved)

  useEffect(() => {
    const p = parseMnemonic(mn.content)
    setFormula(p.formula); setChant(p.chant); setScript(p.script)
  }, [mn.content])

  const cancel = () => {
    const p = parseMnemonic(mn.content)
    setFormula(p.formula); setChant(p.chant); setScript(p.script)
    setEditing(false)
  }

  const doSave = (force?: boolean) => {
    const content = buildMnemonicJson(formula, chant, script)
    save({ content, force_approve: force }, cancel)
  }

  if (editing) {
    return (
      <div className="space-y-2">
        <div>
          <p className="text-[10px] font-bold text-yellow-600/60 uppercase mb-0.5">核心公式</p>
          <input
            value={formula}
            onChange={e => setFormula(e.target.value)}
            disabled={saving}
            className="w-full text-sm font-mono bg-white border border-yellow-300 rounded-lg px-2 py-1 outline-none focus:ring-1 focus:ring-yellow-400"
          />
        </div>
        <div>
          <p className="text-[10px] font-bold text-yellow-600/60 uppercase mb-0.5">助记口诀</p>
          <textarea
            value={chant}
            onChange={e => setChant(e.target.value)}
            disabled={saving}
            rows={2}
            className="w-full text-sm bg-white border border-yellow-300 rounded-lg px-2 py-1 outline-none focus:ring-1 focus:ring-yellow-400 resize-none"
          />
        </div>
        <div>
          <p className="text-[10px] font-bold text-yellow-600/60 uppercase mb-0.5">老师话术</p>
          <textarea
            value={script}
            onChange={e => setScript(e.target.value)}
            disabled={saving}
            rows={3}
            className="w-full text-xs bg-white border border-yellow-300 rounded-lg px-2 py-1 outline-none focus:ring-1 focus:ring-yellow-400 resize-none"
          />
        </div>
        <SaveRow
          saving={saving}
          result={result}
          onSave={() => doSave()}
          onForceApprove={() => doSave(true)}
          onCancel={cancel}
        />
      </div>
    )
  }

  return (
    <div
      className={`space-y-2 rounded-lg p-1 -m-1 transition-colors ${editable ? 'cursor-pointer hover:bg-yellow-100/40' : ''}`}
      onDoubleClick={editable ? () => setEditing(true) : undefined}
      title={editable ? '双击编辑' : undefined}
    >
      {parsed.formula && (
        <div>
          <p className="text-[10px] font-bold text-yellow-600/60 uppercase mb-0.5">核心公式</p>
          <p className="text-sm font-mono font-bold text-yellow-800">{parsed.formula}</p>
        </div>
      )}
      {parsed.chant && (
        <div>
          <p className="text-[10px] font-bold text-yellow-600/60 uppercase mb-0.5">助记口诀</p>
          <p className="text-sm text-yellow-700">{parsed.chant}</p>
        </div>
      )}
      {parsed.script && (
        <div className="pt-2 border-t border-yellow-200/60">
          <p className="text-[10px] font-bold text-yellow-600/60 uppercase mb-0.5">老师话术</p>
          <p className="text-xs text-yellow-800/80 leading-relaxed">{parsed.script}</p>
        </div>
      )}
    </div>
  )
}

function MnemonicSection({ mnemonics, onSaved, editable = true }: { mnemonics: any[]; onSaved: () => void; editable?: boolean }) {
  const mnMap = new Map<string, any>()
  for (const mn of mnemonics) mnMap.set(mn.dimension, mn)

  return (
    <div className="space-y-2 pt-2 border-t border-slate-200/60">
      <div className="flex items-center gap-1.5">
        <Lightbulb size={13} className="text-yellow-500 shrink-0" />
        <span className="text-[10px] font-bold text-slate-400 uppercase">助记（4 种类型）</span>
      </div>
      {ALL_MNEMONIC_DIMS.map(dim => {
        const mn = mnMap.get(dim)
        const typeLabel = MNEMONIC_TYPE_LABELS[dim] ?? dim
        const isRejected = mn?.qc_status === 'rejected'
        const hasContent = mn?.content

        if (!mn) return null

        if (isRejected || !hasContent) {
          return (
            <div key={dim} className="bg-slate-50 rounded-xl p-3 border border-slate-100 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-[10px] px-2 py-0.5 bg-slate-200 text-slate-500 rounded-md font-bold">{typeLabel}</span>
                <span className="flex items-center gap-1 text-xs text-slate-400">
                  <Ban size={11} /> 不适用
                </span>
              </div>
            </div>
          )
        }

        return (
          <div key={dim} className="bg-yellow-50/60 rounded-xl p-3 border border-yellow-100">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] px-2 py-0.5 bg-yellow-100 text-yellow-700 rounded-md font-bold">{typeLabel}</span>
              <span className="text-[9px] text-emerald-500 font-bold flex items-center gap-1">
                <CheckCircle2 size={10} /> 已通过
              </span>
            </div>
            <MnemonicItemEditor mn={mn} onSaved={onSaved} editable={editable} />
          </div>
        )
      })}
    </div>
  )
}

function SyllableInlineEditor({ syllable, onSaved, editable = true }: { syllable: { id: number; content: string }; onSaved: () => void; editable?: boolean }) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(syllable.content)
  const { saving, result, save } = useContentEdit(syllable.id, onSaved)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => { setValue(syllable.content) }, [syllable.content])
  useEffect(() => { if (editing) inputRef.current?.focus() }, [editing])

  const cancel = () => { setValue(syllable.content); setEditing(false) }

  const doSave = (force?: boolean) => {
    if (!value.trim()) return
    save({ content: value.trim(), force_approve: force }, cancel)
  }

  if (editing) {
    return (
      <div className="flex items-center gap-2 flex-wrap">
        <input
          ref={inputRef}
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') doSave(); if (e.key === 'Escape') cancel() }}
          disabled={saving}
          className="text-sm text-slate-700 bg-white border border-blue-300 rounded-lg px-2 py-1 outline-none focus:ring-1 focus:ring-blue-400 w-32"
        />
        <SaveRow
          saving={saving}
          result={result}
          onSave={() => doSave()}
          onForceApprove={() => doSave(true)}
          onCancel={cancel}
        />
      </div>
    )
  }

  return (
    <span
      onDoubleClick={editable ? () => setEditing(true) : undefined}
      className={`text-sm text-slate-500 px-1 rounded transition-colors ${editable ? 'cursor-pointer hover:text-blue-600 hover:bg-blue-50' : ''}`}
      title={editable ? '双击编辑音节' : undefined}
    >
      {syllable.content}
    </span>
  )
}

export default function WordDetailModal({ word, loading, onClose, onWordUpdate, editable = true }: { word: WordDetail | null; loading: boolean; onClose: () => void; onWordUpdate?: (w: WordDetail) => void; editable?: boolean }) {
  const [meaningIdx, setMeaningIdx] = useState(0)
  const meanings = word?.meanings ?? []
  const currentMeaning = meanings[meaningIdx] ?? null

  const { meaningIssuesMap, wordLevelIssues } = word
    ? groupIssuesByMeaning(word.issues ?? [], meanings, word.syllable)
    : { meaningIssuesMap: new Map(), wordLevelIssues: [] }

  const refreshWord = useCallback(() => {
    if (!word) return
    api.get<WordDetail>(`/words/${word.id}`)
      .then(data => onWordUpdate?.(data))
      .catch(() => {})
  }, [word?.id, onWordUpdate])

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.95, y: 20 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.95, y: 20 }}
        className="bg-white w-full max-w-2xl max-h-[85vh] rounded-[28px] shadow-2xl overflow-hidden flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {loading ? (
          <div className="flex items-center justify-center py-24 gap-2 text-slate-400">
            <Loader2 className="animate-spin" size={24} />
            <span className="text-sm">加载中...</span>
          </div>
        ) : !word ? (
          <div className="text-center text-slate-400 py-10">加载失败</div>
        ) : (
          <>
            {/* 头部 */}
            <div className="p-6 pb-4 border-b border-slate-100 bg-gradient-to-r from-blue-50 to-white">
              <div className="flex items-start justify-between">
                <div>
                  <h2 className="text-3xl font-black text-slate-900 tracking-tight">{word.word}</h2>
                  <div className="flex items-center gap-3 mt-2">
                    {word.phonetics?.[0] && (
                      <>
                        <span className="font-mono text-sm text-blue-600">{word.phonetics[0].ipa}</span>
                        <span className="text-xs text-slate-400">·</span>
                        {word.syllable?.id ? (
                          <SyllableInlineEditor
                            syllable={{ id: word.syllable.id, content: word.syllable.content }}
                            onSaved={refreshWord}
                            editable={editable}
                          />
                        ) : (
                          <span className="text-sm text-slate-500">{word.phonetics[0].syllables}</span>
                        )}
                      </>
                    )}
                  </div>
                </div>
                <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-xl transition-colors text-slate-400">
                  <X size={20} />
                </button>
              </div>
            </div>

            {/* 内容 */}
            <div className="flex-1 overflow-y-auto p-6 space-y-5">
              {meanings.length > 1 && (
                <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-2xl w-fit">
                  {meanings.map((m, idx) => (
                    <button
                      key={m.id || idx}
                      onClick={() => setMeaningIdx(idx)}
                      className={`px-4 py-1.5 rounded-xl text-xs font-bold transition-all ${
                        meaningIdx === idx
                          ? 'bg-white text-blue-600 shadow-sm'
                          : 'text-slate-400 hover:text-slate-600'
                      }`}
                    >
                      义项 {idx + 1}
                    </button>
                  ))}
                </div>
              )}

              {currentMeaning && (() => {
                const m = currentMeaning
                return (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2">
                      <BookOpen size={15} className="text-blue-500" />
                      <span className="text-xs font-bold text-slate-400 uppercase">义项 {meaningIdx + 1}</span>
                    </div>
                    <div className="bg-slate-50 rounded-2xl p-4 space-y-3">
                      <div className="flex items-baseline gap-2">
                        <span className="text-xs font-bold text-blue-600 uppercase bg-blue-50 px-2 py-0.5 rounded">{m.pos}</span>
                        <span className="text-sm font-medium text-slate-900">{m.definition}</span>
                      </div>

                      {m.sources && m.sources.length > 0 && (
                        <div className="flex items-center gap-2 flex-wrap">
                          <GraduationCap size={13} className="text-slate-400 shrink-0" />
                          {m.sources.map((s: any, si: number) => (
                            <span key={si} className="text-[10px] px-2 py-0.5 bg-white border border-slate-200 rounded-md text-slate-500">{s.source_name}</span>
                          ))}
                        </div>
                      )}

                      {m.chunk && m.chunk.content && (
                        <EditableContentItem
                          item={m.chunk}
                          label="核心语块"
                          icon={<Layers size={13} className="text-violet-400 mt-0.5 shrink-0" />}
                          contentClass="text-sm text-violet-700 italic font-medium"
                          hasCn
                          onSaved={refreshWord}
                          editable={editable}
                        />
                      )}

                      {m.sentence && m.sentence.content && (
                        <EditableContentItem
                          item={m.sentence}
                          label="例句"
                          icon={<Volume2 size={13} className="text-emerald-400 mt-0.5 shrink-0" />}
                          contentClass="text-sm text-slate-800"
                          hasCn
                          onSaved={refreshWord}
                          editable={editable}
                        />
                      )}

                      {m.mnemonics && m.mnemonics.length > 0 && (
                        <MnemonicSection mnemonics={m.mnemonics} onSaved={refreshWord} editable={editable} />
                      )}

                      {(meaningIssuesMap.get(meaningIdx) ?? []).length > 0 && (
                        <CollapsibleIssues issues={meaningIssuesMap.get(meaningIdx)!} label={`义项 ${meaningIdx + 1} 质检问题`} />
                      )}
                    </div>
                  </div>
                )
              })()}

              {wordLevelIssues.length > 0 && (
                <CollapsibleIssues issues={wordLevelIssues} label="词级质检问题" />
              )}

              <div className="flex items-center gap-4 pt-2 text-[10px] text-slate-400 uppercase tracking-wider">
                <span>ID: {word.id}</span>
                <span>创建: {word.created_at ? new Date(word.created_at).toLocaleDateString() : '-'}</span>
              </div>
            </div>
          </>
        )}
      </motion.div>
    </motion.div>
  )
}
