import { createPortal } from 'react-dom'
import { forwardRef, useCallback, useEffect, useRef, useState } from 'react'
import { ChevronDownIcon } from '@heroicons/react/24/outline'

export interface SelectOption {
  value: string
  label: string
}

interface SelectInputProps {
  id?: string
  value: string
  onChange: (value: string) => void
  options: SelectOption[]
  disabled?: boolean
  /** Applied to the trigger button; defaults to 'input' to match the app's input style. */
  className?: string
  'aria-label'?: string
  'data-testid'?: string
}

/**
 * Custom select that renders its panel via a React portal so the dropdown can
 * never be clipped by a parent's overflow:hidden (e.g. inside modals).
 */
export const SelectInput = forwardRef<HTMLButtonElement, SelectInputProps>(
  function SelectInput({ id, value, onChange, options, disabled, className, ...rest }, ref) {
    const [open, setOpen] = useState(false)
    const [panelStyle, setPanelStyle] = useState<React.CSSProperties>({})
    const [highlighted, setHighlighted] = useState(-1)
    const buttonRef = useRef<HTMLButtonElement>(null)
    const panelRef = useRef<HTMLUListElement>(null)

    const selectedLabel = options.find(o => o.value === value)?.label ?? value

    const setRef = useCallback(
      (el: HTMLButtonElement | null) => {
        ;(buttonRef as React.MutableRefObject<HTMLButtonElement | null>).current = el
        if (typeof ref === 'function') ref(el)
        else if (ref) (ref as React.MutableRefObject<HTMLButtonElement | null>).current = el
      },
      [ref],
    )

    const openPanel = useCallback(() => {
      if (disabled) return
      const rect = buttonRef.current?.getBoundingClientRect()
      if (!rect) return
      setPanelStyle({
        position: 'fixed',
        top: rect.bottom + 4,
        left: rect.left,
        width: rect.width,
        zIndex: 9999,
      })
      setHighlighted(options.findIndex(o => o.value === value))
      setOpen(true)
    }, [disabled, options, value])

    // Close on outside click
    useEffect(() => {
      if (!open) return
      const handler = (e: MouseEvent) => {
        const t = e.target as Node
        if (!buttonRef.current?.contains(t) && !panelRef.current?.contains(t)) {
          setOpen(false)
        }
      }
      document.addEventListener('mousedown', handler)
      return () => document.removeEventListener('mousedown', handler)
    }, [open])

    // Keyboard navigation
    useEffect(() => {
      if (!open) return
      const handler = (e: KeyboardEvent) => {
        if (e.key === 'Escape') {
          setOpen(false)
          buttonRef.current?.focus()
        } else if (e.key === 'ArrowDown') {
          e.preventDefault()
          setHighlighted(h => Math.min(h + 1, options.length - 1))
        } else if (e.key === 'ArrowUp') {
          e.preventDefault()
          setHighlighted(h => Math.max(h - 1, 0))
        } else if ((e.key === 'Enter' || e.key === ' ') && highlighted >= 0) {
          e.preventDefault()
          onChange(options[highlighted].value)
          setOpen(false)
          buttonRef.current?.focus()
        }
      }
      document.addEventListener('keydown', handler)
      return () => document.removeEventListener('keydown', handler)
    }, [open, highlighted, options, onChange])

    return (
      <>
        <button
          ref={setRef}
          id={id}
          type="button"
          disabled={disabled}
          onClick={() => (open ? setOpen(false) : openPanel())}
          aria-haspopup="listbox"
          aria-expanded={open}
          className={`flex items-center justify-between gap-2 text-left ${className ?? 'input'}`}
          {...rest}
        >
          <span className="truncate">{selectedLabel}</span>
          <ChevronDownIcon
            className={`h-4 w-4 shrink-0 text-slate-400 transition-transform duration-150 ${open ? 'rotate-180' : ''}`}
          />
        </button>

        {open &&
          createPortal(
            <ul
              ref={panelRef}
              role="listbox"
              style={panelStyle}
              className="bg-white border border-slate-200 rounded-xl shadow-lg shadow-slate-200/60 max-h-60 overflow-y-auto py-1"
            >
              {options.map((opt, i) => (
                <li
                  key={opt.value}
                  role="option"
                  aria-selected={opt.value === value}
                  onMouseDown={e => {
                    e.preventDefault()
                    onChange(opt.value)
                    setOpen(false)
                    buttonRef.current?.focus()
                  }}
                  onMouseEnter={() => setHighlighted(i)}
                  className={`px-4 py-2.5 text-sm cursor-pointer select-none flex items-center gap-2 ${
                    i === highlighted ? 'bg-sky-50' : ''
                  } ${opt.value === value ? 'text-sky-700 font-medium' : 'text-slate-700'}`}
                >
                  <span className="w-4 shrink-0 text-center">
                    {opt.value === value ? '✓' : ''}
                  </span>
                  {opt.label}
                </li>
              ))}
            </ul>,
            document.body,
          )}
      </>
    )
  },
)
