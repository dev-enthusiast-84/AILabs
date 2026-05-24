import { useCallback, useState } from 'react'

/** Manages a Set<string> with a stable toggle function — avoids duplicate Set-toggle boilerplate. */
export function useToggleSet(initial: Iterable<string> = []) {
  const [set, setSet] = useState(() => new Set<string>(initial))
  const toggle = useCallback((id: string) =>
    setSet(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    }), [])
  return [set, toggle] as const
}
