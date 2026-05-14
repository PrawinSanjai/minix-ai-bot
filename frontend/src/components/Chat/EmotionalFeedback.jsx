import { detectEmotion, EMOTION_LABELS, EMOTION_ICONS } from '../../utils/emotions'
import './EmotionalFeedback.css'

export default function EmotionalFeedback({ messages }) {
  const lastUserMsg = [...messages].reverse().find(m => m.role === 'user')
  const emotion = lastUserMsg ? detectEmotion(lastUserMsg.text) : 'neutral'
  const icon = EMOTION_ICONS[emotion]
  const label = EMOTION_LABELS[emotion]

  return (
    <div className="emotional-feedback">
      <div className="feedback-content">
        <i className={icon} />
        <span>{label}</span>
      </div>
    </div>
  )
}
