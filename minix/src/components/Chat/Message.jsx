import './Message.css'

export default function Message({ role, text, time }) {
  return (
    <div className={`message ${role}`}>
      <div className="message-bubble">{text}</div>
      <span className="message-time">{time}</span>
    </div>
  )
}
