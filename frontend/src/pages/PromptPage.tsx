import { useState, useEffect, useRef } from 'react'
import { Plus, Copy, Trash2, Save, X, Loader2, RotateCcw, Archive, ChevronDown, Check } from 'lucide-react'
import { api } from '../lib/api'

interface Prompt {
  id: number
  name: string
  category: 'generation' | 'qa'
  dimension: string
  model: string
  content: string
  is_active: boolean
}

type StatusTab = 'active' | 'archived'

const MODEL_OPTIONS = [
  { value: 'gpt-5.2', label: 'OpenAI / gpt-5.2' },
  { value: 'gemini-3-flash-preview', label: 'Gemini / gemini-3-flash-preview' },
  { value: 'doubao-seed-1-8-251228', label: '豆包 / doubao-seed-1-8-251228' },
]

function ModelSelect({ value, onChange, disabled }: { value: string; onChange: (v: string) => void; disabled?: boolean }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const current = MODEL_OPTIONS.find(m => m.value === value)

  if (disabled) {
    return (
      <div>
        <label className="text-sm text-white/60 mb-1 block">模型</label>
        <span className="text-sm text-white/70">{current?.label ?? value}</span>
      </div>
    )
  }

  return (
    <div className="relative" ref={ref}>
      <label className="text-sm text-white/60 mb-1 block">模型</label>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-4 py-2.5 bg-white/10 border border-white/20 rounded-2xl text-white text-sm hover:bg-white/15 transition-all min-w-[280px] justify-between"
      >
        <span>{current?.label ?? value}</span>
        <ChevronDown size={14} className={`text-white/40 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 w-full bg-white/10 backdrop-blur-xl border border-white/20 rounded-2xl overflow-hidden z-50 shadow-2xl">
          {MODEL_OPTIONS.map(m => (
            <button
              key={m.value}
              onClick={() => { onChange(m.value); setOpen(false) }}
              className={`w-full flex items-center gap-3 px-4 py-3 text-sm transition-all ${
                m.value === value
                  ? 'bg-white/15 text-white'
                  : 'text-white/70 hover:bg-white/10 hover:text-white'
              }`}
            >
              <Check size={14} className={m.value === value ? 'text-white' : 'text-transparent'} />
              {m.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export default function PromptPage() {
  const [prompts, setPrompts] = useState<Prompt[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [categoryTab, setCategoryTab] = useState<'generation' | 'qa'>('generation')
  const [statusTab, setStatusTab] = useState<StatusTab>('active')
  const [editDraft, setEditDraft] = useState<Prompt | null>(null)
  const [saving, setSaving] = useState(false)
  const [confirmArchive, setConfirmArchive] = useState<number | null>(null)

  const loadPrompts = async () => {
    setLoading(true)
    try {
      const isActive = statusTab === 'active'
      const data = await api.get<Prompt[]>(`/prompts?is_active=${isActive}`)
      setPrompts(data)
      if (!data.find(p => p.id === selectedId) && data.length > 0) {
        setSelectedId(data[0].id)
      } else if (data.length === 0) {
        setSelectedId(null)
      }
    } catch {
      setPrompts([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadPrompts() }, [statusTab])

  const selected = editDraft ?? prompts.find(p => p.id === selectedId) ?? null
  const filteredPrompts = prompts.filter(p => p.category === categoryTab)

  const handleSelect = (id: number) => {
    setSelectedId(id)
    setEditDraft(null)
  }

  const handleSave = async () => {
    if (!editDraft) return
    setSaving(true)
    try {
      const updated = await api.put<Prompt>(`/prompts/${editDraft.id}`, {
        name: editDraft.name,
        model: editDraft.model,
        content: editDraft.content,
        is_active: editDraft.is_active,
      })
      setPrompts(prev => prev.map(p => p.id === updated.id ? updated : p))
      setEditDraft(null)
    } catch { /* ignore */ } finally {
      setSaving(false)
    }
  }

  const handleCreate = async () => {
    try {
      const created = await api.post<Prompt>('/prompts', {
        name: '新 Prompt',
        category: categoryTab,
        dimension: categoryTab === 'generation' ? 'chunk' : 'chunk',
        model: 'gemini-3-flash-preview',
        content: '',
      })
      setPrompts(prev => [...prev, created])
      setSelectedId(created.id)
      setEditDraft(created)
    } catch { /* ignore */ }
  }

  const handleArchive = async (id: number) => {
    try {
      await api.delete(`/prompts/${id}`)
      setPrompts(prev => prev.filter(p => p.id !== id))
      if (selectedId === id) {
        setSelectedId(prompts.find(p => p.id !== id)?.id ?? null)
        setEditDraft(null)
      }
      setConfirmArchive(null)
    } catch { /* ignore */ }
  }

  const handleRestore = async (id: number) => {
    try {
      const restored = await api.post<Prompt>(`/prompts/${id}/restore`)
      setPrompts(prev => prev.filter(p => p.id !== id))
      if (selectedId === id) {
        setSelectedId(prompts.find(p => p.id !== id)?.id ?? null)
        setEditDraft(null)
      }
    } catch { /* ignore */ }
  }

  const handleDuplicate = async (p: Prompt) => {
    try {
      const created = await api.post<Prompt>('/prompts', {
        name: `${p.name} (副本)`,
        category: p.category,
        dimension: p.dimension,
        model: p.model,
        content: p.content,
      })
      // 如果当前在归档页，切换到正在使用页
      if (statusTab === 'archived') {
        setStatusTab('active')
      } else {
        setPrompts(prev => [...prev, created])
      }
      setSelectedId(created.id)
    } catch { /* ignore */ }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-140px)]">
        <Loader2 size={24} className="animate-spin text-white/50" />
      </div>
    )
  }

  return (
    <div className="flex gap-4 h-[calc(100vh-140px)]">
      {/* 左侧列表 */}
      <div className="w-72 shrink-0 glass-card rounded-3xl p-4 flex flex-col">
        {/* 状态切换：正在使用 / 归档 */}
        <div className="flex gap-1 mb-2">
          {([
            { key: 'active' as StatusTab, label: '正在使用' },
            { key: 'archived' as StatusTab, label: '归档' },
          ]).map(t => (
            <button
              key={t.key}
              onClick={() => { setStatusTab(t.key); setEditDraft(null) }}
              className={`flex-1 py-1.5 rounded-xl text-xs font-medium transition-all ${
                statusTab === t.key ? 'bg-white/20 text-white' : 'text-white/40 hover:bg-white/10'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* 分类 Tab */}
        <div className="flex gap-1 mb-3">
          {(['generation', 'qa'] as const).map(cat => (
            <button
              key={cat}
              onClick={() => setCategoryTab(cat)}
              className={`flex-1 py-2 rounded-xl text-sm font-medium transition-all ${
                categoryTab === cat ? 'bg-white/25 text-white' : 'text-white/50 hover:bg-white/10'
              }`}
            >
              {cat === 'generation' ? '生成' : '质检'}
            </button>
          ))}
        </div>

        {/* Prompt 列表 */}
        <div className="flex-1 overflow-y-auto space-y-1">
          {filteredPrompts.length === 0 ? (
            <div className="text-center text-white/30 text-sm py-8">
              {statusTab === 'archived' ? '暂无归档 Prompt' : '暂无 Prompt'}
            </div>
          ) : filteredPrompts.map(p => (
            <div
              key={p.id}
              onClick={() => handleSelect(p.id)}
              className={`p-3 rounded-2xl cursor-pointer transition-all group ${
                selectedId === p.id ? 'bg-white/20' : 'hover:bg-white/10'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-sm text-white font-medium truncate">{p.name}</span>
                <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  {statusTab === 'active' ? (
                    <>
                      <button onClick={e => { e.stopPropagation(); handleDuplicate(p) }} className="text-white/40 hover:text-white/80" title="复制">
                        <Copy size={14} />
                      </button>
                      <button onClick={e => { e.stopPropagation(); setConfirmArchive(p.id) }} className="text-white/40 hover:text-red-300" title="归档">
                        <Archive size={14} />
                      </button>
                    </>
                  ) : (
                    <>
                      <button onClick={e => { e.stopPropagation(); handleRestore(p.id) }} className="text-white/40 hover:text-green-300" title="复原">
                        <RotateCcw size={14} />
                      </button>
                      <button onClick={e => { e.stopPropagation(); handleDuplicate(p) }} className="text-white/40 hover:text-white/80" title="复制为新版本">
                        <Copy size={14} />
                      </button>
                    </>
                  )}
                </div>
              </div>
              <p className="text-xs text-white/40 mt-1">{p.model} · {p.dimension}</p>
            </div>
          ))}
        </div>

        {statusTab === 'active' && (
          <button
            onClick={handleCreate}
            className="mt-3 w-full py-2.5 bg-white/10 hover:bg-white/20 rounded-2xl text-white/60 hover:text-white text-sm flex items-center justify-center gap-1.5 transition-all"
          >
            <Plus size={16} /> 新建
          </button>
        )}
      </div>

      {/* 右侧编辑 */}
      <div className="flex-1 glass-card rounded-3xl p-6 flex flex-col">
        {selected ? (
          <>
            <div className="flex items-center justify-between mb-4">
              <input
                value={editDraft?.name ?? selected.name}
                onChange={e => setEditDraft({ ...(editDraft ?? selected), name: e.target.value })}
                className="text-xl font-bold text-white bg-transparent border-none focus:outline-none"
                readOnly={statusTab === 'archived'}
              />
              {editDraft && statusTab === 'active' && (
                <div className="flex gap-2">
                  <button onClick={() => setEditDraft(null)} className="p-2 text-white/40 hover:text-white/80"><X size={18} /></button>
                  <button
                    onClick={handleSave}
                    disabled={saving}
                    className="flex items-center gap-1 px-4 py-2 bg-white/20 hover:bg-white/30 rounded-xl text-white text-sm disabled:opacity-50"
                  >
                    {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} 保存
                  </button>
                </div>
              )}
            </div>

            <div className="mb-4 flex items-center gap-6">
              <ModelSelect
                value={editDraft?.model ?? selected.model}
                onChange={v => setEditDraft({ ...(editDraft ?? selected), model: v })}
                disabled={statusTab === 'archived'}
              />
              <div>
                <label className="text-sm text-white/60 mb-1 block">维度</label>
                <span className="text-sm text-white/70">{selected.dimension}</span>
              </div>
            </div>

            <div className="flex-1 flex flex-col">
              <label className="text-sm text-white/60 mb-1">Prompt 内容</label>
              <textarea
                value={editDraft?.content ?? selected.content}
                onChange={e => setEditDraft({ ...(editDraft ?? selected), content: e.target.value })}
                className="flex-1 px-4 py-3 bg-white/10 border border-white/20 rounded-2xl text-white placeholder-white/40 focus:outline-none focus:border-white/50 transition-all resize-none font-mono text-sm leading-relaxed"
                placeholder="输入 Prompt 内容..."
                readOnly={statusTab === 'archived'}
              />
            </div>
          </>
        ) : (
          <div className="flex items-center justify-center h-full text-white/40">
            选择一个 Prompt 开始编辑
          </div>
        )}
      </div>

      {/* 归档确认弹窗 */}
      {confirmArchive !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" onClick={() => setConfirmArchive(null)}>
          <div className="glass-card rounded-3xl p-6 w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-bold text-white mb-2">确认归档</h3>
            <p className="text-sm text-white/60 mb-6">
              归档后此 Prompt 将不再用于生产和质检。你可以随时在「归档」中复原。
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setConfirmArchive(null)}
                className="flex-1 py-2.5 bg-white/10 hover:bg-white/20 rounded-2xl text-white/70 text-sm transition-all"
              >
                取消
              </button>
              <button
                onClick={() => handleArchive(confirmArchive)}
                className="flex-1 py-2.5 bg-red-500/20 hover:bg-red-500/30 text-red-200 rounded-2xl text-sm font-medium transition-all"
              >
                确认归档
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
