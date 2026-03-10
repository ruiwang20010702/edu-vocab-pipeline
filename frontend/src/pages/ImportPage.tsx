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
  const [dragOver, setDragOver] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const f = e.dataTransfer.files[0]
    if (f) setFile(f)
  }, [])

  const [confirmOverwrite, setConfirmOverwrite] = useState(false)

  const doImport = async (force = false) => {
    setLoading(true)
    setError('')
    setConfirmOverwrite(false)
    try {
      const fd = new FormData()
      fd.append('file', file!)
      const params = new URLSearchParams({ batch_name: batchName.trim() })
      if (force) params.set('force', 'true')
      const res = await api.upload<{ batch_id: string }>(`/import?${params}`, fd)
      try {
        await api.post(`/batches/${res.batch_id}/produce`)
      } catch {
        // 生产触发失败不阻塞跳转，监控页会显示状态
      }
      onStartProduction(res.batch_id)
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setConfirmOverwrite(true)
      } else {
        setError(e instanceof ApiError ? e.detail : '导入失败')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleImport = async () => {
    if (!file) { setError('请选择文件'); return }
    if (!batchName.trim()) { setError('请输入批次名称'); return }
    await doImport(false)
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
        </div>

        {error && (
          <p className="text-red-200 text-sm text-center bg-red-500/20 rounded-xl py-2 mt-4">{error}</p>
        )}

        {confirmOverwrite && (
          <div className="mt-4 p-4 bg-amber-500/20 border border-amber-400/30 rounded-2xl">
            <p className="text-amber-100 text-sm text-center mb-3">
              批次「{batchName.trim()}」已存在，是否覆盖并重新导入？
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setConfirmOverwrite(false)}
                className="flex-1 py-2 bg-white/10 hover:bg-white/20 text-white/80 rounded-xl transition-all text-sm border border-white/20"
              >
                取消
              </button>
              <button
                onClick={() => doImport(true)}
                disabled={loading}
                className="flex-1 py-2 bg-amber-500/40 hover:bg-amber-500/60 text-white font-medium rounded-xl transition-all text-sm border border-amber-400/30"
              >
                确认覆盖
              </button>
            </div>
          </div>
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
