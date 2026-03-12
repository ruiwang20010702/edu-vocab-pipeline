import { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react'
import { api } from '../../lib/api'
import type { WordDetail } from '../../types'
import type { QcIssue } from './types'

interface DirectEditState {
  directEditId: number | null
  directEditContent: string
  directEditContentCn: string
  directEditSaving: boolean
  directEditMsg: { ok: boolean; text: string; issues?: QcIssue[] } | null
}

interface ReviewEditContextValue extends DirectEditState {
  startDirectEdit: (ci: { id: number; content: string; content_cn?: string | null }) => void
  cancelDirectEdit: () => void
  setDirectEditContent: (v: string) => void
  setDirectEditContentCn: (v: string) => void
  handleDirectEditSave: (contentItemId: number, body: { content: string; content_cn?: string; force_approve?: boolean }) => Promise<void>
}

const ReviewEditContext = createContext<ReviewEditContextValue | null>(null)

export function useReviewEdit() {
  const ctx = useContext(ReviewEditContext)
  if (!ctx) throw new Error('useReviewEdit must be used within ReviewEditProvider')
  return ctx
}

export function ReviewEditProvider({
  wordId,
  onSaved,
  onWordDetailUpdate,
  children,
}: {
  wordId: number
  onSaved: () => void
  onWordDetailUpdate: (data: WordDetail) => void
  children: React.ReactNode
}) {
  // 定时器清理 + 卸载守卫
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([])
  const activeRef = useRef(true)
  useEffect(() => {
    return () => {
      activeRef.current = false
      timersRef.current.forEach(clearTimeout)
    }
  }, [])
  const safeTimeout = useCallback((fn: () => void, ms: number) => {
    const id = setTimeout(() => {
      timersRef.current = timersRef.current.filter(t => t !== id)
      if (!activeRef.current) return
      fn()
    }, ms)
    timersRef.current.push(id)
    return id
  }, [])

  // 用 ref 保存最新回调，避免闭包捕获过期引用
  const onSavedRef = useRef(onSaved)
  const onWordDetailUpdateRef = useRef(onWordDetailUpdate)
  useEffect(() => { onSavedRef.current = onSaved }, [onSaved])
  useEffect(() => { onWordDetailUpdateRef.current = onWordDetailUpdate }, [onWordDetailUpdate])

  // 刷新数据的稳定函数
  const refreshWordDetail = useCallback(() => {
    api.get<WordDetail>(`/words/${wordId}`)
      .then(data => onWordDetailUpdateRef.current(data))
      .catch(() => {})
    onSavedRef.current()
  }, [wordId])

  // 直接编辑（双击编辑）
  const directEditSavedRef = useRef(false)
  const [directEditId, setDirectEditId] = useState<number | null>(null)
  const [directEditContent, setDirectEditContent] = useState('')
  const [directEditContentCn, setDirectEditContentCn] = useState('')
  const [directEditSaving, setDirectEditSaving] = useState(false)
  const [directEditMsg, setDirectEditMsg] = useState<DirectEditState['directEditMsg']>(null)

  const startDirectEdit = useCallback((ci: { id: number; content: string; content_cn?: string | null }) => {
    directEditSavedRef.current = false
    setDirectEditId(ci.id)
    setDirectEditContent(ci.content)
    setDirectEditContentCn(ci.content_cn ?? '')
    setDirectEditMsg(null)
  }, [])

  const cancelDirectEdit = useCallback(() => {
    // 如果编辑期间有过成功保存，关闭时刷新数据
    if (directEditSavedRef.current) {
      directEditSavedRef.current = false
      refreshWordDetail()
    }
    setDirectEditId(null)
    setDirectEditMsg(null)
  }, [refreshWordDetail])

  const handleDirectEditSave = useCallback(async (contentItemId: number, body: { content: string; content_cn?: string; force_approve?: boolean }) => {
    setDirectEditSaving(true)
    setDirectEditMsg(null)
    try {
      const res = await api.post<{ success: boolean; qc_passed: boolean; message: string; new_issues?: QcIssue[] }>(
        `/words/content-items/${contentItemId}/manual-edit`, body,
      )
      setDirectEditMsg({ ok: res.qc_passed, text: res.message, issues: res.new_issues })
      if (res.qc_passed) {
        directEditSavedRef.current = true
        // QC 通过（含强制通过）→ 1.5 秒后自动关闭编辑、刷新数据
        safeTimeout(() => {
          setDirectEditMsg(null)
          setDirectEditId(null)
          refreshWordDetail()
        }, 1500)
      }
      // QC 未通过 → 保持编辑框打开，用户可继续修改或强制通过
    } catch {
      setDirectEditMsg({ ok: false, text: '保存失败' })
      safeTimeout(() => setDirectEditMsg(null), 3000)
    } finally {
      setDirectEditSaving(false)
    }
  }, [refreshWordDetail, safeTimeout])

  const value: ReviewEditContextValue = {
    directEditId, directEditContent, directEditContentCn, directEditSaving, directEditMsg,
    startDirectEdit, cancelDirectEdit, setDirectEditContent, setDirectEditContentCn, handleDirectEditSave,
  }

  return (
    <ReviewEditContext.Provider value={value}>
      {children}
    </ReviewEditContext.Provider>
  )
}
