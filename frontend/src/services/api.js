const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8080'

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
    let message = 'Something went wrong. Please try again.'
    const statusMessages = {
      400: 'Please check your input and try again.',
      401: 'Incorrect email or password.',
      403: 'You don\'t have permission to do that.',
      404: 'The requested resource was not found.',
      413: 'Message is too long. Please shorten it.',
      429: 'You\'re moving too fast! Please wait a moment.',
      500: 'Server error. Please try again later.',
    }
    message = statusMessages[res.status] || message
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') message = body.detail
    } catch { /* response did not contain JSON */ }

    if (res.status === 401 && !path.includes('/auth/')) {
      setToken(null)
      setUser(null)
      window.location.reload()
    }
    throw new Error(message)
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
    const data = await request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })
    setToken(data.access_token)
    setUser(data.user)
    return data
  },

  async register(name, email, password) {
    const data = await request('/auth/register', {
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
    return request('/users/me')
  },

  async updateProfile(data) {
    const result = await request('/users/me', {
      method: 'PUT',
      body: JSON.stringify(data),
    })
    setUser({ ...getUser(), name: result.name })
    return result
  },

  async updateTone(tone) {
    const result = await request('/users/me/tone', {
      method: 'PUT',
      body: JSON.stringify({ tone }),
    })
    setUser({ ...getUser(), tone: result.tone })
    return result
  },

  async changePassword(data) {
    return request('/users/change-password', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  },

  // ─── Chat ───

  async enqueueMessage(message, conversationId, topic, idempotencyKey) {
    return request('/chat/message', {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify({ message, conversation_id: conversationId, topic }),
    })
  },

  async getChatJob(jobId) {
    return request(`/chat/jobs/${jobId}`)
  },

  async streamChatJob(jobId, onEvent, signal) {
    const headers = { Authorization: `Bearer ${getToken()}` }
    const response = await fetch(`${API_BASE}/chat/jobs/${jobId}/events`, { headers, signal })
    if (!response.ok) {
      let detail = 'Live reply stream is unavailable.'
      try {
        const body = await response.json()
        if (body.detail) detail = body.detail
      } catch { /* use generic message */ }
      throw new Error(detail)
    }
    if (!response.body) throw new Error('This browser cannot stream chat replies.')

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let done = false

    while (!done) {
      const { value, done: streamDone } = await reader.read()
      done = streamDone
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
      let boundary
      while ((boundary = buffer.indexOf('\n\n')) >= 0) {
        const block = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        let event = 'message'
        const data = []
        for (const line of block.split(/\r?\n/)) {
          if (line.startsWith('event:')) event = line.slice(6).trim()
          if (line.startsWith('data:')) data.push(line.slice(5).trim())
        }
        if (!data.length) continue
        onEvent(event, JSON.parse(data.join('\n')))
        if (event === 'completed' || event === 'failed') {
          await reader.cancel()
          return
        }
      }
    }
  },

  async getHistory() {
    const list = await request('/chat/history')
    return list.map(c => ({
      id: String(c.id),
      title: c.title,
      topic: c.topic,
      preview: c.preview || '',
      time: c.time || formatTime(c.updated_at),
    }))
  },

  async getConversation(id) {
    const data = await request(`/chat/history/${id}`)
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
    return request(`/chat/history/${id}`, { method: 'DELETE' })
  },

  async clearHistory() {
    return request('/chat/history', { method: 'DELETE' })
  },
}

export { api, setToken, setUser, getToken, getUser }
