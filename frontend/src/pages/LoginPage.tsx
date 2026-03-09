import { useState } from 'react'
import { motion } from 'motion/react'
import { Mail, KeyRound, Loader2 } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { setAuth } from '../lib/auth'
import type { AuthUser } from '../types'

interface Props {
  onLogin: () => void
}

export default function LoginPage({ onLogin }: Props) {
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [step, setStep] = useState<'email' | 'code'>('email')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [countdown, setCountdown] = useState(0)

  const startCountdown = () => {
    setCountdown(60)
    const timer = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) { clearInterval(timer); return 0 }
        return prev - 1
      })
    }, 1000)
  }

  const handleSendCode = async () => {
    if (!email.trim()) { setError('请输入邮箱'); return }
    setLoading(true)
    setError('')
    try {
      await api.post('/auth/send-code', { email: email.trim() })
      setStep('code')
      startCountdown()
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : '发送失败')
    } finally {
      setLoading(false)
    }
  }

  const handleVerify = async () => {
    if (!code.trim()) { setError('请输入验证码'); return }
    setLoading(true)
    setError('')
    try {
      const user = await api.post<AuthUser>('/auth/verify', {
        email: email.trim(),
        code: code.trim(),
      })
      setAuth(user)
      onLogin()
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : '验证失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex items-center justify-center h-screen w-full">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="glass-card rounded-[32px] p-10 w-full max-w-md"
      >
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-16 h-16 bg-white/30 backdrop-blur-md rounded-3xl flex items-center justify-center text-white font-extrabold text-3xl shadow-lg border border-white/30 mb-4">
            V
          </div>
          <h1 className="text-2xl font-bold text-white drop-shadow-sm">教育词汇生产系统</h1>
          <p className="text-white/60 text-sm mt-1">邮箱验证码登录</p>
        </div>

        {/* 表单 */}
        <div className="space-y-4">
          {/* 邮箱 */}
          <div className="relative">
            <Mail className="absolute left-4 top-1/2 -translate-y-1/2 text-white/50" size={18} />
            <input
              type="email"
              placeholder="工作邮箱"
              value={email}
              onChange={e => setEmail(e.target.value)}
              disabled={step === 'code'}
              onKeyDown={e => e.key === 'Enter' && step === 'email' && handleSendCode()}
              className="w-full pl-11 pr-4 py-3 bg-white/10 border border-white/20 rounded-2xl text-white placeholder-white/40 focus:outline-none focus:border-white/50 focus:bg-white/15 transition-all disabled:opacity-50"
            />
          </div>

          {/* 验证码 */}
          {step === 'code' && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="relative">
              <KeyRound className="absolute left-4 top-1/2 -translate-y-1/2 text-white/50" size={18} />
              <input
                type="text"
                placeholder="验证码"
                value={code}
                onChange={e => setCode(e.target.value)}
                maxLength={6}
                onKeyDown={e => e.key === 'Enter' && handleVerify()}
                className="w-full pl-11 pr-4 py-3 bg-white/10 border border-white/20 rounded-2xl text-white placeholder-white/40 focus:outline-none focus:border-white/50 focus:bg-white/15 transition-all"
                autoFocus
              />
            </motion.div>
          )}

          {/* 错误提示 */}
          {error && (
            <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-red-200 text-sm text-center bg-red-500/20 rounded-xl py-2">
              {error}
            </motion.p>
          )}

          {/* 按钮 */}
          {step === 'email' ? (
            <button
              onClick={handleSendCode}
              disabled={loading}
              className="w-full py-3 bg-white/25 hover:bg-white/35 text-white font-semibold rounded-2xl transition-all flex items-center justify-center gap-2 border border-white/30 disabled:opacity-50"
            >
              {loading ? <Loader2 size={18} className="animate-spin" /> : <Mail size={18} />}
              发送验证码
            </button>
          ) : (
            <div className="space-y-3">
              <button
                onClick={handleVerify}
                disabled={loading}
                className="w-full py-3 bg-white/25 hover:bg-white/35 text-white font-semibold rounded-2xl transition-all flex items-center justify-center gap-2 border border-white/30 disabled:opacity-50"
              >
                {loading ? <Loader2 size={18} className="animate-spin" /> : <KeyRound size={18} />}
                登录
              </button>
              <div className="flex items-center justify-between text-sm">
                <button
                  onClick={() => { setStep('email'); setCode(''); setError('') }}
                  className="text-white/50 hover:text-white/80 transition-colors"
                >
                  换个邮箱
                </button>
                <button
                  onClick={handleSendCode}
                  disabled={countdown > 0 || loading}
                  className="text-white/50 hover:text-white/80 transition-colors disabled:opacity-30"
                >
                  {countdown > 0 ? `${countdown}s 后重发` : '重新发送'}
                </button>
              </div>
            </div>
          )}
        </div>
      </motion.div>
    </div>
  )
}
