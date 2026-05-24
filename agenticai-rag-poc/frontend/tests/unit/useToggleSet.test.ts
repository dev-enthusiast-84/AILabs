import { describe, it, expect } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useToggleSet } from '@/hooks/useToggleSet'

describe('useToggleSet', () => {
  it('initial state: has("x") returns false when nothing provided', () => {
    const { result } = renderHook(() => useToggleSet())
    const [set] = result.current
    expect(set.has('x')).toBe(false)
  })

  it('initial state reflects provided initial values', () => {
    const { result } = renderHook(() => useToggleSet(['a', 'b']))
    const [set] = result.current
    expect(set.has('a')).toBe(true)
    expect(set.has('b')).toBe(true)
  })

  it('after toggle("x"): has("x") returns true', () => {
    const { result } = renderHook(() => useToggleSet())
    act(() => {
      const [, toggle] = result.current
      toggle('x')
    })
    const [set] = result.current
    expect(set.has('x')).toBe(true)
  })

  it('after toggle("x") twice: has("x") returns false (removed)', () => {
    const { result } = renderHook(() => useToggleSet())
    act(() => {
      const [, toggle] = result.current
      toggle('x')
    })
    act(() => {
      const [, toggle] = result.current
      toggle('x')
    })
    const [set] = result.current
    expect(set.has('x')).toBe(false)
  })

  it('toggling "a" does not affect "b"', () => {
    const { result } = renderHook(() => useToggleSet(['b']))
    act(() => {
      const [, toggle] = result.current
      toggle('a')
    })
    const [set] = result.current
    expect(set.has('a')).toBe(true)
    expect(set.has('b')).toBe(true)
  })

  it('multiple IDs can all be in the set simultaneously', () => {
    const { result } = renderHook(() => useToggleSet())
    act(() => {
      const [, toggle] = result.current
      toggle('id-1')
    })
    act(() => {
      const [, toggle] = result.current
      toggle('id-2')
    })
    act(() => {
      const [, toggle] = result.current
      toggle('id-3')
    })
    const [set] = result.current
    expect(set.has('id-1')).toBe(true)
    expect(set.has('id-2')).toBe(true)
    expect(set.has('id-3')).toBe(true)
  })

  it('the returned Set is a new reference after each toggle (React state update)', () => {
    const { result } = renderHook(() => useToggleSet())
    const [setBeforeToggle] = result.current
    act(() => {
      const [, toggle] = result.current
      toggle('x')
    })
    const [setAfterToggle] = result.current
    expect(setAfterToggle).not.toBe(setBeforeToggle)
  })

  it('removing the only item leaves an empty set', () => {
    const { result } = renderHook(() => useToggleSet(['only']))
    act(() => {
      const [, toggle] = result.current
      toggle('only')
    })
    const [set] = result.current
    expect(set.size).toBe(0)
    expect(set.has('only')).toBe(false)
  })

  it('toggle function reference is stable (useCallback)', () => {
    const { result } = renderHook(() => useToggleSet())
    const [, toggleBefore] = result.current
    act(() => {
      const [, toggle] = result.current
      toggle('a')
    })
    const [, toggleAfter] = result.current
    expect(toggleBefore).toBe(toggleAfter)
  })
})
