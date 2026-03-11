import { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react'
import { api, ApiError } from '../../lib/api'
import type { ReviewItem, WordDetail } from '../../types'
import type { QcIssue } from './types'

interface EditState {
  editingId: number | null
  editContent: string
  editContentCn: string
  saving: boolean
  editError: string
  editResult: { passed: boolean; message: string; issues?: QcIssue[] } | null
}

interface DirectEditState {
  directEditId: number | null
  directEditContent: string
  directEditContentCn: string
  directEditSaving: boolean
  directEditMsg: { ok: boolean; text: string; issues?: QcIssue[] } | null
}

interface ReviewEditContextValue extends EditState, DirectEditState {
  startEdit: (item: ReviewItem) => void
  cancelEdit: () => void
  setEditContent: (v: string) => void
  setEditContentCn: (v: string) => void
  handleSaveEdit: (reviewId: number, contentOverride?: string) => Promise<void>
  startDirectEdit: (ci: { id: number; content: string; content_cn?: string | null }) => void
  cancelDirectEdit: () => void
  setDirectEditContent: (v: string) => void
  setDirectEditContentCn: (v: string) => void
  handleDirectEditSave: (contentItemId: number, body: { content: string; content_cn?: string }) => Promise<void>
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

  // 审核项编辑
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editContent, setEditContent] = useState('')
  const [editContentCn, setEditContentCn] = useState('')
  const [saving, setSaving] = useState(false)
  const [editError, setEditError] = useState('')
  const [editResult, setEditResult] = useState<EditState['editResult']>(null)

  // 直接编辑
  const [directEditId, setDirectEditId] = useState<number | null>(null)
  const [directEditContent, setDirectEditContent] = useState('')
  const [directEditContentCn, setDirectEditContentCn] = useState('')
  const [directEditSaving, setDirectEditSaving] = useState(false)
  const [directEditMsg, setDirectEditMsg] = useState<DirectEditState['directEditMsg']>(null)

  const startEdit = useCallback((item: ReviewItem) => {
    setEditingId(item.id)
    setEditContent(item.content_item?.content ?? '')
    setEditContentCn(item.content_item?.content_cn ?? '')
    setEditError('')
    setEditResult(null)
  }, [])

  const cancelEdit = useCallback(() => {
    setEditingId(null)
    setEditError('')
    setEditResult(null)
  }, [])

  const handleSaveEdit = useCallback(async (reviewId: number, contentOverride?: string) => {
    setSaving(true)
    setEditError('')
    setEditResult(null)
    try {
      const res = await api.post<{
        success: boolean; qc_passed: boolean; message: string
        new_content: string | null; new_content_cn: string | null
        new_issues: QcIssue[]
      }>(`/reviews/${reviewId}/edit`, {
        content: contentOverride ?? editContent,
        content_cn: editContentCn || null,
      })
      if (res.qc_passed) {
        setEditResult({ passed: true, message: res.message })
        safeTimeout(() => { onSaved(); cancelEdit() }, 1500)
      } else {
        setEditResult({ passed: false, message: res.message, issues: res.new_issues })
        if (res.new_content !== null) setEditContent(res.new_content)
        if (res.new_content_cn !== null) setEditContentCn(res.new_content_cn)
        onSaved()
      }
    } catch (e) {
      setEditError(e instanceof ApiError ? e.detail : '保存失败')
    } finally {
      setSaving(false)
    }
  }, [editContent, editContentCn, onSaved, cancelEdit, safeTimeout])

  const startDirectEdit = useCallback((ci: { id: number; content: string; content_cn?: string | null }) => {
    setDirectEditId(ci.id)
    setDirectEditContent(ci.content)
    setDirectEditContentCn(ci.content_cn ?? '')
    setDirectEditMsg(null)
  }, [])

  const cancelDirectEdit = useCallback(() => {
    setDirectEditId(null)
    setDirectEditMsg(null)
  }, [])

  const handleDirectEditSave = useCallback(async (contentItemId: number, body: { content: string; content_cn?: string }) => {
    setDirectEditSaving(true)
    setDirectEditMsg(null)
    try {
      const res = await api.post<{ success: boolean; qc_passed: boolean; message: string; new_issues?: QcIssue[] }>(
        `/words/content-items/${contentItemId}/manual-edit`, body,
      )
      setDirectEditMsg({ ok: res.qc_passed, text: res.message, issues: res.new_issues })
      safeTimeout(() => {
        setDirectEditMsg(null)
        cancelDirectEdit()
        api.get<WordDetail>(`/words/${wordId}`)
          .then(data => onWordDetailUpdate(data))
          .catch(() => {})
        onSaved()
      }, 1500)
    } catch {
      setDirectEditMsg({ ok: false, text: '保存失败' })
      safeTimeout(() => setDirectEditMsg(null), 3000)
    } finally {
      setDirectEditSaving(false)
    }
  }, [wordId, onSaved, cancelDirectEdit, onWordDetailUpdate, safeTimeout])

  const value: ReviewEditContextValue = {
    editingId, editContent, editContentCn, saving, editError, editResult,
    directEditId, directEditContent, directEditContentCn, directEditSaving, directEditMsg,
    startEdit, cancelEdit, setEditContent, setEditContentCn, handleSaveEdit,
    startDirectEdit, cancelDirectEdit, setDirectEditContent, setDirectEditContentCn, handleDirectEditSave,
  }

  return (
    <ReviewEditContext.Provider value={value}>
      {children}
    </ReviewEditContext.Provider>
  )
}
