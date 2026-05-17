import { useState } from 'react'
import { useApp } from '../../context/AppContext'
import GlassCard from '../UI/GlassCard'
import './Auth.css'

export default function Signup() {
  const { dispatch, handleRegister } = useApp()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!name || !email || !password) return
    setError('')
    setLoading(true)
    try {
      await handleRegister(name, email, password)
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
          <i className="fa-solid fa-heart auth-icon" />
        </div>

        <h1 className="auth-title">Join Minix</h1>
        <p className="auth-subtitle">Begin your journey of emotional well-being</p>

        <form onSubmit={handleSubmit}>
          <div className="input-group">
            <label htmlFor="signup-name"><i className="fa-regular fa-user" /> Name</label>
            <input id="signup-name" type="text" placeholder="Your name" value={name} onChange={e => setName(e.target.value)} required />
          </div>
          <div className="input-group">
            <label htmlFor="signup-email"><i className="fa-regular fa-envelope" /> Email</label>
            <input id="signup-email" type="email" placeholder="you@example.com" value={email} onChange={e => setEmail(e.target.value)} required />
          </div>
          <div className="input-group">
            <label htmlFor="signup-password"><i className="fa-regular fa-lock" /> Password</label>
            <input id="signup-password" type="password" placeholder="••••••••" value={password} onChange={e => setPassword(e.target.value)} required />
          </div>
          {error && <p className="auth-error">{error}</p>}
          <button type="submit" className="btn-primary gradient" disabled={loading}>
            <span>{loading ? 'Creating...' : 'Create Account'}</span>
            <i className="fa-solid fa-heart" />
          </button>
        </form>

        <p className="auth-switch">
          Already have an account?{' '}
          <a href="#" onClick={e => { e.preventDefault(); dispatch({ type: 'SET_SCREEN', payload: 'login' }) }}>Login</a>
        </p>
      </GlassCard>
    </div>
  )
}
