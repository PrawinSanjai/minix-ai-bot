const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function getToken() {
  return localStorage.getItem('minix_token')
}

function setToken(token) {
  if (token) {
    localStorage.setItem('minix_token', token)
  } else {
    localStorage.removeItem('minix_token')
  }
}

function getUser() {
  try {
    const raw = localStorage.getItem('minix_user')
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function setUser(user) {
  if (user) {
    localStorage.setItem('minix_user', JSON.stringify(user))
  } else {
    localStorage.removeItem('minix_user')
  }
}

async function request(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...options.headers }
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers })

  if (!res.ok) {
    let detail = 'Request failed'
    try {
      const body = await res.json()
      detail = body.detail || detail
    } catch { /* ignore */ }
    if (res.status === 401) {
      setToken(null)
      setUser(null)
      window.location.reload()
    }
    throw new Error(detail)
  }

  return res.json()
}

function formatTime(isoString) {
  if (!isoString) return ''
  const d = new Date(isoString)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

const api = {

  // ─── Auth ───

  async login(email, password) {
    const data = await request('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })
    setToken(data.access_token)
    setUser(data.user)
    return data
  },

  async register(name, email, password) {
    const data = await request('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ name, email, password }),
    })
    setToken(data.access_token)
    setUser(data.user)
    return data
  },

  logout() {
    setToken(null)
    setUser(null)
  },

  getToken,
  getUser,

  // ─── User Profile ───

  async getProfile() {
    return request('/api/users/me')
  },

  async updateProfile(data) {
    const result = await request('/api/users/me', {
      method: 'PUT',
      body: JSON.stringify(data),
    })
    setUser({ ...getUser(), name: result.name })
    return result
  },

  async updateTone(tone) {
    const result = await request('/api/users/me/tone', {
      method: 'PUT',
      body: JSON.stringify({ tone }),
    })
    setUser({ ...getUser(), tone: result.tone })
    return result
  },

  async changePassword(data) {
    return request('/api/users/change-password', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  },

  // ─── Chat ───

  async sendMessage(message, conversationId, topic) {
    const data = await request('/api/chat/message', {
      method: 'POST',
      body: JSON.stringify({ message, conversation_id: conversationId, topic }),
    })
    return {
      reply: data.reply,
      conversationId: data.conversation_id,
      emotion: data.emotion,
    }
  },

  async getHistory() {
    const list = await request('/api/chat/history')
    return list.map(c => ({
      id: String(c.id),
      title: c.title,
      topic: c.topic,
      preview: c.preview || '',
      time: c.time || formatTime(c.updated_at),
    }))
  },

  async getConversation(id) {
    const data = await request(`/api/chat/history/${id}`)
    return {
      id: String(data.id),
      title: data.title,
      topic: data.topic,
      messages: (data.messages || []).map(m => ({
        role: m.role,
        text: m.content,
        time: formatTime(m.created_at),
      })),
    }
  },

  async deleteConversation(id) {
    return request(`/api/chat/history/${id}`, { method: 'DELETE' })
  },

  async clearHistory() {
    return request('/api/chat/history', { method: 'DELETE' })
  },
}

export { api, setToken, setUser, getToken, getUser }
