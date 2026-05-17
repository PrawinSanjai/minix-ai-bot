import { createContext, useContext, useReducer, useEffect, useCallback } from 'react'
import { api, setToken as saveToken, setUser as saveUser, getToken, getUser } from '../services/api'
import { loadState, saveState } from '../utils/storage'

const AppContext = createContext(null)

const initialState = {
  user: { name: '', email: '', tone: 'friendly' },
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
      return { ...state, user: action.payload, tone: action.payload.tone || 'friendly' }

    case 'SET_SCREEN':
      return { ...state, currentScreen: action.payload }

    case 'SET_TOPIC':
      return { ...state, topic: action.payload }

    case 'SET_TONE':
      return { ...state, tone: action.payload }

    case 'SET_MESSAGES':
      return { ...state, messages: action.payload }

    case 'ADD_MESSAGE': {
      const msg = {
        role: action.payload.role,
        text: action.payload.text,
        time: action.payload.time || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      }
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
      return { ...state, currentChatId: action.payload }
    }

    case 'SET_CHAT_MESSAGES':
      return { ...state, messages: action.payload }

    case 'DELETE_CHAT': {
      const filtered = state.chatHistory.filter(c => c.id !== action.payload)
      let msgs = state.messages
      let cid = state.currentChatId
      if (state.currentChatId === action.payload) {
        cid = filtered.length > 0 ? filtered[0].id : null
        msgs = []
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

  // Hydrate from localStorage on mount
  useEffect(() => {
    const token = getToken()
    const savedUser = getUser()

    if (token && savedUser) {
      dispatch({ type: 'SET_USER', payload: savedUser })
      dispatch({ type: 'SET_SCREEN', payload: 'onboarding' })
    } else {
      const saved = loadState()
      if (saved && saved.user && saved.user.name) {
        dispatch({ type: 'HYDRATE', payload: saved })
      }
    }
  }, [])

  // Persist to localStorage as fallback
  useEffect(() => {
    if (state.user.name && !getToken()) {
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

  // ─── Auth handlers ───

  const handleLogin = useCallback(async (email, password) => {
    const data = await api.login(email, password)
    dispatch({ type: 'SET_USER', payload: data.user })
    dispatch({ type: 'SET_SCREEN', payload: 'onboarding' })
  }, [])

  const handleRegister = useCallback(async (name, email, password) => {
    const data = await api.register(name, email, password)
    dispatch({ type: 'SET_USER', payload: data.user })
    dispatch({ type: 'SET_SCREEN', payload: 'onboarding' })
  }, [])

  const handleLogout = useCallback(() => {
    api.logout()
    dispatch({ type: 'SET_USER', payload: { name: '', email: '', tone: 'friendly' } })
    dispatch({ type: 'CLEAR_HISTORY' })
    dispatch({ type: 'SET_SCREEN', payload: 'login' })
  }, [])

  // ─── Chat handlers ───

  const fetchHistory = useCallback(async () => {
    try {
      const list = await api.getHistory()
      dispatch({ type: 'SET_CHAT_HISTORY', payload: list })
    } catch { /* offline */ }
  }, [])

  const loadConversation = useCallback(async (id) => {
    try {
      const chat = await api.getConversation(id)
      dispatch({ type: 'SET_CHAT_MESSAGES', payload: chat.messages })
      dispatch({ type: 'SET_CURRENT_CHAT', payload: id })
    } catch { /* offline */ }
  }, [])

  const handleDeleteChat = useCallback(async (id) => {
    try {
      await api.deleteConversation(id)
    } catch { /* offline */ }
    dispatch({ type: 'DELETE_CHAT', payload: id })
  }, [])

  const handleClearHistory = useCallback(async () => {
    try {
      await api.clearHistory()
    } catch { /* offline */ }
    dispatch({ type: 'CLEAR_HISTORY' })
  }, [])

  // ─── Settings handlers ───

  const handleUpdateProfile = useCallback(async (name) => {
    try {
      await api.updateProfile({ name })
    } catch { /* offline */ }
    dispatch({ type: 'SET_USER', payload: { ...state.user, name } })
  }, [state.user])

  const handleUpdateTone = useCallback(async (tone) => {
    try {
      await api.updateTone(tone)
    } catch { /* offline */ }
    dispatch({ type: 'SET_TONE', payload: tone })
  }, [])

  return (
    <AppContext.Provider value={{
      state,
      dispatch,
      updateChatHistory,
      handleLogin,
      handleRegister,
      handleLogout,
      fetchHistory,
      loadConversation,
      handleDeleteChat,
      handleClearHistory,
      handleUpdateProfile,
      handleUpdateTone,
    }}>
      {children}
    </AppContext.Provider>
  )
}

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used within AppProvider')
  return ctx
}
