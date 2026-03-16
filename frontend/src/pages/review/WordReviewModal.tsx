import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import {
  Loader2, X, BookOpen, Layers, Volume2, Save, CheckCircle2, XCircle,
} from 'lucide-react'
import { api } from '../../lib/api'
import type { WordDetail } from '../../types'
import type { WordGroup } from './types'
import { ReviewEditProvider } from './ReviewContext'
import { ReviewDimensionCard, ContentDimensionCard, MnemonicReviewSection } from './ReviewDimensionCard'

function SyllableEditor({ syllable, wordId, onUpdated }: {
  syllable: { id: number; content: string }
  wordId: number
  onUpdated: (w: WordDetail) => void
}) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(syllable.content)
  const [saving, setSaving] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; text: string; issues?: Array<{ rule_id: string; message: string }> } | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => { setValue(syllable.content) }, [syllable.content])
  useEffect(() => { if (editing) inputRef.current?.focus() }, [editing])

  const cancel = () => { setValue(syllable.content); setEditing(false); setResult(null) }

  const save = async () => {
    if (!value.trim()) return
    setSaving(true)
    setResult(null)
    try {
      const res = await api.post<{ qc_passed: boolean; message: string; new_issues?: Array<{ rule_id: string; field: string; message: string }> }>(
        `/words/content-items/${syllable.id}/manual-edit`, { content: value.trim() },
      )
      setResult({ ok: res.qc_passed, text: res.message, issues: res.new_issues })
      if (res.qc_passed) {
        setTimeout(() => {
          setEditing(false)
          setResult(null)
          api.get<WordDetail>(`/words/${wordId}`)
            .then(data => onUpdated(data))
            .catch(() => {})
        }, 1500)
      }
    } catch (err: any) {
      setResult({ ok: false, text: err?.message ?? '保存失败' })
    } finally { setSaving(false) }
  }

  if (editing) {
    return (
      <div className="flex items-center gap-2 flex-wrap">
        <input
          ref={inputRef}
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') cancel() }}
          disabled={saving}
          className="text-sm text-slate-700 bg-white border border-blue-300 rounded-lg px-2 py-1 outline-none focus:ring-1 focus:ring-blue-400 w-32"
        />
        <button
          onClick={save}
          disabled={saving || !value.trim()}
          className="flex items-center gap-1 px-2.5 py-1 bg-blue-50 hover:bg-blue-100 text-blue-600 border border-blue-200 rounded-lg text-xs font-bold disabled:opacity-50"
        >
          {saving ? <Loader2 size={11} className="animate-spin" /> : <Save size={11} />} 保存并质检
        </button>
        <button onClick={cancel} className="text-xs text-slate-400 hover:text-slate-600 font-bold">取消</button>
        {result && (
          <div className="w-full">
            <span className={`flex items-center gap-1 text-xs font-bold ${result.ok ? 'text-emerald-600' : 'text-rose-500'}`}>
              {result.ok ? <CheckCircle2 size={11} /> : <XCircle size={11} />} {result.text}
            </span>
            {!result.ok && result.issues && result.issues.length > 0 && (
              <ul className="mt-1 space-y-0.5">
                {result.issues.map((iss, i) => (
                  <li key={i} className="text-xs text-rose-600/80 bg-rose-50/50 px-2 py-1 rounded-lg border border-rose-100/50">
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

  return (
    <span
      onDoubleClick={() => setEditing(true)}
      className="text-sm text-slate-500 cursor-pointer hover:text-blue-600 hover:bg-blue-50 px-1 rounded transition-colors"
      title="双击编辑音节"
    >
      {syllable.content}
    </span>
  )
}

export function WordReviewModal({
  group, onClose, onApprove, onRegenerate, onSaved, actionLoading, regenResult, resolvedIds,
}: {
  group: WordGroup
  onClose: () => void
  onApprove: (id: number) => void
  onRegenerate: (id: number) => void
  onSaved: () => void
  actionLoading: number | null
  regenResult: { id: number; passed: boolean; message: string } | null
  resolvedIds: Set<number>
}) {
  const [wordDetail, setWordDetail] = useState<WordDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(true)
  const [meaningIdx, setMeaningIdx] = useState(0)

  useEffect(() => {
    setDetailLoading(true)
    api.get<WordDetail>(`/words/${group.word_id}`)
      .then(data => setWordDetail(data))
      .catch(() => setWordDetail(null))
      .finally(() => setDetailLoading(false))
  }, [group.word_id])

  // F-M2: 重新生成完成后刷新 wordDetail，使用 AbortController 防并发
  useEffect(() => {
    if (!regenResult) return
    const controller = new AbortController()
    api.get<WordDetail>(`/words/${group.word_id}`, { signal: controller.signal })
      .then(data => setWordDetail(data))
      .catch(() => {})
    return () => controller.abort()
  }, [regenResult, group.word_id])

  const meanings = wordDetail?.meanings ?? []
  const currentMeaning = meanings[meaningIdx] ?? null

  // 当前义项下的审核项
  const currentItems = currentMeaning
    ? group.items.filter(i => i.meaning_id === currentMeaning.id)
    : group.items.filter(i => i.meaning_id === null)

  // 无义项关联的审核项（音标等词级维度）
  const wordLevelItems = group.items.filter(i => i.meaning_id == null)

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
        className="bg-white rounded-[32px] shadow-2xl border border-slate-100 w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {detailLoading ? (
          <div className="flex items-center justify-center py-24 gap-2 text-slate-400">
            <Loader2 className="animate-spin" size={24} />
            <span className="text-sm">加载中...</span>
          </div>
        ) : (
          <ReviewEditProvider
            wordId={group.word_id}
            onSaved={onSaved}
            onWordDetailUpdate={setWordDetail}
          >
            {/* Header: 单词 + 音标 */}
            <div className="p-6 pb-4 border-b border-slate-100 bg-gradient-to-r from-blue-50 to-white">
              <div className="flex items-start justify-between">
                <div>
                  <h2 className="text-3xl font-black text-slate-900 tracking-tight">{group.word_name}</h2>
                  {wordDetail?.phonetics?.[0] && (
                    <div className="flex items-center gap-3 mt-2">
                      <span className="font-mono text-sm text-blue-600">{wordDetail.phonetics[0].ipa}</span>
                      {(wordDetail.syllable?.content || wordDetail.phonetics[0].syllables) && (
                        <>
                          <span className="text-xs text-slate-400">·</span>
                          {wordDetail.syllable?.id ? (
                            <SyllableEditor syllable={{ id: wordDetail.syllable.id, content: wordDetail.syllable.content }} wordId={group.word_id} onUpdated={setWordDetail} />
                          ) : (
                            <span className="text-sm text-slate-500">{wordDetail.phonetics[0].syllables}</span>
                          )}
                        </>
                      )}
                    </div>
                  )}
                  <p className="text-xs text-slate-400 mt-1">{group.items.length} 个异常项待处理</p>
                </div>
                <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-xl transition-colors text-slate-400">
                  <X size={20} />
                </button>
              </div>
            </div>

            {/* 义项 Tab */}
            {meanings.length > 1 && (
              <div className="px-6 pt-4 flex items-center gap-1 bg-white">
                <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-2xl">
                  {meanings.map((m, idx) => {
                    const itemsForMeaning = group.items.filter(i => i.meaning_id === m.id)
                    return (
                      <button
                        key={m.id || idx}
                        onClick={() => setMeaningIdx(idx)}
                        className={`px-4 py-1.5 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 ${
                          meaningIdx === idx
                            ? 'bg-white text-blue-600 shadow-sm'
                            : 'text-slate-400 hover:text-slate-600'
                        }`}
                      >
                        义项 {idx + 1}
                        {itemsForMeaning.length > 0 && (
                          <span className="w-4 h-4 bg-rose-500 text-white text-[9px] rounded-full flex items-center justify-center">
                            {itemsForMeaning.length}
                          </span>
                        )}
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            {/* 内容区 */}
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {/* 义项头 */}
              {currentMeaning && (
                <div className="flex items-center gap-2">
                  <BookOpen size={14} className="text-blue-500" />
                  <span className="text-xs font-bold text-blue-600 uppercase bg-blue-50 px-2 py-0.5 rounded">{currentMeaning.pos}</span>
                  <span className="text-sm font-medium text-slate-900">{currentMeaning.definition}</span>
                </div>
              )}

              {/* 语块 — 完整展示 */}
              {currentMeaning && (() => {
                const chunk = currentMeaning.chunk
                const reviewItem = currentItems.find(i => i.content_item?.dimension === 'chunk')
                if (!chunk) return null
                return (
                  <ContentDimensionCard
                    icon={<Layers size={13} className="text-violet-400" />}
                    label="语块"
                    content={chunk}
                    reviewItem={reviewItem}
                    actionLoading={actionLoading}
                    resolvedIds={resolvedIds}
                    regenResult={regenResult}
                    onApprove={onApprove}
                    onRegenerate={onRegenerate}
                  />
                )
              })()}

              {/* 例句 — 完整展示 */}
              {currentMeaning && (() => {
                const sentence = currentMeaning.sentence
                const reviewItem = currentItems.find(i => i.content_item?.dimension === 'sentence')
                if (!sentence) return null
                return (
                  <ContentDimensionCard
                    icon={<Volume2 size={13} className="text-emerald-400" />}
                    label="例句"
                    content={sentence}
                    reviewItem={reviewItem}
                    actionLoading={actionLoading}
                    resolvedIds={resolvedIds}
                    regenResult={regenResult}
                    onApprove={onApprove}
                    onRegenerate={onRegenerate}
                  />
                )
              })()}

              {/* 助记 — 全部 4 种类型 */}
              {currentMeaning && (currentMeaning.mnemonics ?? []).length > 0 && (
                <MnemonicReviewSection
                  mnemonics={currentMeaning.mnemonics ?? []}
                  reviewItems={currentItems.filter(i => i.content_item?.dimension?.startsWith('mnemonic_'))}
                  actionLoading={actionLoading}
                  resolvedIds={resolvedIds}
                  regenResult={regenResult}
                  onApprove={onApprove}
                  onRegenerate={onRegenerate}
                  onRegenerated={() => {
                    api.get<WordDetail>(`/words/${group.word_id}`)
                      .then(data => setWordDetail(data))
                      .catch(() => {})
                  }}
                />
              )}

              {/* 词级维度（音节等） */}
              {wordLevelItems.length > 0 && meaningIdx === 0 && (
                <div className="space-y-3 pt-2 border-t border-slate-100">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">词级维度</p>
                  <AnimatePresence>
                  {wordLevelItems.map(item => (
                    <ReviewDimensionCard
                      key={item.id}
                      item={item}
                      isLoading={actionLoading === item.id}
                      isResolved={resolvedIds.has(item.id)}
                      regenResult={regenResult?.id === item.id ? regenResult : null}
                      onApprove={() => onApprove(item.id)}
                      onRegenerate={() => onRegenerate(item.id)}
                    />
                  ))}
                  </AnimatePresence>
                </div>
              )}
            </div>
          </ReviewEditProvider>
        )}
      </motion.div>
    </motion.div>
  )
}
