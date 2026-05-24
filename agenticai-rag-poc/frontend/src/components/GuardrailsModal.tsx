import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ShieldCheckIcon,
  XMarkIcon,
  PlusIcon,
  TrashIcon,
  LockClosedIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
  BeakerIcon,
  PencilSquareIcon,
} from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import { guardrailsApi, extractErrorMessage } from '@/services/api'
import type {
  GuardrailRule,
  GuardrailRuleCreate,
  GuardrailRuleUpdate,
  GuardrailCheckResponse,
} from '@/types'

// ── helpers ──────────────────────────────────────────────────────────────────

type FilterType   = 'all' | GuardrailRule['type']
type FilterTarget = 'all' | GuardrailRule['target']
type FilterAction = 'all' | GuardrailRule['action']

const severityDot: Record<GuardrailRule['severity'], string> = {
  high:   'bg-rose-500',
  medium: 'bg-amber-400',
  low:    'bg-emerald-500',
}

const actionBadge: Record<GuardrailRule['action'], string> = {
  block:  'bg-rose-100 text-rose-700',
  flag:   'bg-amber-100 text-amber-700',
  redact: 'bg-slate-100 text-slate-600',
}

const typeBadge   = 'bg-sky-100 text-sky-700'
const targetBadge = 'bg-indigo-100 text-indigo-700'

// ── sub-components ────────────────────────────────────────────────────────────

