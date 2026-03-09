import { useState } from 'react'
import {
  LayoutDashboard,
  FileUp,
  Activity,
  ShieldCheck,
  Database,
  Settings,
  Users,
  Menu,
  X,
  LogOut,
} from 'lucide-react'
import { motion, AnimatePresence } from 'motion/react'
import { getAuth, clearAuth, isAuthenticated } from './lib/auth'

import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import ImportPage from './pages/ImportPage'
import MonitoringPage from './pages/MonitoringPage'
import ReviewPage from './pages/ReviewPage'
import MasterTablePage from './pages/MasterTablePage'
import PromptPage from './pages/PromptPage'
import AdminPage from './pages/AdminPage'

type Page = 'dashboard' | 'import' | 'monitoring' | 'review' | 'master' | 'prompt' | 'admin'

export default function App() {
  const [authed, setAuthed] = useState(isAuthenticated())
  const [currentPage, setCurrentPage] = useState<Page>('dashboard')
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const [currentBatchId, setCurrentBatchId] = useState<string | null>(null)

  if (!authed) {
    return <LoginPage onLogin={() => setAuthed(true)} />
  }

  const auth = getAuth()

  const isAdmin = auth?.user_role === 'admin'

  const navItems: { id: Page; label: string; icon: typeof LayoutDashboard }[] = [
    { id: 'dashboard', label: '数据看板', icon: LayoutDashboard },
    { id: 'import', label: '词表导入', icon: FileUp },
    { id: 'monitoring', label: '生产监控', icon: Activity },
    { id: 'review', label: '质检审核', icon: ShieldCheck },
    { id: 'master', label: '总表管理', icon: Database },
    { id: 'prompt', label: 'Prompt管理', icon: Settings },
    ...(isAdmin ? [{ id: 'admin' as const, label: '用户管理', icon: Users }] : []),
  ]

  const handleLogout = () => {
    clearAuth()
    setAuthed(false)
  }

  const renderPage = () => {
    switch (currentPage) {
      case 'dashboard':
        return <DashboardPage onViewBatch={(batchId, view) => { setCurrentBatchId(batchId); setCurrentPage(view) }} />
      case 'import':
        return <ImportPage onStartProduction={(batchId) => { setCurrentBatchId(batchId); setCurrentPage('monitoring') }} />
      case 'monitoring':
        return <MonitoringPage batchId={currentBatchId} onGoToReview={() => setCurrentPage('review')} />
      case 'review':
        return <ReviewPage onBack={() => setCurrentPage('monitoring')} />
      case 'master':
        return <MasterTablePage />
      case 'prompt':
        return <PromptPage />
      case 'admin':
        return <AdminPage />
    }
  }

  return (
    <div className="flex h-screen w-full p-5 gap-5 overflow-hidden font-sans text-slate-900 relative z-10">
      {/* 侧边栏 */}
      <aside
        className={`${
          isSidebarOpen ? 'w-64' : 'w-24'
        } h-full glass-module rounded-[40px] flex flex-col transition-all duration-300 z-50 shrink-0`}
      >
        <div className="p-6 flex items-center gap-3">
          <div className="w-12 h-12 bg-white/30 backdrop-blur-md rounded-2xl flex items-center justify-center text-white font-extrabold text-xl shadow-lg cursor-pointer hover:scale-110 transition-transform hover:bg-white/40 border border-white/30">
            V
          </div>
          {isSidebarOpen && (
            <span className="font-bold text-lg tracking-tight text-white drop-shadow-sm">教育词汇系统</span>
          )}
        </div>

        <nav className="flex-1 px-4 py-2 space-y-2">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => setCurrentPage(item.id)}
              className={`w-full flex items-center gap-3 p-3 rounded-2xl transition-all duration-300 ${
                currentPage === item.id
                  ? 'text-white bg-white/30 backdrop-blur-md shadow-lg scale-[1.02]'
                  : 'text-white/70 hover:text-white hover:bg-white/20'
              }`}
            >
              <item.icon size={20} strokeWidth={currentPage === item.id ? 2.5 : 2} />
              {isSidebarOpen && <span className="font-medium">{item.label}</span>}
            </button>
          ))}
        </nav>

        {/* 底部：用户 + 折叠 */}
        <div className="p-4 space-y-2">
          {isSidebarOpen && auth && (
            <div className="flex items-center justify-between px-3 py-2">
              <span className="text-sm text-white/60 truncate">{auth.user_name}</span>
              <button onClick={handleLogout} className="text-white/40 hover:text-white/80 transition-colors" title="退出">
                <LogOut size={16} />
              </button>
            </div>
          )}
          <button
            onClick={() => setIsSidebarOpen(!isSidebarOpen)}
            className="w-full flex items-center justify-center p-2 rounded-2xl hover:bg-white/20 text-white/50 transition-all"
          >
            {isSidebarOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </aside>

      {/* 主内容 */}
      <main className="flex-1 flex flex-col min-w-0 h-full relative">
        <header className="h-20 shrink-0 flex items-center justify-between px-2">
          <h1 className="text-2xl font-bold text-white tracking-tight drop-shadow-sm">
            {navItems.find(i => i.id === currentPage)?.label}
          </h1>
        </header>

        <div className="flex-1 overflow-y-auto pr-2 pb-6 scroll-smooth">
          <div className="max-w-7xl mx-auto">
            <AnimatePresence mode="wait">
              <motion.div
                key={currentPage}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.2 }}
              >
                {renderPage()}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </main>
    </div>
  )
}
