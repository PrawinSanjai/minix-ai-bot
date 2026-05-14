import './TypingIndicator.css'

export default function TypingIndicator({ active }) {
  if (!active) return null
  return (
    <div className="typing-indicator active">
      <span className="typing-dot" />
      <span className="typing-dot" />
      <span className="typing-dot" />
    </div>
  )
}
