import { useState, useCallback, createContext, useContext } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { XCircle, CheckCircle2, AlertTriangle, X } from 'lucide-react'

type ToastType = 'error' | 'success' | 'warning'

interface ToastItem {
  id: number
  type: ToastType
  message: string
}

interface ToastContextType {
  showToast: (type: ToastType, message: string) => void
}

const ToastContext = createContext<ToastContextType>({ showToast: () => {} })

export function useToast() {
  return useContext(ToastContext)
}

let _nextId = 0

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const showToast = useCallback((type: ToastType, message: string) => {
    const id = ++_nextId
    setToasts(prev => [...prev, { id, type, message }])
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id))
    }, 4000)
  }, [])

  const dismiss = useCallback((id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div className="fixed bottom-6 right-6 z-[9999] flex flex-col gap-2 pointer-events-none">
        <AnimatePresence>
          {toasts.map(t => (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, y: 20, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 10, scale: 0.95 }}
              className={`pointer-events-auto flex items-center gap-2 px-4 py-3 rounded-xl shadow-lg text-sm font-medium max-w-sm ${
                t.type === 'error' ? 'bg-red-600 text-white' :
                t.type === 'success' ? 'bg-emerald-600 text-white' :
                'bg-amber-500 text-white'
              }`}
            >
              {t.type === 'error' && <XCircle size={16} className="shrink-0" />}
              {t.type === 'success' && <CheckCircle2 size={16} className="shrink-0" />}
              {t.type === 'warning' && <AlertTriangle size={16} className="shrink-0" />}
              <span className="flex-1">{t.message}</span>
              <button onClick={() => dismiss(t.id)} className="shrink-0 p-0.5 hover:bg-white/20 rounded transition-colors">
                <X size={14} />
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  )
}
