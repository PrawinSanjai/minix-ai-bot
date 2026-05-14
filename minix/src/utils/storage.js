const STORAGE_KEY = 'minix_state'

export function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return {
      user: parsed.user || { name: '', email: '' },
      tone: parsed.tone || 'friendly',
      chatHistory: parsed.chatHistory || [],
    }
  } catch {
    return null
  }
}

export function saveState(data) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
  } catch {
    /* storage unavailable */
  }
}

export function clearState() {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* storage unavailable */
  }
}
