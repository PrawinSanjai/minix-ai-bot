export default function GlassCard({ children, className = '', ...props }) {
  return (
    <div className={`glass ${className}`} {...props}>
      {children}
    </div>
  )
}
