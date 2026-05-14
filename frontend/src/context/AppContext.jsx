import { createContext, useContext, useReducer, useEffect, useCallback } from 'react'
import { loadState, saveState } from '../utils/storage'

const AppContext = createContext(null)

const initialState = {
  user: { name: '', email: '' },
  currentScreen: 'login',
  topic: '',
  tone: 'friendly',
  messages: [],
  chatHistory: [],
  currentChatId: null,
  sidebarOpen: false,
  isTyping: false,
}

function reducer(state, action) {
  switch (action.type) {
    case 'SET_USER':
      return { ...state, user: action.payload }

    case 'SET_SCREEN':
      return { ...state, currentScreen: action.payload }

    case 'SET_TOPIC':
      return { ...state, topic: action.payload }

    case 'SET_TONE':
      return { ...state, tone: action.payload }

    case 'SET_MESSAGES':
      return { ...state, messages: action.payload }

    case 'ADD_MESSAGE': {
      const msg = { role: action.payload.role, text: action.payload.text, time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }
      return { ...state, messages: [...state.messages, msg] }
    }

    case 'SET_CURRENT_CHAT':
      return { ...state, currentChatId: action.payload }

    case 'SET_CHAT_HISTORY':
      return { ...state, chatHistory: action.payload }

    case 'ADD_CHAT': {
      const existing = state.chatHistory.find(c => c.id === action.payload.id)
      if (existing) return state
      return { ...state, chatHistory: [action.payload, ...state.chatHistory], currentChatId: action.payload.id }
    }

    case 'UPDATE_CURRENT_CHAT': {
      const history = state.chatHistory.map(c => {
        if (c.id !== state.currentChatId) return c
        const userMsgs = state.messages.filter(m => m.role === 'user')
        const last = userMsgs[userMsgs.length - 1]
        return {
          ...c,
          messages: [...state.messages],
          preview: last ? last.text.slice(0, 50) : c.preview,
          title: state.topic || (last ? last.text.slice(0, 30) : c.title),
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        }
      })
      return { ...state, chatHistory: history }
    }

    case 'LOAD_CHAT': {
      const chat = state.chatHistory.find(c => c.id === action.payload)
      if (!chat) return state
      return { ...state, currentChatId: action.payload, messages: chat.messages || [] }
    }

    case 'DELETE_CHAT': {
      const filtered = state.chatHistory.filter(c => c.id !== action.payload)
      let msgs = state.messages
      let cid = state.currentChatId
      if (state.currentChatId === action.payload) {
        cid = filtered.length > 0 ? filtered[0].id : null
        msgs = cid ? (filtered.find(c => c.id === cid)?.messages || []) : []
      }
      return { ...state, chatHistory: filtered, currentChatId: cid, messages: msgs }
    }

    case 'CLEAR_HISTORY':
      return { ...state, chatHistory: [], messages: [], currentChatId: null }

    case 'CLEAR_MESSAGES':
      return { ...state, messages: [] }

    case 'TOGGLE_SIDEBAR':
      return { ...state, sidebarOpen: !state.sidebarOpen }

    case 'CLOSE_SIDEBAR':
      return { ...state, sidebarOpen: false }

    case 'SET_TYPING':
      return { ...state, isTyping: action.payload }

    case 'HYDRATE':
      return { ...state, ...action.payload }

    default:
      return state
  }
}

export function AppProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, initialState)

  useEffect(() => {
    const saved = loadState()
    if (saved) {
      dispatch({ type: 'HYDRATE', payload: saved })
    }
  }, [])

  useEffect(() => {
    if (state.user.name) {
      saveState({
        user: state.user,
        tone: state.tone,
        chatHistory: state.chatHistory,
      })
    }
  }, [state.user, state.tone, state.chatHistory])

  const updateChatHistory = useCallback(() => {
    dispatch({ type: 'UPDATE_CURRENT_CHAT' })
  }, [])

  return (
    <AppContext.Provider value={{ state, dispatch, updateChatHistory }}>
      {children}
    </AppContext.Provider>
  )
}

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used within AppProvider')
  return ctx
}
