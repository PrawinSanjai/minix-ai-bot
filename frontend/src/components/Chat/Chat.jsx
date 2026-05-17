import { useState, useCallback, useEffect, useRef } from 'react'
import { useApp } from '../../context/AppContext'
import { useScrollToBottom } from '../../hooks/useScrollToBottom'
import { getWelcomeMessage } from '../../utils/responses'
import { api } from '../../services/api'
import Message from './Message'
import ChatSidebar from './ChatSidebar'
import InputBar from './InputBar'
import EmotionalFeedback from './EmotionalFeedback'
import TypingIndicator from './TypingIndicator'
import './Chat.css'

export default function Chat() {
  const { state, dispatch, updateChatHistory, fetchHistory, loadConversation } = useApp()
  const [botTyping, setBotTyping] = useState(false)
  const [error, setError] = useState('')
  const messagesRef = useScrollToBottom([state.messages, botTyping])
  const historyFetched = useRef(false)

  const hasMessages = state.messages.length > 0

  // Fetch history on first mount
  useEffect(() => {
    if (!historyFetched.current) {
      historyFetched.current = true
      fetchHistory()
    }
  }, [fetchHistory])

  // Show welcome message for new chats
  useEffect(() => {
    if (!hasMessages && state.topic && !state.currentChatId) {
      const welcome = getWelcomeMessage(state.topic)
      dispatch({ type: 'ADD_MESSAGE', payload: { role: 'bot', text: welcome } })
    }
  }, [])

  // Auto-create a new chat entry in sidebar when first message arrives
  useEffect(() => {
    if (state.messages.length === 1 && state.messages[0].role === 'bot' && !state.currentChatId) {
      const id = 'local_' + Date.now()
      dispatch({
        type: 'ADD_CHAT',
        payload: {
          id,
          title: state.topic || 'New conversation',
          preview: '',
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      })
    }
  }, [state.messages, state.currentChatId, dispatch, state.topic])

  const handleSend = useCallback(async (text) => {
    setError('')
    dispatch({ type: 'ADD_MESSAGE', payload: { role: 'user', text } })

    if (!state.currentChatId) {
      const id = 'local_' + Date.now()
      dispatch({
        type: 'ADD_CHAT',
        payload: {
          id,
          title: text.slice(0, 30),
          preview: text.slice(0, 50),
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      })
    }

    setBotTyping(true)

    try {
      const cid = state.currentChatId && !String(state.currentChatId).startsWith('local_') ? state.currentChatId : null
      const result = await api.sendMessage(text, cid, state.topic)

      // Update to real server ID if we had a local ID
      if (!state.currentChatId || String(state.currentChatId).startsWith('local_')) {
        dispatch({ type: 'SET_CURRENT_CHAT', payload: result.conversationId })
      }

      dispatch({
        type: 'ADD_MESSAGE',
        payload: { role: 'bot', text: result.reply },
      })
    } catch (err) {
      setError(err.message || 'Could not connect to server.')
    } finally {
      setBotTyping(false)
      setTimeout(() => updateChatHistory(), 100)
      setTimeout(() => fetchHistory(), 200)
    }
  }, [state.currentChatId, state.topic, state.tone, dispatch, updateChatHistory, fetchHistory])

  function handleClearChat() {
    if (state.messages.length === 0) return
    dispatch({ type: 'CLEAR_MESSAGES' })
    setTimeout(() => updateChatHistory(), 50)
  }

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
            <button className="icon-btn" onClick={handleClearChat} aria-label="Clear chat" title="Clear chat">
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

        {error && <div className="chat-error">{error}</div>}

        <EmotionalFeedback messages={state.messages} />
        <TypingIndicator active={botTyping} />
        <InputBar onSend={handleSend} disabled={botTyping} />
      </div>
    </div>
  )
}
