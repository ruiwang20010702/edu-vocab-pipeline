import { useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { FileUp, X, Loader2, ArrowRight, History } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import BatchHistoryModal from '../components/BatchHistoryModal'

interface Props {
  onStartProduction: (batchId: string) => void
}

interface PreviewRow {
  word: string
  pos: string
  definition: string
  source: string
}

export default function ImportPage({ onStartProduction }: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [batchName, setBatchName] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [confirmOverwrite, setConfirmOverwrite] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [previewRows, setPreviewRows] = useState<PreviewRow[]>([])
  const [previewTotal, setPreviewTotal] = useState(0)
  const [previewLoading, setPreviewLoading] = useState(false)

  const loadPreview = async (f: File) => {
    setPreviewLoading(true)
    try {
      const fd = new FormData()
      fd.append('file', f)
      const res = await api.upload<{ rows: PreviewRow[]; total_count: number }>('/import/preview', fd)
      setPreviewRows(res.rows)
      setPreviewTotal(res.total_count)
    } catch {
      setPreviewRows([])
      setPreviewTotal(0)
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleFileSelect = (f: File) => {
    setFile(f)
    setError('')
    setConfirmOverwrite(false)
    loadPreview(f)
  }

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const f = e.dataTransfer.files[0]
    if (f) handleFileSelect(f)
  }, [])

  const clearFile = () => {
    setFile(null)
    setPreviewRows([])
    setPreviewTotal(0)
    setError('')
    setConfirmOverwrite(false)
  }

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
        // 生产触发失败不阻塞跳转
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
    await doImport(false)
  }

  return (
    <div className="space-y-8">
      {/* ===== 上传区域 ===== */}
      <section className="bg-white rounded-[32px] p-12 border border-white text-center space-y-6 shadow-sm relative overflow-hidden">
        <div className="absolute -right-20 -top-20 w-64 h-64 bg-slate-50/50 rounded-full blur-3xl" />
        <div className="absolute -left-20 -bottom-20 w-64 h-64 bg-slate-50/50 rounded-full blur-3xl" />

        <div className="relative z-10 space-y-6">
          <div className="w-20 h-20 bg-blue-50 rounded-full flex items-center justify-center mx-auto text-blue-600">
            <FileUp size={40} />
          </div>

          <div className="space-y-2">
            <h2 className="text-3xl font-bold tracking-tight text-slate-900">上传教材词表</h2>
            <p className="text-slate-500 max-w-md mx-auto">
              支持 Excel 格式，系统将自动进行义项合并与五维内容生产。
            </p>
          </div>

          {/* 拖拽上传 */}
          <div className="max-w-lg mx-auto">
            <div
              onDrop={handleDrop}
              onDragOver={e => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onClick={() => document.getElementById('file-input')?.click()}
              className={`border-2 border-dashed rounded-2xl p-8 cursor-pointer transition-all ${
                dragOver
                  ? 'border-blue-400 bg-blue-50/50'
                  : 'border-blue-200 hover:border-blue-400 hover:bg-blue-50/50'
              }`}
            >
              <input
                id="file-input"
                type="file"
                accept=".xlsx,.xls,.csv,.json"
                className="hidden"
                onChange={e => { if (e.target.files?.[0]) handleFileSelect(e.target.files[0]) }}
              />
              {file ? (
                <div className="flex items-center justify-center gap-3">
                  <span className="text-sm font-medium text-slate-600">{file.name}</span>
                  <button
                    onClick={e => { e.stopPropagation(); clearFile() }}
                    className="text-slate-400 hover:text-slate-600 transition-colors"
                  >
                    <X size={16} />
                  </button>
                </div>
              ) : (
                <span className="text-sm font-medium text-slate-400">
                  词表导入模板.xlsx
                </span>
              )}
            </div>
          </div>

          {/* 批次名称 */}
          <div className="max-w-lg mx-auto">
            <input
              type="text"
              value={batchName}
              onChange={e => setBatchName(e.target.value)}
              placeholder="为本次生产批次命名 (可选)..."
              className="w-full px-4 py-3 bg-white border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-400 transition-all"
            />
          </div>

          {/* 错误提示 */}
          {error && (
            <p className="text-red-600 text-sm text-center bg-red-50 border border-red-100 rounded-xl py-2 max-w-lg mx-auto">
              {error}
            </p>
          )}

          {/* 覆盖确认 */}
          {confirmOverwrite && (
            <div className="max-w-lg mx-auto p-4 bg-amber-50 border border-amber-200 rounded-2xl">
              <p className="text-amber-800 text-sm text-center mb-3">
                批次「{batchName.trim()}」已存在，是否覆盖并重新导入？
              </p>
              <div className="flex gap-3">
                <button
                  onClick={() => setConfirmOverwrite(false)}
                  className="flex-1 py-2 bg-white hover:bg-slate-50 text-slate-600 rounded-xl transition-all text-sm border border-slate-200"
                >
                  取消
                </button>
                <button
                  onClick={() => doImport(true)}
                  disabled={loading}
                  className="flex-1 py-2 bg-amber-500 hover:bg-amber-600 text-white font-medium rounded-xl transition-all text-sm"
                >
                  确认覆盖
                </button>
              </div>
            </div>
          )}

          {/* 操作栏 */}
          <div className="flex items-center justify-center gap-4">
            <button
              disabled={!file || loading}
              onClick={handleImport}
              className="bg-blue-600 text-white px-8 py-2.5 rounded-2xl font-bold flex items-center gap-2 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg shadow-blue-200 hover:-translate-y-0.5 active:scale-95"
            >
              {loading ? <Loader2 className="animate-spin" size={20} /> : <ArrowRight size={20} />}
              开始生产
            </button>
            <button
              onClick={() => setShowHistory(true)}
              className="px-4 py-2.5 bg-white border border-slate-200 rounded-xl text-sm font-medium hover:bg-slate-50 transition-all flex items-center gap-2"
            >
              <History size={18} />
              导入历史
            </button>
          </div>
        </div>
      </section>

      {/* ===== 导入历史弹窗 ===== */}
      <AnimatePresence>
        {showHistory && (
          <BatchHistoryModal
            onClose={() => setShowHistory(false)}
            onSelectBatch={(batchId) => {
              setShowHistory(false)
              onStartProduction(batchId)
            }}
          />
        )}
      </AnimatePresence>

      {/* ===== 上传预览 ===== */}
      <AnimatePresence>
        {(previewRows.length > 0 || previewLoading) && (
          <motion.section
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="bg-white rounded-[32px] border border-white overflow-hidden shadow-sm"
          >
            <div className="p-6 border-b border-slate-100 flex items-center justify-between">
              <h3 className="font-bold text-xl text-slate-900">
                上传预览 (前5条)
              </h3>
              {previewLoading ? (
                <Loader2 size={16} className="animate-spin text-blue-600" />
              ) : (
                <span className="text-sm text-slate-400">
                  共检测到 {previewTotal} 条词项
                </span>
              )}
            </div>
            {previewLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 size={24} className="animate-spin text-blue-600" />
              </div>
            ) : (
              <table className="w-full text-left">
                <thead className="bg-slate-50 text-slate-400 text-xs uppercase tracking-wider">
                  <tr>
                    <th className="px-6 py-4 font-semibold">单词</th>
                    <th className="px-6 py-4 font-semibold">词性</th>
                    <th className="px-6 py-4 font-semibold">中文释义</th>
                    <th className="px-6 py-4 font-semibold">教材来源</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {previewRows.map((item, i) => (
                    <tr key={i} className="hover:bg-blue-50/30 transition-colors">
                      <td className="px-6 py-4 font-medium text-slate-900">{item.word}</td>
                      <td className="px-6 py-4 text-slate-500">{item.pos}</td>
                      <td className="px-6 py-4 text-slate-700">{item.definition}</td>
                      <td className="px-6 py-4">
                        {item.source && (
                          <span className="px-2 py-1 bg-blue-50 text-blue-600 rounded text-[10px] font-bold border border-blue-200">
                            {item.source}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </motion.section>
        )}
      </AnimatePresence>
    </div>
  )
}
