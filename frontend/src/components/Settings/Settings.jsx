import { useState } from 'react'
import { useApp } from '../../context/AppContext'
import GlassCard from '../UI/GlassCard'
import './Settings.css'

const TONES = [
  { value: 'friendly', icon: 'fa-regular fa-face-smile', label: 'Friendly', desc: 'Warm and approachable' },
  { value: 'motivational', icon: 'fa-solid fa-rocket', label: 'Motivational', desc: 'Encouraging and empowering' },
  { value: 'listener', icon: 'fa-regular fa-ear-listen', label: 'Listener', desc: 'Reflective and empathetic' },
]

export default function Settings() {
  const { state, dispatch, handleUpdateProfile, handleUpdateTone, handleLogout, handleClearHistory } = useApp()
  const [name, setName] = useState(state.user.name)
  const [currentPw, setCurrentPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [confirmPw, setConfirmPw] = useState('')
  const [saving, setSaving] = useState(false)

  async function handleSave() {
    setSaving(true)
    try {
      if (name.trim() && name.trim() !== state.user.name) {
        await handleUpdateProfile(name.trim())
      }
      const selectedTone = document.querySelector('input[name="tone"]:checked')?.value
      if (selectedTone && selectedTone !== state.tone) {
        await handleUpdateTone(selectedTone)
      }
      alert('Settings saved!')
    } catch (err) {
      alert('Error saving settings: ' + err.message)
    } finally {
      setSaving(false)
    }
  }

  function handleClear() {
    if (state.chatHistory.length === 0) return
    handleClearHistory()
  }

  function handleLogoutClick() {
    handleLogout()
  }

  return (
    <div className="settings-screen">
      <div className="settings-container">
        <header className="settings-header">
          <button className="icon-btn" onClick={() => dispatch({ type: 'SET_SCREEN', payload: 'chat' })} aria-label="Back">
            <i className="fa-solid fa-arrow-left" />
          </button>
          <h2>Settings</h2>
        </header>

        <div className="settings-body">
          <GlassCard className="settings-section">
            <h3><i className="fa-regular fa-user" /> Profile</h3>
            <div className="input-group">
              <label htmlFor="settings-name">Display Name</label>
              <input id="settings-name" type="text" value={name} onChange={e => setName(e.target.value)} />
            </div>
          </GlassCard>

          <GlassCard className="settings-section">
            <h3><i className="fa-regular fa-lock" /> Change Password</h3>
            <div className="input-group">
              <label htmlFor="settings-current-pw">Current Password</label>
              <input id="settings-current-pw" type="password" placeholder="Current password" value={currentPw} onChange={e => setCurrentPw(e.target.value)} />
            </div>
            <div className="input-group">
              <label htmlFor="settings-new-pw">New Password</label>
              <input id="settings-new-pw" type="password" placeholder="New password" value={newPw} onChange={e => setNewPw(e.target.value)} />
            </div>
            <div className="input-group">
              <label htmlFor="settings-confirm-pw">Confirm Password</label>
              <input id="settings-confirm-pw" type="password" placeholder="Confirm new password" value={confirmPw} onChange={e => setConfirmPw(e.target.value)} />
            </div>
          </GlassCard>

          <GlassCard className="settings-section">
            <h3><i className="fa-regular fa-face-smile" /> Chatbot Tone</h3>
            <p className="settings-desc">Choose how Minix responds to you</p>
            <div className="tone-options" role="radiogroup" aria-label="Chatbot tone">
              {TONES.map(t => (
                <label key={t.value} className="tone-option">
                  <input type="radio" name="tone" value={t.value} defaultChecked={state.tone === t.value} />
                  <div className="tone-content">
                    <i className={t.icon} />
                    <span className="tone-label">{t.label}</span>
                    <span className="tone-desc">{t.desc}</span>
                  </div>
                </label>
              ))}
            </div>
          </GlassCard>

          <GlassCard className="settings-section danger">
            <h3><i className="fa-regular fa-triangle-exclamation" /> Data</h3>
            <p className="settings-desc">Manage your conversation data</p>
            <button className="btn-secondary danger-btn" onClick={handleClear}>
              <i className="fa-regular fa-trash-can" />
              Clear Chat History
            </button>
          </GlassCard>

          <button className="btn-primary gradient" onClick={handleSave} disabled={saving}>
            <i className="fa-regular fa-floppy-disk" />
            <span>{saving ? 'Saving...' : 'Save Changes'}</span>
          </button>

          <button className="btn-secondary logout-btn" onClick={handleLogoutClick}>
            <i className="fa-solid fa-right-from-bracket" />
            Logout
          </button>
        </div>
      </div>
    </div>
  )
}
