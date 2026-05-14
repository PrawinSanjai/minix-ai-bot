import { useState, useCallback, useEffect } from 'react'
import { useApp } from '../../context/AppContext'
import { useScrollToBottom } from '../../hooks/useScrollToBottom'
import { getWelcomeMessage, generateResponse } from '../../utils/responses'
import { detectEmotion } from '../../utils/emotions'
import Message from './Message'
import ChatSidebar from './ChatSidebar'
import InputBar from './InputBar'
import EmotionalFeedback from './EmotionalFeedback'
import TypingIndicator from './TypingIndicator'
import './Chat.css'

export default function Chat() {
  const { state, dispatch, updateChatHistory } = useApp()
  const [botTyping, setBotTyping] = useState(false)
  const messagesRef = useScrollToBottom([state.messages, botTyping])

  const hasMessages = state.messages.length > 0

  useEffect(() => {
    if (!hasMessages && state.topic) {
      const welcome = getWelcomeMessage(state.topic)
      dispatch({ type: 'ADD_MESSAGE', payload: { role: 'bot', text: welcome } })
    }
  }, [])

  useEffect(() => {
    if (state.messages.length === 1 && state.messages[0].role === 'bot' && !state.currentChatId) {
      const id = 'chat_' + Date.now()
      dispatch({
        type: 'ADD_CHAT',
        payload: {
          id,
          title: state.topic || 'New conversation',
          preview: '',
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          messages: [...state.messages],
        },
      })
    }
  }, [state.messages, state.currentChatId, dispatch, state.topic])

  const handleSend = useCallback((text) => {
    dispatch({ type: 'ADD_MESSAGE', payload: { role: 'user', text } })

    if (!state.currentChatId) {
      const id = 'chat_' + Date.now()
      dispatch({
        type: 'ADD_CHAT',
        payload: {
          id,
          title: text.slice(0, 30),
          preview: text.slice(0, 50),
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          messages: [],
        },
      })
    }

    setBotTyping(true)

    setTimeout(() => {
      const emotion = detectEmotion(text)
      const response = generateResponse(state.tone, emotion)
      dispatch({ type: 'ADD_MESSAGE', payload: { role: 'bot', text: response } })
      setBotTyping(false)
      setTimeout(() => updateChatHistory(), 50)
    }, 1000 + Math.random() * 800)
  }, [state.currentChatId, state.tone, dispatch, updateChatHistory])

  return (
    <div className="chat-layout">
      <ChatSidebar />
      {state.sidebarOpen && (
        <div className="sidebar-overlay" onClick={() => dispatch({ type: 'CLOSE_SIDEBAR' })} />
      )}
      <div className="chat-main">
        <header className="chat-header">
          <button className="icon-btn hamburger" onClick={() => dispatch({ type: 'TOGGLE_SIDEBAR' })} aria-label="Open sidebar">
            <i className="fa-solid fa-bars" />
          </button>
          <div className="chat-header-info">
            <span className="chat-title">Minix</span>
            <span className="chat-status">{botTyping ? 'Typing...' : 'Online'}</span>
          </div>
          <div className="chat-header-actions">
            <button
              className="icon-btn"
              onClick={() => {
                if (state.messages.length === 0) return
                dispatch({ type: 'CLEAR_MESSAGES' })
                setTimeout(() => updateChatHistory(), 50)
              }}
              aria-label="Clear chat"
              title="Clear chat"
            >
              <i className="fa-regular fa-trash-can" />
            </button>
          </div>
        </header>

        <div className="messages" ref={messagesRef}>
          {!hasMessages ? (
            <div className="welcome-message">
              <div className="welcome-icon">
                <i className="fa-solid fa-sparkles" />
              </div>
              <h3>Hello! I'm your emotional companion</h3>
              <p>Share what's on your mind. I'm here to listen without judgment.</p>
            </div>
          ) : (
            state.messages.map((msg, i) => (
              <Message key={i} role={msg.role} text={msg.text} time={msg.time} />
            ))
          )}
        </div>

        <EmotionalFeedback messages={state.messages} />
        <TypingIndicator active={botTyping} />
        <InputBar onSend={handleSend} disabled={botTyping} />
      </div>
    </div>
  )
}
