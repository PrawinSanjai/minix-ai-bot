import { useState } from 'react'
import { useApp } from '../../context/AppContext'
import GlassCard from '../UI/GlassCard'
import './Auth.css'

export default function Login() {
  const { dispatch } = useApp()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  function handleSubmit(e) {
    e.preventDefault()
    if (!email || !password) return
    const name = email.split('@')[0]
    dispatch({ type: 'SET_USER', payload: { name, email } })
    dispatch({ type: 'SET_SCREEN', payload: 'onboarding' })
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
          <button type="submit" className="btn-primary gradient">
            <span>Login</span>
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
