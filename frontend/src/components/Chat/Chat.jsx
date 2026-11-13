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
  const { state, dispatch, fetchHistory } = useApp()
  const [botTyping, setBotTyping] = useState(false)
  const [streamingReply, setStreamingReply] = useState('')
  const [streamingConversationId, setStreamingConversationId] = useState(null)
  const [error, setError] = useState('')
  const messagesRef = useScrollToBottom([state.messages, botTyping, streamingReply])
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
    setStreamingReply('')
    dispatch({ type: 'ADD_MESSAGE', payload: { role: 'user', text } })
    setBotTyping(true)
    let streamController = null

    try {
      const cid = state.currentChatId && !String(state.currentChatId).startsWith('local_') ? state.currentChatId : null
      const idempotencyKey = globalThis.crypto?.randomUUID?.() || `minix-${Date.now()}-${Math.random().toString(36).slice(2)}`
      const job = await api.enqueueMessage(text, cid, state.topic, idempotencyKey)
      dispatch({ type: 'SET_CURRENT_CHAT', payload: String(job.conversation_id) })
      setStreamingConversationId(String(job.conversation_id))
      fetchHistory()

      let replyDraft = ''
      let terminal = false
      const finish = reply => {
        if (terminal) return
        terminal = true
        dispatch({
          type: 'ADD_MESSAGE_TO_CHAT',
          payload: {
            conversationId: job.conversation_id,
            message: { role: 'bot', text: reply || replyDraft },
          },
        })
        setStreamingReply('')
        setStreamingConversationId(null)
      }
      const handleEvent = (event, data) => {
        if (event === 'reset' || event === 'retrying') {
          replyDraft = ''
          setStreamingReply('')
        } else if (event === 'chunk') {
          replyDraft += data.text || ''
          setStreamingReply(replyDraft)
        } else if (event === 'completed') {
          finish(data.reply)
        } else if (event === 'failed') {
          terminal = true
          setError(data.error || 'Minix could not generate a reply.')
          setStreamingReply('')
          setStreamingConversationId(null)
        }
      }

      streamController = new AbortController()
      const streamPromise = api.streamChatJob(job.job_id, handleEvent, streamController.signal)
        .catch(() => { /* Redis event streaming can fail while the durable job continues. */ })

      for (let attempt = 0; attempt < 300 && !terminal; attempt += 1) {
        const status = await api.getChatJob(job.job_id)
        if (status.status === 'completed') {
          finish(status.reply)
          break
        }
        if (status.status === 'failed') {
          terminal = true
          setError(status.error || 'Minix could not generate a reply.')
          setStreamingReply('')
          setStreamingConversationId(null)
          break
        }
        await new Promise(resolve => setTimeout(resolve, 1000))
      }
      streamController.abort()
      await streamPromise
      if (!terminal) {
        setError('Minix is still working. Your message is saved; reopen this chat to check for the reply.')
        setStreamingReply('')
        setStreamingConversationId(null)
      }
    } catch (err) {
      setError(err.message || 'Could not connect to server.')
    } finally {
      streamController?.abort()
      setBotTyping(false)
      fetchHistory()
    }
  }, [state.currentChatId, state.topic, dispatch, fetchHistory])

  async function handleClearChat() {
    if (state.messages.length === 0) return
    if (state.currentChatId && !String(state.currentChatId).startsWith('local_')) {
      try {
        await api.deleteConversation(state.currentChatId)
      } catch (err) {
        setError(err.message || 'Could not clear this conversation.')
        return
      }
    }
    dispatch({ type: 'CLEAR_MESSAGES' })
    dispatch({ type: 'SET_CURRENT_CHAT', payload: null })
    fetchHistory()
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
          {streamingReply && String(state.currentChatId) === streamingConversationId && <Message role="bot" text={streamingReply} />}
        </div>

        {error && <div className="chat-error">{error}</div>}

        <EmotionalFeedback messages={state.messages} />
        <TypingIndicator active={botTyping} />
        <InputBar onSend={handleSend} disabled={botTyping} />
      </div>
    </div>
  )
}
