import { useState, useCallback } from 'react'
import { motion } from 'motion/react'
import { Upload, FileUp, X, Loader2 } from 'lucide-react'
import { api, ApiError } from '../lib/api'

interface Props {
  onStartProduction: (batchId: string) => void
}

export default function ImportPage({ onStartProduction }: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [batchName, setBatchName] = useState('')
  const [model, setModel] = useState('gpt-4o-mini')
  const [dragOver, setDragOver] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const f = e.dataTransfer.files[0]
    if (f) setFile(f)
  }, [])

  const handleImport = async () => {
    if (!file) { setError('请选择文件'); return }
    if (!batchName.trim()) { setError('请输入批次名称'); return }

    setLoading(true)
    setError('')
    try {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('batch_name', batchName.trim())
      fd.append('model', model)
      const res = await api.upload<{ batch_id: string }>('/import', fd)
      // 导入成功后触发生产流水线
      try {
        await api.post(`/batches/${res.batch_id}/produce`)
      } catch {
        // 生产触发失败不阻塞跳转，监控页会显示状态
      }
      onStartProduction(res.batch_id)
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : '导入失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6 max-w-2xl mx-auto">
      {/* 上传区域 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-card rounded-3xl p-8"
      >
        <h2 className="text-lg font-bold text-white mb-6">词表导入</h2>

        {/* 拖拽上传 */}
        <div
          onDrop={handleDrop}
          onDragOver={e => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          className={`border-2 border-dashed rounded-2xl p-10 text-center transition-all cursor-pointer ${
            dragOver ? 'border-white/60 bg-white/10' : 'border-white/20 hover:border-white/40'
          }`}
          onClick={() => document.getElementById('file-input')?.click()}
        >
          <input
            id="file-input"
            type="file"
            accept=".xlsx,.xls,.csv,.json"
            className="hidden"
            onChange={e => { if (e.target.files?.[0]) setFile(e.target.files[0]) }}
          />
          {file ? (
            <div className="flex items-center justify-center gap-3">
              <FileUp size={24} className="text-white/70" />
              <span className="text-white font-medium">{file.name}</span>
              <button onClick={e => { e.stopPropagation(); setFile(null) }} className="text-white/40 hover:text-white/80">
                <X size={18} />
              </button>
            </div>
          ) : (
            <>
              <Upload size={40} className="mx-auto text-white/40 mb-3" />
              <p className="text-white/60">拖拽文件到此处，或点击选择</p>
              <p className="text-white/40 text-sm mt-1">支持 .xlsx, .csv, .json</p>
            </>
          )}
        </div>

        {/* 表单 */}
        <div className="mt-6 space-y-4">
          <div>
            <label className="text-sm text-white/60 mb-1 block">批次名称</label>
            <input
              type="text"
              placeholder="例：人教版七年级上册"
              value={batchName}
              onChange={e => setBatchName(e.target.value)}
              className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-2xl text-white placeholder-white/40 focus:outline-none focus:border-white/50 transition-all"
            />
          </div>
          <div>
            <label className="text-sm text-white/60 mb-1 block">AI 模型</label>
            <select
              value={model}
              onChange={e => setModel(e.target.value)}
              className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-2xl text-white focus:outline-none focus:border-white/50 transition-all appearance-none"
            >
              <option value="gpt-4o-mini">GPT-4o Mini（推荐）</option>
              <option value="gpt-4o">GPT-4o</option>
              <option value="claude-sonnet-4-20250514">Claude Sonnet</option>
            </select>
          </div>
        </div>

        {error && (
          <p className="text-red-200 text-sm text-center bg-red-500/20 rounded-xl py-2 mt-4">{error}</p>
        )}

        <button
          onClick={handleImport}
          disabled={loading}
          className="w-full mt-6 py-3 bg-white/25 hover:bg-white/35 text-white font-semibold rounded-2xl transition-all flex items-center justify-center gap-2 border border-white/30 disabled:opacity-50"
        >
          {loading ? <Loader2 size={18} className="animate-spin" /> : <Upload size={18} />}
          开始生产
        </button>
      </motion.div>
    </div>
  )
}
