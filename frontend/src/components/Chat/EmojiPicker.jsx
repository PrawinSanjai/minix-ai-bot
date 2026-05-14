import './EmojiPicker.css'

const EMOJIS = ['😊', '🥺', '😌', '😔', '❤️', '🙏', '✨', '💪', '🌱', '🌈', '🕊️', '🌊', '🔥', '💫', '🎵', '☕']

export default function EmojiPicker({ open, onSelect }) {
  if (!open) return null
  return (
    <div className="emoji-picker open">
      <div className="emoji-grid">
        {EMOJIS.map((emoji, i) => (
          <button key={i} className="emoji-item" onClick={() => onSelect(emoji)}>
            {emoji}
          </button>
        ))}
      </div>
    </div>
  )
}
