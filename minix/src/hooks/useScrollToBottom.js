import { useEffect, useRef } from 'react'

export function useScrollToBottom(deps = []) {
  const ref = useRef(null)

  useEffect(() => {
    if (ref.current) {
      ref.current.scrollTop = ref.current.scrollHeight
    }
  }, deps)

  return ref
}
