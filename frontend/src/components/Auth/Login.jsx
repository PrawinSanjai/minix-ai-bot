import { useState } from 'react'
import { useApp } from '../../context/AppContext'
import GlassCard from '../UI/GlassCard'
import './Auth.css'

export default function Login() {
  const { state, dispatch, handleLogin } = useApp()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!email || !password) return
    setError('')
    setLoading(true)
    try {
      await handleLogin(email, password)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-screen">
      <GlassCard className="auth-card">
        <div className="auth-visual">
          <div className="blob blob-1" />
          <div className="blob blob-2" />
          <div className="blob blob-3" />
          <i className="fa-solid fa-brain auth-icon" />
        </div>

        <h1 className="auth-title">Welcome Back</h1>
        <p className="auth-subtitle">Your safe space to express emotions</p>

        <form onSubmit={handleSubmit}>
          <div className="input-group">
            <label htmlFor="login-email"><i className="fa-regular fa-envelope" /> Email</label>
            <input id="login-email" type="email" placeholder="you@example.com" value={email} onChange={e => setEmail(e.target.value)} required />
          </div>
          <div className="input-group">
            <label htmlFor="login-password"><i className="fa-regular fa-lock" /> Password</label>
            <input id="login-password" type="password" placeholder="••••••••" value={password} onChange={e => setPassword(e.target.value)} required />
          </div>
          {error && <p className="auth-error">{error}</p>}
          <button type="submit" className="btn-primary gradient" disabled={loading}>
            <span>{loading ? 'Logging in...' : 'Login'}</span>
            <i className="fa-solid fa-arrow-right" />
          </button>
        </form>

        <p className="auth-switch">
          Don't have an account?{' '}
          <a href="#" onClick={e => { e.preventDefault(); dispatch({ type: 'SET_SCREEN', payload: 'signup' }) }}>Sign up</a>
        </p>
      </GlassCard>
    </div>
  )
}