function Badge({ className, children }: { className: string; children: React.ReactNode }) {
  return (
    <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ${className}`}>
      {children}
    </span>
  )
}

function SeverityDot({ severity }: { severity: GuardrailRule['severity'] }) {
  return (
    <span
      className={`inline-block h-2 w-2 rounded-full shrink-0 ${severityDot[severity]}`}
      title={`Severity: ${severity}`}
    />
  )
}

// ── AddRuleForm ───────────────────────────────────────────────────────────────

interface AddRuleFormProps {
  onSave: (rule: GuardrailRule) => void
  onCancel: () => void
}

function AddRuleForm({ onSave, onCancel }: AddRuleFormProps) {
  const [name, setName]             = useState('')
  const [description, setDesc]      = useState('')
  const [type, setType]             = useState<GuardrailRuleCreate['type']>('word')
  const [target, setTarget]         = useState<GuardrailRuleCreate['target']>('both')
  const [action, setAction]         = useState<GuardrailRuleCreate['action']>('block')
  const [severity, setSeverity]     = useState<GuardrailRuleCreate['severity']>('medium')
  const [words, setWords]           = useState('')
  const [keywords, setKeywords]     = useState('')
  const [pattern, setPattern]       = useState('')
  const [replacement, setReplacement] = useState('[REDACTED]')
  const [saving, setSaving]         = useState(false)

  const handleSubmit = useCallback(async () => {
    if (!name.trim()) { toast.error('Name is required.'); return }

    const payload: GuardrailRuleCreate = {
      name: name.trim(),
      description: description.trim() || undefined,
      type,
      target,
      action,
      severity,
    }

    if (type === 'word') {
      payload.words = words.split(',').map((w) => w.trim()).filter(Boolean)
    } else if (type === 'topic') {
      payload.keywords = keywords.split(',').map((k) => k.trim()).filter(Boolean)
    } else if (type === 'regex') {
      payload.pattern = pattern.trim()
      payload.replacement = replacement.trim()
    }

    setSaving(true)
    try {
      const created = await guardrailsApi.create(payload)
      onSave(created)
      toast.success('Rule created.')
    } catch (err) {
      toast.error(extractErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }, [name, description, type, target, action, severity, words, keywords, pattern, replacement, onSave])

  return (
    <div className="mt-4 rounded-xl border border-sky-200 bg-sky-50/60 p-4 space-y-3" data-testid="add-rule-form">
      <h3 className="text-sm font-semibold text-slate-800">New Rule</h3>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Name *</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Block profanity"
            maxLength={100}
            className="input text-sm"
            data-testid="add-rule-name"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Description</label>
          <input
            type="text"
            value={description}
            onChange={(e) => setDesc(e.target.value)}
            placeholder="Optional description"
            maxLength={200}
            className="input text-sm"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Type</label>
          <select
            value={type}
            onChange={(e) => setType(e.target.value as GuardrailRuleCreate['type'])}
            className="input text-sm"
            data-testid="add-rule-type"
          >
            <option value="word">Word</option>
            <option value="topic">Topic</option>
            <option value="regex">Regex</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Target</label>
          <select
            value={target}
            onChange={(e) => setTarget(e.target.value as GuardrailRuleCreate['target'])}
            className="input text-sm"
            data-testid="add-rule-target"
          >
            <option value="input">Input</option>
            <option value="output">Output</option>
            <option value="both">Both</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Action</label>
          <select
            value={action}
            onChange={(e) => setAction(e.target.value as GuardrailRuleCreate['action'])}
            className="input text-sm"
            data-testid="add-rule-action"
          >
            <option value="block">Block</option>
            <option value="flag">Flag</option>
            <option value="redact">Redact</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Severity</label>
          <select
            value={severity}
            onChange={(e) => setSeverity(e.target.value as GuardrailRuleCreate['severity'])}
            className="input text-sm"
            data-testid="add-rule-severity"
          >
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
        </div>
      </div>

      {/* Conditional fields */}
      {type === 'word' && (
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">
            Words (comma-separated)
          </label>
          <textarea
            value={words}
            onChange={(e) => setWords(e.target.value)}
            placeholder="bad, worse, awful"
            rows={2}
            className="input text-sm resize-none"
            data-testid="add-rule-words"
          />
        </div>
      )}
      {type === 'topic' && (
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">
            Keywords (comma-separated)
          </label>
          <textarea
            value={keywords}
            onChange={(e) => setKeywords(e.target.value)}
            placeholder="violence, harm, illegal"
            rows={2}
            className="input text-sm resize-none"
            data-testid="add-rule-keywords"
          />
        </div>
      )}
      {type === 'regex' && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Regex Pattern</label>
            <input
              type="text"
              value={pattern}
              onChange={(e) => setPattern(e.target.value)}
              placeholder="\b\d{4}-\d{4}-\d{4}-\d{4}\b"
              className="input text-sm font-mono"
              data-testid="add-rule-pattern"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Replacement</label>
            <input
              type="text"
              value={replacement}
              onChange={(e) => setReplacement(e.target.value)}
              placeholder="[REDACTED]"
              className="input text-sm"
              data-testid="add-rule-replacement"
            />
          </div>
        </div>
      )}

      <div className="flex justify-end gap-2 pt-1">
        <button onClick={onCancel} className="btn-secondary text-sm py-1.5" disabled={saving}>
          Cancel
        </button>
        <button
          onClick={handleSubmit}
          disabled={saving}
          className="btn-primary text-sm py-1.5 disabled:opacity-50"
          data-testid="add-rule-save"
        >
          {saving ? 'Saving…' : 'Save Rule'}
        </button>
      </div>
    </div>
  )
}

// ── EditRuleForm ──────────────────────────────────────────────────────────────

interface EditRuleFormProps {
  rule: GuardrailRule
  onSave: (updated: GuardrailRule) => void
  onCancel: () => void
}

function EditRuleForm({ rule, onSave, onCancel }: EditRuleFormProps) {
  const [name, setName]               = useState(rule.name)
  const [description, setDesc]        = useState(rule.description ?? '')
  const [action, setAction]           = useState<GuardrailRule['action']>(rule.action)
  const [severity, setSeverity]       = useState<GuardrailRule['severity']>(rule.severity)
  const [words, setWords]             = useState((rule.words ?? []).join(', '))
  const [keywords, setKeywords]       = useState((rule.keywords ?? []).join(', '))
  const [pattern, setPattern]         = useState(rule.pattern ?? '')
  const [replacement, setReplacement] = useState(rule.replacement ?? '[REDACTED]')
  const [saving, setSaving]           = useState(false)

  const handleSubmit = useCallback(async () => {
    if (!name.trim()) { toast.error('Name is required.'); return }

    const payload: GuardrailRuleUpdate = {
      name: name.trim(),
      description: description.trim() || undefined,
      action,
      severity,
    }

    if (rule.type === 'word') {
      payload.words = words.split(',').map((w) => w.trim()).filter(Boolean)
    } else if (rule.type === 'topic') {
      payload.keywords = keywords.split(',').map((k) => k.trim()).filter(Boolean)
    } else if (rule.type === 'regex') {
      payload.pattern = pattern.trim()
      payload.replacement = replacement.trim()
    }

    setSaving(true)
    try {
      const updated = await guardrailsApi.update(rule.id, payload)
      onSave(updated)
      toast.success('Rule updated.')
    } catch (err) {
      toast.error(extractErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }, [name, description, action, severity, words, keywords, pattern, replacement, rule, onSave])

  return (
    <div className="py-3 px-4 bg-sky-50/60 border-b border-sky-100 space-y-3" data-testid={`edit-rule-form-${rule.id}`}>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Name *</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={100}
            className="input text-sm"
            data-testid={`edit-rule-name-${rule.id}`}
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Description</label>
          <input
            type="text"
            value={description}
            onChange={(e) => setDesc(e.target.value)}
            maxLength={200}
            className="input text-sm"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Action</label>
          <select
            value={action}
            onChange={(e) => setAction(e.target.value as GuardrailRule['action'])}
            className="input text-sm"
            data-testid={`edit-rule-action-${rule.id}`}
          >
            <option value="block">Block</option>
            <option value="flag">Flag</option>
            <option value="redact">Redact</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Severity</label>
          <select
            value={severity}
            onChange={(e) => setSeverity(e.target.value as GuardrailRule['severity'])}
            className="input text-sm"
            data-testid={`edit-rule-severity-${rule.id}`}
          >
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
        </div>
      </div>

      {rule.type === 'word' && (
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Words (comma-separated)</label>
          <textarea
            value={words}
            onChange={(e) => setWords(e.target.value)}
            rows={2}
            className="input text-sm resize-none"
            data-testid={`edit-rule-words-${rule.id}`}
          />
        </div>
      )}
      {rule.type === 'topic' && (
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Keywords (comma-separated)</label>
          <textarea
            value={keywords}
            onChange={(e) => setKeywords(e.target.value)}
            rows={2}
            className="input text-sm resize-none"
            data-testid={`edit-rule-keywords-${rule.id}`}
          />
        </div>
      )}
      {rule.type === 'regex' && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Regex Pattern</label>
            <input
              type="text"
              value={pattern}
              onChange={(e) => setPattern(e.target.value)}
              className="input text-sm font-mono"
              data-testid={`edit-rule-pattern-${rule.id}`}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Replacement</label>
            <input
              type="text"
              value={replacement}
              onChange={(e) => setReplacement(e.target.value)}
              className="input text-sm"
              data-testid={`edit-rule-replacement-${rule.id}`}
            />
          </div>
        </div>
      )}

      <div className="flex justify-end gap-2 pt-1">
        <button onClick={onCancel} className="btn-secondary text-sm py-1.5" disabled={saving}>
          Cancel
        </button>
        <button
          onClick={handleSubmit}
          disabled={saving}
          className="btn-primary text-sm py-1.5 disabled:opacity-50"
          data-testid={`edit-rule-save-${rule.id}`}
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </div>
  )
}

// ── RuleRow ───────────────────────────────────────────────────────────────────

interface RuleRowProps {
  rule: GuardrailRule
  readOnly: boolean
  isEditing: boolean
  onToggle: (id: string, enabled: boolean) => void
  onDelete: (id: string) => void
  onEdit: (id: string) => void
  onEditSave: (updated: GuardrailRule) => void
  onEditCancel: () => void
}

function RuleRow({ rule, readOnly, isEditing, onToggle, onDelete, onEdit, onEditSave, onEditCancel }: RuleRowProps) {
  if (isEditing) {
    return <EditRuleForm rule={rule} onSave={onEditSave} onCancel={onEditCancel} />
  }

  return (
    <div className="flex items-center gap-3 py-3 px-4 hover:bg-slate-50 transition-colors" data-testid={`rule-row-${rule.id}`}>
      {/* Toggle switch */}
      <label className="relative inline-flex items-center shrink-0" title={readOnly ? 'Read-only' : rule.enabled ? 'Disable rule' : 'Enable rule'}>
        <input
          type="checkbox"
          checked={rule.enabled}
          onChange={() => !readOnly && onToggle(rule.id, rule.enabled)}
          disabled={readOnly}
          className="sr-only peer"
          aria-label={`Toggle ${rule.name}`}
          data-testid={`toggle-${rule.id}`}
        />
        <div className={`w-9 h-5 rounded-full transition-colors peer-checked:bg-sky-500 bg-slate-200 ${readOnly ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'} peer-focus:ring-2 peer-focus:ring-sky-400/50`} />
        <div className="absolute left-0.5 top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform peer-checked:translate-x-4 pointer-events-none" />
      </label>

      {/* Badges */}
      <div className="flex items-center gap-1.5 shrink-0">
        <Badge className={typeBadge}>{rule.type}</Badge>
        <Badge className={targetBadge}>{rule.target}</Badge>
        <Badge className={actionBadge[rule.action]}>{rule.action}</Badge>
      </div>

      {/* Severity + name */}
      <div className="flex items-center gap-2 min-w-0 flex-1">
        <SeverityDot severity={rule.severity} />
        {rule.builtin && (
          <>
            <LockClosedIcon className="h-3.5 w-3.5 text-slate-400 shrink-0" title="Built-in rule — cannot be deleted" />
            <span className="text-xs text-slate-400 italic" title="Built-in rules cannot be deleted or reconfigured. Only enable/disable is allowed.">
              Built-in
            </span>
          </>
        )}
        <div className="min-w-0">
          <p className="text-sm font-medium text-slate-800 truncate">{rule.name}</p>
          {rule.description && (
            <p className="text-xs text-slate-500 truncate">{rule.description}</p>
          )}
        </div>
      </div>

      {/* Edit */}
      {!rule.builtin && !readOnly && (
        <button
          onClick={() => onEdit(rule.id)}
          className="btn-tool h-7 px-1.5"
          aria-label={`Edit ${rule.name}`}
          title="Edit rule"
          data-testid={`edit-${rule.id}`}
        >
          <PencilSquareIcon className="h-3.5 w-3.5" />
        </button>
      )}

      {/* Delete */}
      {!rule.builtin && !readOnly && (
        <button
          onClick={() => onDelete(rule.id)}
          className="shrink-0 p-1 text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors rounded"
          aria-label={`Delete rule ${rule.name}`}
          data-testid={`delete-${rule.id}`}
        >
          <TrashIcon className="h-4 w-4" />
        </button>
      )}
    </div>
  )
}

// ── TestTab ───────────────────────────────────────────────────────────────────

function TestTab() {
  const [text, setText]       = useState('')
  const [target, setTarget]   = useState<'input' | 'output' | 'both'>('input')
  const [running, setRunning] = useState(false)
  const [result, setResult]   = useState<GuardrailCheckResponse | null>(null)

  const handleRun = useCallback(async () => {
    if (!text.trim()) { toast.error('Enter some text to test.'); return }
    setRunning(true)
    setResult(null)
    try {
      const res = await guardrailsApi.check({ text: text.trim(), target })
      setResult(res)
    } catch (err) {
      toast.error(extractErrorMessage(err))
    } finally {
      setRunning(false)
    }
  }, [text, target])

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-slate-600 mb-1.5">
          Text to test
        </label>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Enter text to test against guardrails…"
          maxLength={2000}
          rows={5}
          className="input text-sm resize-none w-full"
          data-testid="test-text-input"
        />
        <p className="text-xs text-slate-400 text-right mt-0.5">{text.length}/2000</p>
      </div>

      <div className="flex items-center gap-4">
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Target</label>
          <select
            value={target}
            onChange={(e) => setTarget(e.target.value as typeof target)}
            className="input text-sm"
            data-testid="test-target-select"
          >
            <option value="input">Input</option>
            <option value="output">Output</option>
            <option value="both">Both</option>
          </select>
        </div>
        <div className="flex-1 flex items-end justify-end">
          <button
            onClick={handleRun}
            disabled={running || !text.trim()}
            className="btn-primary text-sm py-2 disabled:opacity-50"
            data-testid="run-test-btn"
          >
            {running ? 'Running…' : 'Run Test'}
          </button>
        </div>
      </div>

      {result && (
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 space-y-3" data-testid="test-result">
          {/* Status badges */}
          <div className="flex flex-wrap items-center gap-2">
            {result.allowed ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 border border-emerald-200 px-3 py-1 text-sm font-medium text-emerald-700">
                <CheckCircleIcon className="h-4 w-4" />
                Allowed
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 border border-rose-200 px-3 py-1 text-sm font-medium text-rose-700">
                <ExclamationCircleIcon className="h-4 w-4" />
                Blocked
              </span>
            )}
            {result.flagged && (
              <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 border border-amber-200 px-3 py-1 text-sm font-medium text-amber-700">
                Flagged
              </span>
            )}
          </div>

          {/* Redacted output */}
          {result.modified_text && result.modified_text !== text && (
            <div>
              <p className="text-xs font-medium text-slate-600 mb-1">Redacted output:</p>
              <pre className="text-sm bg-white border border-slate-200 rounded-lg p-3 overflow-auto whitespace-pre-wrap break-words font-mono text-slate-700">
                {result.modified_text}
              </pre>
            </div>
          )}

          {/* Violations */}
          {result.violations.length > 0 && (
            <div>
              <p className="text-xs font-medium text-slate-600 mb-2">Violations ({result.violations.length}):</p>
              <ul className="space-y-1.5">
                {result.violations.map((v) => (
                  <li key={v.rule_id} className="flex items-center gap-2 text-sm">
                    <SeverityDot severity={v.severity as GuardrailRule['severity']} />
                    <span className="font-medium text-slate-800">{v.rule_name}</span>
                    <Badge className={actionBadge[v.action as GuardrailRule['action']] ?? 'bg-slate-100 text-slate-600'}>
                      {v.action}
                    </Badge>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── GuardrailsModal (main) ────────────────────────────────────────────────────

interface Props {
  open: boolean
  onClose: () => void
  isGuest?: boolean
}

export default function GuardrailsModal({ open, onClose, isGuest = false }: Props) {
  const [rules, setRules]               = useState<GuardrailRule[]>([])
  const [loading, setLoading]           = useState(false)
  const [tab, setTab]                   = useState<'rules' | 'test'>('rules')
  const [filterType, setFilterType]     = useState<FilterType>('all')
  const [filterTarget, setFilterTarget] = useState<FilterTarget>('all')
  const [filterAction, setFilterAction] = useState<FilterAction>('all')
  const [showAddForm, setShowAddForm]   = useState(false)
  const [editingId, setEditingId]       = useState<string | null>(null)

  // Load rules when modal opens
  useEffect(() => {
    if (!open) return
    setLoading(true)
    guardrailsApi.list()
      .then(setRules)
      .catch(() => toast.error('Could not load guardrail rules.'))
      .finally(() => setLoading(false))
    setTab('rules')
    setShowAddForm(false)
    setEditingId(null)
    setFilterType('all')
    setFilterTarget('all')
    setFilterAction('all')
  }, [open])

  // Close on Escape
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  const filteredRules = useMemo(() => rules.filter((r) => {
    if (filterType !== 'all' && r.type !== filterType) return false
    if (filterTarget !== 'all' && r.target !== filterTarget) return false
    if (filterAction !== 'all' && r.action !== filterAction) return false
    return true
  }), [rules, filterType, filterTarget, filterAction])

  const handleToggle = useCallback(async (id: string, currentEnabled: boolean) => {
    try {
      const result = await guardrailsApi.update(id, { enabled: !currentEnabled })
      setRules((prev) => prev.map((r) => (r.id === id ? result : r)))
    } catch (err) {
      toast.error(extractErrorMessage(err))
    }
  }, [])

  const handleDelete = useCallback(async (id: string) => {
    try {
      await guardrailsApi.remove(id)
      setRules((prev) => prev.filter((r) => r.id !== id))
      toast.success('Rule deleted.')
    } catch (err) {
      toast.error(extractErrorMessage(err))
    }
  }, [])

  const handleRuleCreated = useCallback((rule: GuardrailRule) => {
    setRules((prev) => [...prev, rule])
    setShowAddForm(false)
  }, [])

  const handleEditSave = useCallback((updated: GuardrailRule) => {
    setRules((prev) => prev.map((r) => (r.id === updated.id ? updated : r)))
    setEditingId(null)
  }, [])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-slate-900/50 backdrop-blur-sm overflow-y-auto py-8 px-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
      role="dialog"
      aria-modal="true"
      aria-labelledby="guardrails-title"
    >
      <div className="bg-white border border-slate-200 rounded-2xl shadow-xl shadow-slate-300/40 w-full max-w-2xl overflow-hidden flex flex-col">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
          <div className="flex items-center gap-2">
            <ShieldCheckIcon className="h-5 w-5 text-sky-600" />
            <h2 id="guardrails-title" className="text-base font-semibold text-slate-900">
              Content Guardrails
            </h2>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 transition-colors"
            aria-label="Close guardrails"
            data-testid="guardrails-close"
          >
            <XMarkIcon className="h-5 w-5" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-slate-200 px-6">
          <button
            onClick={() => setTab('rules')}
            className={`py-3 px-1 mr-6 text-sm font-medium border-b-2 transition-colors ${
              tab === 'rules'
                ? 'border-sky-600 text-sky-700'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
            data-testid="tab-rules"
          >
            Rules
            {rules.length > 0 && (
              <span className="ml-2 inline-flex items-center justify-center rounded-full bg-slate-100 border border-slate-200 px-2 py-0.5 text-xs font-medium text-slate-500">
                {rules.length}
              </span>
            )}
          </button>
          {!isGuest && (
            <button
              onClick={() => setTab('test')}
              className={`py-3 px-1 text-sm font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
                tab === 'test'
                  ? 'border-sky-600 text-sky-700'
                  : 'border-transparent text-slate-500 hover:text-slate-700'
              }`}
              data-testid="tab-test"
            >
              <BeakerIcon className="h-4 w-4" />
              Test
            </button>
          )}
        </div>

        {/* Body */}
        <div className="px-6 py-5 flex-1 overflow-y-auto min-h-0 max-h-[60vh]">
          {tab === 'rules' && (
            <div className="space-y-4">
              {/* Guest read-only notice */}
              {isGuest && (
                <div className="flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-700">
                  <LockClosedIcon className="h-3.5 w-3.5 shrink-0" />
                  <span>Guest mode — view only. Sign in to manage guardrail rules.</span>
                </div>
              )}

              {/* Filter bar */}
              <div className="flex flex-wrap items-center gap-2">
                <select
                  value={filterType}
                  onChange={(e) => setFilterType(e.target.value as FilterType)}
                  className="input text-sm py-1.5 w-auto"
                  aria-label="Filter by type"
                  data-testid="filter-type"
                >
                  <option value="all">All types</option>
                  <option value="word">Word</option>
                  <option value="topic">Topic</option>
                  <option value="regex">Regex</option>
                </select>
                <select
                  value={filterTarget}
                  onChange={(e) => setFilterTarget(e.target.value as FilterTarget)}
                  className="input text-sm py-1.5 w-auto"
                  aria-label="Filter by target"
                  data-testid="filter-target"
                >
                  <option value="all">All targets</option>
                  <option value="input">Input</option>
                  <option value="output">Output</option>
                  <option value="both">Both</option>
                </select>
                <select
                  value={filterAction}
                  onChange={(e) => setFilterAction(e.target.value as FilterAction)}
                  className="input text-sm py-1.5 w-auto"
                  aria-label="Filter by action"
                  data-testid="filter-action"
                >
                  <option value="all">All actions</option>
                  <option value="block">Block</option>
                  <option value="flag">Flag</option>
                  <option value="redact">Redact</option>
                </select>
                <span className="text-xs text-slate-400 ml-auto">
                  {filteredRules.length} of {rules.length} rule{rules.length !== 1 ? 's' : ''}
                </span>
              </div>

              {/* Rule list */}
              {loading ? (
                <div className="flex items-center justify-center gap-3 py-10" data-testid="rules-loading">
                  <div className="w-4 h-4 rounded-full border-2 border-sky-500 border-t-transparent animate-spin" />
                  <span className="text-sm text-slate-400">Loading rules…</span>
                </div>
              ) : filteredRules.length === 0 ? (
                <div className="py-10 text-center text-sm text-slate-400" data-testid="rules-empty">
                  {rules.length === 0 ? 'No guardrail rules configured.' : 'No rules match the current filters.'}
                </div>
              ) : (
                <div className="divide-y divide-slate-100 rounded-xl border border-slate-200 overflow-hidden">
                  {filteredRules.map((rule) => (
                    <RuleRow
                      key={rule.id}
                      rule={rule}
                      readOnly={!!isGuest}
                      isEditing={editingId === rule.id}
                      onToggle={handleToggle}
                      onDelete={handleDelete}
                      onEdit={setEditingId}
                      onEditSave={handleEditSave}
                      onEditCancel={() => setEditingId(null)}
                    />
                  ))}
                </div>
              )}

              {/* Add rule button + form */}
              {!isGuest && (
                <>
                  {!showAddForm && (
                    <button
                      onClick={() => setShowAddForm(true)}
                      className="flex items-center gap-2 btn-secondary text-sm w-full justify-center"
                      data-testid="add-rule-btn"
                    >
                      <PlusIcon className="h-4 w-4" />
                      Add Rule
                    </button>
                  )}
                  {showAddForm && (
                    <AddRuleForm
                      onSave={handleRuleCreated}
                      onCancel={() => setShowAddForm(false)}
                    />
                  )}
                </>
              )}
            </div>
          )}

          {tab === 'test' && !isGuest && <TestTab />}
        </div>

        {/* Footer */}
        <div className="flex justify-end px-6 py-4 border-t border-slate-200 bg-slate-50">
          <button onClick={onClose} className="btn-secondary text-sm" data-testid="guardrails-close-footer">
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
