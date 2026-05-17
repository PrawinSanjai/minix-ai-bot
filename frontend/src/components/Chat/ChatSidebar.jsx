import { useApp } from '../../context/AppContext'
import './ChatSidebar.css'

export default function ChatSidebar() {
  const { state, dispatch, loadConversation } = useApp()

  function handleLoadChat(chatId) {
    dispatch({ type: 'SET_CURRENT_CHAT', payload: chatId })
    dispatch({ type: 'CLOSE_SIDEBAR' })

    // Fetch full conversation if it's a server-side chat (numeric ID)
    if (!String(chatId).startsWith('local_')) {
      loadConversation(chatId)
    } else {
      // Load from local state
      const chat = state.chatHistory.find(c => c.id === chatId)
      if (chat && chat.messages) {
        dispatch({ type: 'SET_CHAT_MESSAGES', payload: chat.messages })
      } else {
        dispatch({ type: 'CLEAR_MESSAGES' })
      }
    }
  }

  function newChat() {
    dispatch({ type: 'SET_TOPIC', payload: '' })
    dispatch({ type: 'CLEAR_MESSAGES' })
    dispatch({ type: 'SET_CURRENT_CHAT', payload: null })
    dispatch({ type: 'CLOSE_SIDEBAR' })
  }

  return (
    <aside className={`sidebar${state.sidebarOpen ? ' open' : ''}`}>
      <div className="sidebar-header">
        <div className="user-profile">
          <div className="user-avatar">
            {state.user.name ? state.user.name.charAt(0).toUpperCase() : 'U'}
          </div>
          <div className="user-info">
            <span className="user-name">{state.user.name || 'User'}</span>
            <span className="user-status">Online</span>
          </div>
        </div>
        <button className="icon-btn close-sidebar" onClick={() => dispatch({ type: 'CLOSE_SIDEBAR' })} aria-label="Close sidebar">
          <i className="fa-solid fa-xmark" />
        </button>
      </div>

      <div className="sidebar-search">
        <i className="fa-solid fa-search" />
        <input type="text" placeholder="Search conversations..." />
      </div>

      <div className="chat-history">
        <h3 className="section-title">Chat History</h3>
        {state.chatHistory.length === 0 ? (
          <div className="history-empty">
            <i className="fa-regular fa-message" />
            <span>No conversations yet</span>
          </div>
        ) : (
          <ul>
            {state.chatHistory.map(chat => (
              <li
                key={chat.id}
                className={`history-item${chat.id === state.currentChatId ? ' active' : ''}`}
                onClick={() => handleLoadChat(chat.id)}
              >
                <div className="history-item-icon">
                  <i className="fa-regular fa-comment-dots" />
                </div>
                <div className="history-item-info">
                  <div className="history-item-title">{chat.title}</div>
                  <div className="history-item-preview">{chat.preview || 'No messages'}</div>
                </div>
                <span className="history-item-time">{chat.time || ''}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="sidebar-footer">
        <button className="sidebar-btn" onClick={() => dispatch({ type: 'SET_SCREEN', payload: 'settings' })}>
          <i className="fa-solid fa-sliders" />
          <span>Settings</span>
        </button>
        <button className="sidebar-btn" onClick={newChat}>
          <i className="fa-solid fa-plus" />
          <span>New Chat</span>
        </button>
      </div>
    </aside>
  )
}
