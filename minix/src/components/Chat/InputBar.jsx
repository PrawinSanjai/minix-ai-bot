import { useState, useRef, useEffect } from 'react'
import EmojiPicker from './EmojiPicker'
import './InputBar.css'

export default function InputBar({ onSend, disabled }) {
  const [text, setText] = useState('')
  const [emojiOpen, setEmojiOpen] = useState(false)
  const inputRef = useRef(null)

  useEffect(() => {
    if (!disabled && inputRef.current) {
      inputRef.current.focus()
    }
  }, [disabled])

  function handleSend() {
    if (!text.trim() || disabled) return
    onSend(text.trim())
    setText('')
  }

  function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function handleEmojiSelect(emoji) {
    setText(prev => prev + emoji)
    setEmojiOpen(false)
    inputRef.current?.focus()
  }

  useEffect(() => {
    function close(e) {
      if (!e.target.closest('.emoji-picker') && !e.target.closest('.emoji-btn')) {
        setEmojiOpen(false)
      }
    }
    document.addEventListener('click', close)
    return () => document.removeEventListener('click', close)
  }, [])

  return (
    <div className="input-bar" style={{ position: 'relative' }}>
      <button className="icon-btn emoji-btn" onClick={e => { e.stopPropagation(); setEmojiOpen(o => !o) }} aria-label="Add emoji">
        <i className="fa-regular fa-face-smile-wink" />
      </button>
      <input
        ref={inputRef}
        type="text"
        placeholder="How are you feeling today?"
        value={text}
        onChange={e => setText(e.target.value)}
        onKeyDown={handleKey}
        disabled={disabled}
        aria-label="Type your message"
      />
      <button className="send-btn" onClick={handleSend} disabled={disabled || !text.trim()} aria-label="Send message">
        <i className="fa-solid fa-paper-plane" />
      </button>
      <EmojiPicker open={emojiOpen} onSelect={handleEmojiSelect} />
    </div>
  )
}
