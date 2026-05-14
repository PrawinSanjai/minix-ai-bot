import { useState } from 'react'
import { useApp } from '../../context/AppContext'
import GlassCard from '../UI/GlassCard'
import './Onboarding.css'

const TOPICS = [
  { key: 'stress', icon: 'fa-solid fa-cloud', label: 'Stress' },
  { key: 'anxiety', icon: 'fa-solid fa-heart-pulse', label: 'Anxiety' },
  { key: 'career', icon: 'fa-solid fa-briefcase', label: 'Career' },
  { key: 'relationships', icon: 'fa-solid fa-hand-holding-heart', label: 'Relationships' },
  { key: 'general', icon: 'fa-solid fa-comment-dots', label: 'General Chat' },
]

export default function Onboarding() {
  const { dispatch } = useApp()
  const [selected, setSelected] = useState('')
  const [custom, setCustom] = useState('')

  function selectTopic(key) {
    setSelected(key)
    setCustom('')
    dispatch({ type: 'SET_TOPIC', payload: key })
  }

  function handleCustomInput(e) {
    const val = e.target.value
    setCustom(val)
    if (val.trim()) {
      setSelected('')
      dispatch({ type: 'SET_TOPIC', payload: val })
    }
  }

  function startChat() {
    if (!selected && !custom.trim()) return
    dispatch({ type: 'SET_SCREEN', payload: 'chat' })
  }

  const ready = selected || custom.trim()

  return (
    <div className="onboarding-screen">
      <GlassCard className="onboarding-card">
        <div className="onboarding-header">
          <div className="onboarding-avatar">
            <i className="fa-solid fa-sparkles" />
          </div>
          <h2>What would you like to talk about?</h2>
          <p>Choose what's on your mind, or type your own</p>
        </div>

        <div className="topic-chips">
          {TOPICS.map(t => (
            <button
              key={t.key}
              className={`chip${selected === t.key ? ' active' : ''}`}
              onClick={() => selectTopic(t.key)}
            >
              <i className={t.icon} /> {t.label}
            </button>
          ))}
        </div>

        <div className="custom-topic">
          <i className="fa-regular fa-pen-to-square" />
          <input
            type="text"
            placeholder="Or type something else..."
            value={custom}
            onChange={handleCustomInput}
          />
        </div>

        <button
          className="btn-primary gradient"
          disabled={!ready}
          onClick={startChat}
        >
          <span>Start Chatting</span>
          <i className="fa-solid fa-arrow-right" />
        </button>
      </GlassCard>
    </div>
  )
}
