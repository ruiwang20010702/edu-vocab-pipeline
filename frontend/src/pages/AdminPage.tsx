import { useState, useEffect } from 'react'
import { motion } from 'motion/react'
import { UserPlus, Loader2, Shield, Eye, ShieldCheck, Pencil, Check, X, Ban, UserCheck } from 'lucide-react'
import { api, ApiError } from '../lib/api'

interface User {
  id: number
  email: string
  name: string
  role: 'admin' | 'reviewer' | 'viewer'
  is_active: boolean
  created_at: string | null
  last_login_at: string | null
}

const ROLE_LABELS: Record<string, { label: string; icon: typeof Shield; color: string }> = {
  admin: { label: '管理员', icon: Shield, color: 'text-red-200 bg-red-400/20' },
  reviewer: { label: '审核员', icon: ShieldCheck, color: 'text-blue-200 bg-blue-400/20' },
  viewer: { label: '查看者', icon: Eye, color: 'text-green-200 bg-green-400/20' },
}

export default function AdminPage() {
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [formData, setFormData] = useState({ email: '', name: '', role: 'reviewer' })
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editData, setEditData] = useState({ name: '', role: '', is_active: true })

  const loadUsers = async () => {
    setLoading(true)
    try {
      const data = await api.get<User[]>('/admin/users')
      setUsers(data)
    } catch {
      setUsers([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadUsers() }, [])

  const handleCreate = async () => {
    if (!formData.email || !formData.name) {
      setError('请填写所有字段')
      return
    }
    setCreating(true)
    setError('')
    try {
      const user = await api.post<User>('/admin/users', formData)
      setUsers(prev => [...prev, user])
      setShowForm(false)
      setFormData({ email: '', name: '', role: 'reviewer' })
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : '创建失败')
    } finally {
      setCreating(false)
    }
  }

  const startEdit = (u: User) => {
    setEditingId(u.id)
    setEditData({ name: u.name, role: u.role, is_active: u.is_active })
  }

  const cancelEdit = () => setEditingId(null)

  const handleSaveEdit = async (userId: number) => {
    try {
      const updated = await api.patch<User>(`/admin/users/${userId}`, editData)
      setUsers(prev => prev.map(u => u.id === userId ? updated : u))
      setEditingId(null)
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : '更新失败')
    }
  }

  const toggleActive = async (u: User) => {
    try {
      const updated = await api.patch<User>(`/admin/users/${u.id}`, { is_active: !u.is_active })
      setUsers(prev => prev.map(x => x.id === u.id ? updated : x))
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : '操作失败')
    }
  }

  return (
    <div className="space-y-6">
      {/* 头部 */}
      <div className="flex items-center justify-between">
        <p className="text-white/60 text-sm">共 {users.length} 个用户</p>
        <button
          onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-2 px-5 py-2.5 bg-white/20 hover:bg-white/30 rounded-2xl text-white text-sm transition-all"
        >
          <UserPlus size={16} /> 创建用户
        </button>
      </div>

      {/* 创建表单 */}
      {showForm && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          className="glass-card rounded-3xl p-6"
        >
          <h3 className="text-white font-bold mb-4">创建新用户</h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="text-sm text-white/60 mb-1 block">邮箱</label>
              <input
                type="email"
                value={formData.email}
                onChange={e => setFormData(prev => ({ ...prev, email: e.target.value }))}
                className="w-full px-4 py-2.5 bg-white/10 border border-white/20 rounded-2xl text-white placeholder-white/40 focus:outline-none focus:border-white/50"
                placeholder="user@example.com"
              />
            </div>
            <div>
              <label className="text-sm text-white/60 mb-1 block">姓名</label>
              <input
                type="text"
                value={formData.name}
                onChange={e => setFormData(prev => ({ ...prev, name: e.target.value }))}
                className="w-full px-4 py-2.5 bg-white/10 border border-white/20 rounded-2xl text-white placeholder-white/40 focus:outline-none focus:border-white/50"
                placeholder="张三"
              />
            </div>
            <div>
              <label className="text-sm text-white/60 mb-1 block">角色</label>
              <select
                value={formData.role}
                onChange={e => setFormData(prev => ({ ...prev, role: e.target.value }))}
                className="w-full px-4 py-2.5 bg-white/10 border border-white/20 rounded-2xl text-white focus:outline-none focus:border-white/50 appearance-none"
              >
                <option value="admin">管理员</option>
                <option value="reviewer">审核员</option>
                <option value="viewer">查看者</option>
              </select>
            </div>
          </div>
          {error && <p className="text-red-200 text-sm mt-3 bg-red-500/20 rounded-xl py-2 px-3">{error}</p>}
          <div className="flex justify-end mt-4">
            <button
              onClick={handleCreate}
              disabled={creating}
              className="px-6 py-2.5 bg-white/25 hover:bg-white/35 text-white rounded-2xl text-sm transition-all disabled:opacity-50 flex items-center gap-2"
            >
              {creating && <Loader2 size={14} className="animate-spin" />}
              确认创建
            </button>
          </div>
        </motion.div>
      )}

      {/* 用户列表 */}
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="glass-card rounded-3xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-40">
            <Loader2 size={24} className="animate-spin text-white/50" />
          </div>
        ) : users.length === 0 ? (
          <div className="text-center text-white/50 py-10">暂无用户</div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-left text-sm font-medium text-white/60 px-6 py-4">姓名</th>
                <th className="text-left text-sm font-medium text-white/60 px-6 py-4">邮箱</th>
                <th className="text-left text-sm font-medium text-white/60 px-6 py-4">角色</th>
                <th className="text-left text-sm font-medium text-white/60 px-6 py-4">状态</th>
                <th className="text-left text-sm font-medium text-white/60 px-6 py-4">最近登录</th>
                <th className="text-left text-sm font-medium text-white/60 px-6 py-4">操作</th>
              </tr>
            </thead>
            <tbody>
              {users.map(u => {
                const roleInfo = ROLE_LABELS[u.role] ?? ROLE_LABELS.viewer
                const isEditing = editingId === u.id
                return (
                  <tr key={u.id} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                    <td className="px-6 py-3 text-white font-medium">
                      {isEditing ? (
                        <input
                          value={editData.name}
                          onChange={e => setEditData(prev => ({ ...prev, name: e.target.value }))}
                          className="w-full px-2 py-1 bg-white/10 border border-white/20 rounded-lg text-white text-sm focus:outline-none focus:border-white/50"
                        />
                      ) : u.name}
                    </td>
                    <td className="px-6 py-3 text-white/60 text-sm">{u.email}</td>
                    <td className="px-6 py-3">
                      {isEditing ? (
                        <select
                          value={editData.role}
                          onChange={e => setEditData(prev => ({ ...prev, role: e.target.value }))}
                          className="px-2 py-1 bg-white/10 border border-white/20 rounded-lg text-white text-sm focus:outline-none focus:border-white/50 appearance-none"
                        >
                          <option value="admin">管理员</option>
                          <option value="reviewer">审核员</option>
                          <option value="viewer">查看者</option>
                        </select>
                      ) : (
                        <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs ${roleInfo.color}`}>
                          <roleInfo.icon size={12} />
                          {roleInfo.label}
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-3">
                      {u.is_active ? (
                        <span className="px-2 py-1 rounded-lg text-xs bg-green-400/20 text-green-200">活跃</span>
                      ) : (
                        <span className="px-2 py-1 rounded-lg text-xs bg-red-400/20 text-red-200">停用</span>
                      )}
                    </td>
                    <td className="px-6 py-3 text-white/40 text-sm">
                      {u.last_login_at ? new Date(u.last_login_at).toLocaleDateString() : '从未登录'}
                    </td>
                    <td className="px-6 py-3">
                      {isEditing ? (
                        <div className="flex items-center gap-1">
                          <button onClick={() => handleSaveEdit(u.id)} className="p-1.5 hover:bg-green-400/20 rounded-lg text-green-200 transition-colors" title="保存">
                            <Check size={14} />
                          </button>
                          <button onClick={cancelEdit} className="p-1.5 hover:bg-white/10 rounded-lg text-white/40 transition-colors" title="取消">
                            <X size={14} />
                          </button>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1">
                          <button onClick={() => startEdit(u)} className="p-1.5 hover:bg-white/10 rounded-lg text-white/40 hover:text-white transition-colors" title="编辑">
                            <Pencil size={14} />
                          </button>
                          <button onClick={() => toggleActive(u)} className={`p-1.5 rounded-lg transition-colors ${u.is_active ? 'hover:bg-red-400/20 text-white/40 hover:text-red-200' : 'hover:bg-green-400/20 text-white/40 hover:text-green-200'}`} title={u.is_active ? '停用' : '启用'}>
                            {u.is_active ? <Ban size={14} /> : <UserCheck size={14} />}
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </motion.div>
    </div>
  )
}
