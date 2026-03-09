import { useState } from 'react'
import { Plus, Copy, Trash2, Save, X } from 'lucide-react'

interface Prompt {
  id: string
  name: string
  category: 'generation' | 'qa'
  model: string
  content: string
}

const STORAGE_KEY = 'vocab_prompts'

function loadPrompts(): Prompt[] {
  const raw = localStorage.getItem(STORAGE_KEY)
  if (raw) {
    try { return JSON.parse(raw) } catch { /* fallthrough */ }
  }
  return defaultPrompts()
}

function savePrompts(prompts: Prompt[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(prompts))
}

function defaultPrompts(): Prompt[] {
  return [
    { id: '1', name: '语块生成', category: 'generation', model: 'gpt-4o-mini', content: '请为单词 {word} 的义项「{pos} {definition}」生成一个常用语块...' },
    { id: '2', name: '例句生成', category: 'generation', model: 'gpt-4o-mini', content: '请为单词 {word} 的义项「{pos} {definition}」生成一个例句...' },
    { id: '3', name: '助记生成', category: 'generation', model: 'gpt-4o-mini', content: '请为单词 {word} 生成助记法...' },
    { id: '4', name: '语块质检', category: 'qa', model: 'gpt-4o-mini', content: '请检查以下语块是否符合标准...' },
    { id: '5', name: '例句质检', category: 'qa', model: 'gpt-4o-mini', content: '请检查以下例句是否符合标准...' },
  ]
}

export default function PromptPage() {
  const [prompts, setPrompts] = useState<Prompt[]>(loadPrompts)
  const [selectedId, setSelectedId] = useState<string | null>(prompts[0]?.id ?? null)
  const [categoryTab, setCategoryTab] = useState<'generation' | 'qa'>('generation')
  const [editDraft, setEditDraft] = useState<Prompt | null>(null)

  const selected = editDraft ?? prompts.find(p => p.id === selectedId) ?? null

  const filteredPrompts = prompts.filter(p => p.category === categoryTab)

  const handleSelect = (id: string) => {
    setSelectedId(id)
    setEditDraft(null)
  }

  const handleSave = () => {
    if (!editDraft) return
    const updated = prompts.map(p => p.id === editDraft.id ? editDraft : p)
    setPrompts(updated)
    savePrompts(updated)
    setEditDraft(null)
  }

  const handleCreate = () => {
    const newPrompt: Prompt = {
      id: Date.now().toString(),
      name: '新 Prompt',
      category: categoryTab,
      model: 'gpt-4o-mini',
      content: '',
    }
    const updated = [...prompts, newPrompt]
    setPrompts(updated)
    savePrompts(updated)
    setSelectedId(newPrompt.id)
    setEditDraft(newPrompt)
  }

  const handleDelete = (id: string) => {
    const updated = prompts.filter(p => p.id !== id)
    setPrompts(updated)
    savePrompts(updated)
    if (selectedId === id) {
      setSelectedId(updated[0]?.id ?? null)
      setEditDraft(null)
    }
  }

  const handleDuplicate = (p: Prompt) => {
    const dup: Prompt = { ...p, id: Date.now().toString(), name: `${p.name} (副本)` }
    const updated = [...prompts, dup]
    setPrompts(updated)
    savePrompts(updated)
    setSelectedId(dup.id)
  }

  return (
    <div className="flex gap-4 h-[calc(100vh-140px)]">
      {/* 左侧列表 */}
      <div className="w-72 shrink-0 glass-card rounded-3xl p-4 flex flex-col">
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
          {filteredPrompts.map(p => (
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
                  <button onClick={e => { e.stopPropagation(); handleDuplicate(p) }} className="text-white/40 hover:text-white/80">
                    <Copy size={14} />
                  </button>
                  <button onClick={e => { e.stopPropagation(); handleDelete(p.id) }} className="text-white/40 hover:text-red-300">
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
              <p className="text-xs text-white/40 mt-1">{p.model}</p>
            </div>
          ))}
        </div>

        <button
          onClick={handleCreate}
          className="mt-3 w-full py-2.5 bg-white/10 hover:bg-white/20 rounded-2xl text-white/60 hover:text-white text-sm flex items-center justify-center gap-1.5 transition-all"
        >
          <Plus size={16} /> 新建
        </button>
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
              />
              {editDraft && (
                <div className="flex gap-2">
                  <button onClick={() => setEditDraft(null)} className="p-2 text-white/40 hover:text-white/80"><X size={18} /></button>
                  <button onClick={handleSave} className="flex items-center gap-1 px-4 py-2 bg-white/20 hover:bg-white/30 rounded-xl text-white text-sm">
                    <Save size={14} /> 保存
                  </button>
                </div>
              )}
            </div>

            <div className="mb-4">
              <label className="text-sm text-white/60 mb-1 block">模型</label>
              <select
                value={editDraft?.model ?? selected.model}
                onChange={e => setEditDraft({ ...(editDraft ?? selected), model: e.target.value })}
                className="px-4 py-2.5 bg-white/10 border border-white/20 rounded-2xl text-white focus:outline-none focus:border-white/50 transition-all appearance-none"
              >
                <option value="gpt-4o-mini">GPT-4o Mini</option>
                <option value="gpt-4o">GPT-4o</option>
                <option value="claude-sonnet-4-20250514">Claude Sonnet</option>
              </select>
            </div>

            <div className="flex-1 flex flex-col">
              <label className="text-sm text-white/60 mb-1">Prompt 内容</label>
              <textarea
                value={editDraft?.content ?? selected.content}
                onChange={e => setEditDraft({ ...(editDraft ?? selected), content: e.target.value })}
                className="flex-1 px-4 py-3 bg-white/10 border border-white/20 rounded-2xl text-white placeholder-white/40 focus:outline-none focus:border-white/50 transition-all resize-none font-mono text-sm leading-relaxed"
                placeholder="输入 Prompt 内容..."
              />
            </div>
          </>
        ) : (
          <div className="flex items-center justify-center h-full text-white/40">
            选择一个 Prompt 开始编辑
          </div>
        )}
      </div>
    </div>
  )
}
