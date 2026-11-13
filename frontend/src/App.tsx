import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, AlertTriangle, ArrowDownToLine, AudioLines, Check, CheckCircle2,
  ChevronDown, ChevronRight, Clock3, FileCheck2, FileText, FolderOpen,
  Gauge, HelpCircle, ListChecks, LoaderCircle, LockKeyhole,
  MessageSquareText, Plus, Search, ShieldCheck, Sparkles, Upload,
  MapPin, X, XCircle, Zap, CalendarDays, UserRound, History, ClipboardList,
} from 'lucide-react'

type Tab = 'exercises' | 'overview' | 'objectives' | 'evidence' | 'timeline' | 'findings' | 'actions' | 'reports'
type ReportDownloadState = { status: 'idle' | 'preparing' | 'started' | 'failed'; message?: string; filename?: string }
type Source = { id: string; filename: string; kind: string; mime_type: string; sha256: string; provenance: Record<string, unknown>; scan_status: string; observation_count: number }
type Observation = { id: string; source_id: string; source_filename: string; text: string; event_time_raw: string | null; event_time_normalized: string | null; time_confidence: string; source_locator: string; observation_type: string; extraction_method: string; recognition_confidence: number | null }
type Support = { source_id: string; source_filename: string; observation_id: string; source_locator: string; text: string; event_time_normalized: string | null; time_confidence: string }
type Finding = { id: string; code: string; title: string; category: 'strength' | 'improvement'; objective_id: string | null; observation: string; interpretation: string; evidence_ids: string[]; evidence_labels: string[]; confidence: string; status: string; review_note: string; reviewer: string | null; supporting_evidence: Support[] }
type Action = { id: string; finding_id: string; finding_title: string; title: string; evidence_ids: string[]; owner: string | null; priority: string; due_date: string | null; acceptance_criteria: string; status: string; reviewer_decision: string; reviewer: string | null; closure_evidence: string }
type Objective = { id: string; text: string; evaluation_rule?: Record<string, unknown> }
type ObjectiveDraft = {
  id: string
  text: string
  ruleType: 'none' | 'elapsed_time' | 'reported_duration' | 'event_presence' | 'required_field'
  thresholdValue: string
  thresholdUnit: 'seconds' | 'minutes' | 'hours'
  startTerms: string
  completionTerms: string
  completionClaimTerms: string
  claimTerms: string
  terms: string
  missingTerms: string
  presentTerms: string
  ruleMetadata: Record<string, unknown>
}
type ObjectiveAssessment = { objective_id: string | null; objective_text: string; state: string; rule_type: string | null; threshold_seconds: number | null; elapsed_seconds: number[]; evidence: { observation_id: string; source_id: string; source_locator: string; source_wording: string; timestamp: string | null; time_confidence: string }[]; unknowns: string[]; conflicts: string[] }
type Exercise = { id: string; title: string; scenario: string; exercise_date: string; duration_minutes: number; objectives: Objective[]; criteria: string[]; evaluator_roles: string[]; participants: string[]; expected_milestones: { id: string; expected: string; objective_id: string }[]; finding_count?: number; action_count?: number }
type AuditEvent = { actor: string; action: string; object_id: string; details: Record<string, unknown>; created_at: string }
type Detail = { exercise: Exercise; objective_assessments: ObjectiveAssessment[]; analysis_locked: boolean; sources: Source[]; timeline: Observation[]; timeline_conflicts: { observation_id: string; source_id: string; source_filename: string; source_locator: string; description: string }[]; findings: Finding[]; actions: Action[]; audit_events: AuditEvent[] }
type Identity = { id: string; username: string; name: string; role: 'admin' | 'evaluator' | 'reviewer' | 'viewer'; organization_id: string }
type AccessGrant = { user_id: string; username: string; name: string; role: Identity['role'] }
type Capabilities = { asr: { available: boolean; package_version: string | null; model_path_configured: boolean; note: string }; analysis: { mode: string; cloud_api_required: boolean }; review: { required_identity: boolean; review_roles: string[] }; synthetic_demo_seed_enabled?: boolean }
type ReviewTarget = { kind: 'finding'; record: Finding; decision: 'approved' | 'rejected' } | { kind: 'action'; record: Action; decision: 'approved' | 'rejected' }

let csrfTokenValue = ''
let lastOutsideDialogFocus: HTMLElement | null = null

function useAccessibleDialog<T extends HTMLElement>(onClose: () => void) {
  const dialogRef = useRef<T>(null)
  const closeRef = useRef(onClose)
  closeRef.current = onClose

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    const activeElement = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const previousFocus =
      activeElement && activeElement !== document.body && !dialog.contains(activeElement)
        ? activeElement
        : lastOutsideDialogFocus
    const selector = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])'
    const focusable = () => Array.from(dialog.querySelectorAll<HTMLElement>(selector)).filter(item => item.getAttribute('aria-hidden') !== 'true')
    const controls = focusable()
    ;(controls[0] || dialog).focus()

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        closeRef.current()
        return
      }
      if (event.key !== 'Tab') return
      const current = focusable()
      if (!current.length) {
        event.preventDefault()
        dialog.focus()
        return
      }
      const first = current[0]
      const last = current[current.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      previousFocus?.focus()
    }
  }, [])

  return dialogRef
}

const toTermText = (rule: Record<string, unknown> | undefined, key: string) => Array.isArray(rule?.[key]) ? (rule?.[key] as unknown[]).filter((item): item is string => typeof item === 'string').join('; ') : ''

function thresholdPresentation(seconds: number): Pick<ObjectiveDraft, 'thresholdValue' | 'thresholdUnit'> {
  if (seconds !== 0 && seconds % 3600 === 0) return { thresholdValue: String(seconds / 3600), thresholdUnit: 'hours' }
  if (seconds !== 0 && seconds % 60 === 0) return { thresholdValue: String(seconds / 60), thresholdUnit: 'minutes' }
  return { thresholdValue: String(seconds), thresholdUnit: 'seconds' }
}

function objectiveToDraft(objective: Objective, index: number): ObjectiveDraft {
  const rule = objective.evaluation_rule
  const knownRuleFields = new Set(['type', 'threshold_seconds', 'start_terms', 'completion_terms', 'completion_claim_terms', 'claim_terms', 'terms', 'missing_terms', 'present_terms'])
  const threshold = typeof rule?.threshold_seconds === 'number' ? thresholdPresentation(rule.threshold_seconds) : { thresholdValue: '', thresholdUnit: 'minutes' as const }
  return {
    id: objective.id || `OBJ-${String(index + 1).padStart(2, '0')}`,
    text: objective.text || '',
    ruleType: rule?.type === 'elapsed_time' || rule?.type === 'reported_duration' || rule?.type === 'event_presence' || rule?.type === 'required_field' ? rule.type : 'none',
    ...threshold,
    startTerms: toTermText(rule, 'start_terms'),
    completionTerms: toTermText(rule, 'completion_terms'),
    completionClaimTerms: toTermText(rule, 'completion_claim_terms'),
    claimTerms: toTermText(rule, 'claim_terms'),
    terms: toTermText(rule, 'terms'),
    missingTerms: toTermText(rule, 'missing_terms'),
    presentTerms: toTermText(rule, 'present_terms'),
    ruleMetadata: Object.fromEntries(Object.entries(rule || {}).filter(([key]) => !knownRuleFields.has(key))),
  }
}

function termsFromText(value: string): string[] {
  return value.split(';').map(term => term.trim()).filter(Boolean)
}

function draftToObjective(draft: ObjectiveDraft): Objective {
  const evaluation_rule: Record<string, unknown> | undefined = draft.ruleType === 'none' ? undefined : draft.ruleType === 'elapsed_time'
    ? {
        ...draft.ruleMetadata,
        type: 'elapsed_time',
        ...(draft.thresholdValue.trim() ? { threshold_seconds: Math.round(Number(draft.thresholdValue) * ({ seconds: 1, minutes: 60, hours: 3600 }[draft.thresholdUnit])) } : {}),
        start_terms: termsFromText(draft.startTerms), completion_terms: termsFromText(draft.completionTerms),
        completion_claim_terms: termsFromText(draft.completionClaimTerms),
      }
    : draft.ruleType === 'reported_duration'
      ? { ...draft.ruleMetadata, type: 'reported_duration', start_terms: termsFromText(draft.startTerms), completion_terms: termsFromText(draft.completionTerms), claim_terms: termsFromText(draft.claimTerms) }
      : draft.ruleType === 'event_presence'
        ? { ...draft.ruleMetadata, type: 'event_presence', terms: termsFromText(draft.terms) }
        : { ...draft.ruleMetadata, type: 'required_field', missing_terms: termsFromText(draft.missingTerms), present_terms: termsFromText(draft.presentTerms) }
  return { id: draft.id.trim(), text: draft.text.trim(), ...(evaluation_rule ? { evaluation_rule } : {}) }
}

function objectiveRuleSummary(objective: Objective): string {
  const rule = objective.evaluation_rule
  if (!rule || typeof rule.type !== 'string') return 'No measurable success criteria configured yet.'
  const phrases = (key: string) => toTermText(rule, key).split(';').map(item => item.trim()).filter(Boolean)
  if (rule.type === 'elapsed_time') {
    const parts: string[] = []
    if (typeof rule.threshold_seconds === 'number') parts.push(`Target time: ${formatDuration(rule.threshold_seconds)}`)
    const start = phrases('start_terms')
    const complete = phrases('completion_terms')
    if (start.length) parts.push(`Start evidence: ${start.join(', ')}`)
    if (complete.length) parts.push(`Completion evidence: ${complete.join(', ')}`)
    const claims = phrases('completion_claim_terms')
    if (claims.length) parts.push(`Reported completion: ${claims.join(', ')}`)
    return parts.length ? parts.join(' · ') : 'Time target needs more detail.'
  }
  if (rule.type === 'reported_duration') {
    const parts = [phrases('start_terms').length ? `Start: ${phrases('start_terms').join(', ')}` : '', phrases('completion_terms').length ? `Completion: ${phrases('completion_terms').join(', ')}` : '', phrases('claim_terms').length ? `Reported duration: ${phrases('claim_terms').join(', ')}` : ''].filter(Boolean)
    return parts.length ? parts.join(' · ') : 'Add start, completion, and reported duration phrases.'
  }
  if (rule.type === 'event_presence') return phrases('terms').length ? `Evidence should include: ${phrases('terms').join(', ')}` : 'Add a phrase evaluators can look for in the source records.'
  const missing = phrases('missing_terms')
  const present = phrases('present_terms')
  return [missing.length ? `Missing: ${missing.join(', ')}` : '', present.length ? `Present: ${present.join(', ')}` : ''].filter(Boolean).join(' · ') || 'Add phrases that state whether the field is present or missing.'
}

function formatDuration(seconds: number): string {
  if (seconds !== 0 && seconds % 3600 === 0) return `${seconds / 3600} ${seconds === 3600 ? 'hour' : 'hours'}`
  if (seconds !== 0 && seconds % 60 === 0) return `${seconds / 60} ${seconds === 60 ? 'minute' : 'minutes'}`
  return `${seconds} ${seconds === 1 ? 'second' : 'seconds'}`
}

function validateObjectiveDrafts(drafts: ObjectiveDraft[]): string[] {
  const errors: string[] = []
  const ids = new Set<string>()
  drafts.forEach((draft, index) => {
    const label = `Objective ${index + 1}`
    const id = draft.id.trim()
    if (id.length < 1 || !/^[\p{L}\p{N}_-]+$/u.test(id)) errors.push(`${label}: use letters, numbers, hyphens, or underscores for the ID.`)
    else if (ids.has(id)) errors.push(`${label}: objective IDs must be unique.`)
    ids.add(id)
    if (draft.text.trim().length < 4) errors.push(`${label}: add a description of at least 4 characters.`)
    if (draft.ruleType === 'elapsed_time') {
      const seconds = Number(draft.thresholdValue) * ({ seconds: 1, minutes: 60, hours: 3600 }[draft.thresholdUnit])
      if (!draft.thresholdValue.trim() || !Number.isFinite(seconds) || seconds < 0 || !Number.isInteger(seconds)) errors.push(`${label}: enter a target time that equals a whole number of seconds.`)
      if (!termsFromText(draft.startTerms).length || !termsFromText(draft.completionTerms).length) errors.push(`${label}: add phrases that identify the start and completion evidence.`)
    }
    if (draft.ruleType === 'reported_duration' && (!termsFromText(draft.startTerms).length || !termsFromText(draft.completionTerms).length || !termsFromText(draft.claimTerms).length)) errors.push(`${label}: reported duration needs start, completion, and stated-duration phrases.`)
    if (draft.ruleType === 'event_presence' && !termsFromText(draft.terms).length) errors.push(`${label}: add at least one phrase to look for in source records.`)
    if (draft.ruleType === 'required_field' && !termsFromText(draft.missingTerms).length && !termsFromText(draft.presentTerms).length) errors.push(`${label}: add a phrase for a present or missing field.`)
  })
  return errors
}

function ObjectiveEditor({ value, onChange, onClose, onSubmit, busy, errorMessage }: { value: ObjectiveDraft[]; onChange: (value: ObjectiveDraft[]) => void; onClose: () => void; onSubmit: () => void; busy: boolean; errorMessage: string }) {
  const dialogRef = useAccessibleDialog<HTMLElement>(onClose)
  const [attempted, setAttempted] = useState(false)
  const errors = attempted ? validateObjectiveDrafts(value) : []
  const update = (index: number, field: keyof ObjectiveDraft, nextValue: string) => onChange(value.map((draft, draftIndex) => draftIndex === index ? { ...draft, [field]: nextValue } : draft))
  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    setAttempted(true)
    if (validateObjectiveDrafts(value).length === 0) onSubmit()
  }
  return <div className="modal-shade"><section ref={dialogRef} className="create-modal objective-editor" role="dialog" aria-modal="true" aria-labelledby="objectives-heading" tabIndex={-1}><form noValidate onSubmit={submit}>
    <div className="modal-head"><div className="modal-file-icon"><Check size={19} /></div><div><span>OBJECTIVE SETUP</span><h2 id="objectives-heading">Define what success looks like</h2></div><button type="button" className="icon-button" onClick={onClose} aria-label="Close objective editor"><X size={18} /></button></div>
    <div className="create-form objective-draft-list">
      <p className="objective-editor-intro">Describe the intended outcome, then choose what the source records must show. Each objective stays linked to this exercise.</p>
      {errorMessage && <div className="form-error-summary" role="alert">{errorMessage}</div>}
      {errors.length > 0 && <div className="form-error-summary" role="alert">Review these details before saving: {errors.join(' ')}</div>}
      {value.map((draft, index) => <article className="objective-draft-card" key={`${index}-${draft.id}`}>
        <div className="objective-draft-head"><span className="objective-number">{String(index + 1).padStart(2, '0')}</span><strong>Objective {index + 1}</strong><button type="button" className="text-link objective-remove" onClick={() => onChange(value.filter((_, itemIndex) => itemIndex !== index))} aria-label={`Remove objective ${index + 1}`}>Remove</button></div>
        <div className="objective-edit-grid">
          <label className="objective-id-field"><span>OBJECTIVE ID</span><input value={draft.id} maxLength={80} onChange={event => update(index, 'id', event.target.value)} aria-invalid={attempted && (!draft.id.trim() || !/^[\p{L}\p{N}_-]+$/u.test(draft.id.trim()))} /><small>Short label used to reference this target.</small></label>
          <label className="objective-description-field"><span>DESCRIPTION</span><textarea rows={2} value={draft.text} maxLength={2000} onChange={event => update(index, 'text', event.target.value)} placeholder="What should participants accomplish?" aria-invalid={attempted && draft.text.trim().length < 4} /><small>Describe the expected outcome in plain language.</small></label>
          <label className="objective-rule-select"><span>SUCCESS CRITERIA</span><select value={draft.ruleType} onChange={event => update(index, 'ruleType', event.target.value as ObjectiveDraft['ruleType'])}><option value="none">No measurable criteria yet</option><option value="elapsed_time">Complete within a target time</option><option value="event_presence">A specific event is recorded</option><option value="required_field">A required item is present or missing</option><option value="reported_duration">A reported duration matches the record</option></select><small>Choose how the source record can support this objective.</small></label>
          {draft.ruleType === 'elapsed_time' && <>
            <label className="threshold-field"><span>TARGET TIME</span><div className="threshold-input"><input type="number" min="0" step="any" value={draft.thresholdValue} onChange={event => update(index, 'thresholdValue', event.target.value)} aria-label={`Objective ${index + 1} target time`} /><select value={draft.thresholdUnit} onChange={event => update(index, 'thresholdUnit', event.target.value as ObjectiveDraft['thresholdUnit'])} aria-label={`Objective ${index + 1} target time unit`}><option value="seconds">seconds</option><option value="minutes">minutes</option><option value="hours">hours</option></select></div><small>Use seconds, minutes, or hours. Values are saved exactly in whole seconds.</small></label>
            <label><span>START EVENT PHRASE(S)</span><textarea rows={2} value={draft.startTerms} onChange={event => update(index, 'startTerms', event.target.value)} placeholder="Power supply failed" /><small>Separate alternate phrases with semicolons.</small></label>
            <label><span>COMPLETION EVENT PHRASE(S)</span><textarea rows={2} value={draft.completionTerms} onChange={event => update(index, 'completionTerms', event.target.value)} placeholder="Essential circuits restored" /><small>These phrases help locate possible evidence. A person still reviews findings.</small></label>
            <label className="objective-full-field"><span>OPTIONAL REPORTED COMPLETION PHRASES</span><textarea rows={2} value={draft.completionClaimTerms} onChange={event => update(index, 'completionClaimTerms', event.target.value)} placeholder="Restoration completed" /><small>Use when a source may state a completion time separately.</small></label>
          </>}
          {draft.ruleType === 'reported_duration' && <>
            <label><span>START EVENT PHRASE(S)</span><textarea rows={2} value={draft.startTerms} onChange={event => update(index, 'startTerms', event.target.value)} /></label>
            <label><span>COMPLETION EVENT PHRASE(S)</span><textarea rows={2} value={draft.completionTerms} onChange={event => update(index, 'completionTerms', event.target.value)} /></label>
            <label className="objective-full-field"><span>STATED DURATION PHRASE(S)</span><textarea rows={2} value={draft.claimTerms} onChange={event => update(index, 'claimTerms', event.target.value)} placeholder="Response took" /><small>Used to compare the source-stated duration with the timestamps.</small></label>
          </>}
          {draft.ruleType === 'event_presence' && <label className="objective-full-field"><span>EVENT PHRASE(S) TO LOOK FOR</span><textarea rows={2} value={draft.terms} onChange={event => update(index, 'terms', event.target.value)} placeholder="Emergency operations center activated" /><small>Separate alternate phrases with semicolons.</small></label>}
          {draft.ruleType === 'required_field' && <>
            <label><span>PHRASES THAT STATE THE ITEM IS PRESENT</span><textarea rows={2} value={draft.presentTerms} onChange={event => update(index, 'presentTerms', event.target.value)} placeholder="Contact number recorded" /></label>
            <label><span>PHRASES THAT STATE THE ITEM IS MISSING</span><textarea rows={2} value={draft.missingTerms} onChange={event => update(index, 'missingTerms', event.target.value)} placeholder="Contact number not recorded" /></label>
          </>}
        </div>
      </article>)}
      {value.length === 0 && <div className="objective-draft-empty"><CheckCircle2 size={22} /><strong>No objectives added yet</strong><span>Add a target that evaluators can compare with source evidence.</span></div>}
      <button type="button" className="button secondary objective-add-button" onClick={() => onChange([...value, { id: `OBJ-${String(value.length + 1).padStart(2, '0')}`, text: '', ruleType: 'none', thresholdValue: '', thresholdUnit: 'minutes', startTerms: '', completionTerms: '', completionClaimTerms: '', claimTerms: '', terms: '', missingTerms: '', presentTerms: '', ruleMetadata: {} }])}><Plus size={15} /> Add objective</button>
      <div className="objective-rule-help"><HelpCircle size={15} /><span>Time criteria compare a source-matched start and completion timestamp with the target. Missing or conflicting evidence stays visible for evaluator review. Objectives become read-only after analysis starts so existing findings and decisions keep their original context.</span></div>
    </div>
    <div className="modal-footer"><span>Unconfigured criteria remain marked for evaluator review.</span><div><button type="button" className="button secondary" onClick={onClose}>Cancel</button><button type="submit" className="button primary" disabled={busy}><Check size={14} /> Save objectives</button></div></div>
  </form></section></div>
}

const api = async <T,>(path: string, options: RequestInit = {}): Promise<T> => {
  const url = path.startsWith('/api') ? path : `/api${path}`
  const headers = new Headers(options.headers)
  if (options.method && !['GET', 'HEAD', 'OPTIONS'].includes(options.method.toUpperCase()) && csrfTokenValue && !url.endsWith('/auth/login')) headers.set('X-CSRF-Token', csrfTokenValue)
  const response = await fetch(url, { ...options, headers, credentials: 'same-origin' })
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    let code: string | undefined
    try {
      const data = await response.json()
      code = typeof data.detail?.code === 'string' ? data.detail.code : undefined
      message = data.detail?.message || data.detail?.code || data.detail || message
    } catch { /* Keep HTTP status message. */ }
    if (response.status === 401 && !url.endsWith('/auth/login') && !url.endsWith('/auth/session')) window.dispatchEvent(new Event('drillloop-auth-expired'))
    throw Object.assign(new Error(message), { status: response.status, code })
  }
  if (response.headers.get('content-type')?.includes('application/pdf')) return await response.blob() as T
  return await response.json() as T
}

const initials = (name: string) => name.split(' ').map(part => part[0]).join('').slice(0, 2).toUpperCase()
const shortTime = (value: string | null) => value ? value.slice(value.indexOf('T') + 1, value.indexOf('T') + 9) : 'Time unresolved'
const timelineTime = (value: string | null, exerciseDate: string) => {
  if (!value) return 'Event time not recorded'
  const date = value.includes('T') ? value.slice(0, 10) : ''
  const clock = shortTime(value).endsWith(':00') ? shortTime(value).slice(0, 5) : shortTime(value)
  return date && date !== exerciseDate ? `${date} · ${clock}` : clock
}
const timeLabel = (value: string) => ({ certain: 'Time recorded', medium: 'Time recognized', uncertain: 'Time uncertain', unknown: 'Time missing' }[value] || value)
const eventTimeLabel = (value: string) => ({
  certain: 'Explicit date and time',
  medium: 'Date or timezone incomplete',
  uncertain: 'Recognition uncertain',
  unknown: 'Event time not recorded',
}[value] || value)
const scanLabel = (value: Source['scan_status']) => value === 'clean' ? 'Upload scan passed' : value === 'not_scanned' ? 'Upload scan not performed' : `Upload scan: ${value.replace(/_/g, ' ')}`
const isTranscript = (source: Source | undefined) => source?.kind === 'transcript'
const timeMentions = (value: string) => Array.from(new Set(value.match(/\b(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?\b/g) || []))
const DEMO_SOURCE_HASHES: Record<string, string> = {
  'control_room_log.csv': '3e5cb9557b0815b279ff8bee6f5d57302d313996c2bf9c75ffc990b5f6fa3f75',
  'evaluator_notes.txt': '3f81dd4a14d3af995891e1d6963f9d90ab275a2a8c9794b191df9e7ff2be67a7',
  'transcript.json': '55c2a02cffa46f55c455cce596a2969699f91c94e8faa00457486334a3ab8cb6',
}
const localDateInput = () => {
  const date = new Date()
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

export default function App() {
  const [exercises, setExercises] = useState<Exercise[]>([])
  const [selectedId, setSelectedId] = useState(() => localStorage.getItem('drillloop-selected-exercise') || '')
  const [data, setData] = useState<Detail | null>(null)
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null)
  const [identity, setIdentity] = useState<Identity | null>(null)
  const [authenticated, setAuthenticated] = useState(false)
  const [loginForm, setLoginForm] = useState({ username: '', password: '' })
  const [tab, setTab] = useState<Tab>('exercises')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [reportDownload, setReportDownload] = useState<ReportDownloadState>({ status: 'idle' })
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [sourceFilter, setSourceFilter] = useState('')
  const [evidenceOpen, setEvidenceOpen] = useState<Support | null>(null)
  const [sourceOpen, setSourceOpen] = useState<Source | null>(null)
  const [sourceFocusObservationId, setSourceFocusObservationId] = useState('')
  const [pendingReview, setPendingReview] = useState<ReviewTarget | null>(null)
  const [closureTarget, setClosureTarget] = useState<Action | null>(null)
  const [timelineFocusId, setTimelineFocusId] = useState('')
  const [uploading, setUploading] = useState(false)
  const uploadLock = useRef(false)
  const decisionLock = useRef(false)
  const reportExportLock = useRef(false)
  const resetWorkspaceScrollOnSelection = useRef(false)
  const [accessOpen, setAccessOpen] = useState(false)
  const [accessGrants, setAccessGrants] = useState<AccessGrant[]>([])
  const [configuredUsers, setConfiguredUsers] = useState<AccessGrant[]>([])
  const [createOpen, setCreateOpen] = useState(false)
  const [objectivesOpen, setObjectivesOpen] = useState(false)
  const [objectiveDraft, setObjectiveDraft] = useState<ObjectiveDraft[]>([])
  const [newForm, setNewForm] = useState({ id: '', title: '', scenario: '', exercise_date: localDateInput(), duration_minutes: '120', evaluator_roles: '', participants: '', milestones: '' })

  useEffect(() => {
    const rememberFocus = (event: FocusEvent) => {
      const target = event.target
      if (target instanceof HTMLElement && !target.closest('[role="dialog"]')) {
        lastOutsideDialogFocus = target
      }
    }
    document.addEventListener('focusin', rememberFocus)
    return () => document.removeEventListener('focusin', rememberFocus)
  }, [])

  const refreshExercises = useCallback(async () => {
    const list = await api<Exercise[]>('/exercises')
    setExercises(list)
    if (!list.some(item => item.id === selectedId) && list[0]) setSelectedId(list[0].id)
    if (list.length === 0) setLoading(false)
  }, [selectedId])

  const refreshDetail = useCallback(async (id = selectedId) => {
    const detail = await api<Detail>(`/exercises/${encodeURIComponent(id)}`)
    setData(detail)
  }, [selectedId])

  const loadWorkspace = async () => {
    const [list, caps] = await Promise.all([api<Exercise[]>('/exercises'), api<Capabilities>('/capabilities')])
    setExercises(list)
    setCapabilities(caps)
    const initial = list.find(item => item.id === selectedId)?.id || list[0]?.id || ''
    setSelectedId(initial)
    setData(initial ? await api<Detail>(`/exercises/${encodeURIComponent(initial)}`) : null)
  }

  useEffect(() => {
    let live = true
    const expired = () => { csrfTokenValue = ''; setIdentity(null); setAuthenticated(true); setData(null); setExercises([]); setError('Your session expired. Sign in again.') }
    window.addEventListener('drillloop-auth-expired', expired)
    api<{ identity: Identity; csrf_token: string }>('/auth/session')
      .then(async session => {
        csrfTokenValue = session.csrf_token
        if (!live) return
        setIdentity(session.identity); setAuthenticated(true)
        await loadWorkspace()
      })
      .catch((err: Error & { status?: number }) => {
        if (!live) return
        setAuthenticated(true)
        if (err.status !== 401) setError(err.message)
      })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false; window.removeEventListener('drillloop-auth-expired', expired) }
  }, [])

  useEffect(() => {
    if (selectedId) localStorage.setItem('drillloop-selected-exercise', selectedId)
  }, [selectedId])

  useLayoutEffect(() => {
    const revealActiveSection = () => {
      const nav = document.querySelector<HTMLElement>('.subnav')
      const active = nav?.querySelector<HTMLElement>('.subnav-link[aria-current="page"]')
      if (!nav || !active) return

      const navBounds = nav.getBoundingClientRect()
      const activeBounds = active.getBoundingClientRect()
      if (activeBounds.left < navBounds.left) {
        nav.scrollLeft -= navBounds.left - activeBounds.left
      } else if (activeBounds.right > navBounds.right) {
        nav.scrollLeft += activeBounds.right - navBounds.right
      }
    }

    revealActiveSection()
    window.addEventListener('resize', revealActiveSection)
    return () => window.removeEventListener('resize', revealActiveSection)
  }, [tab, data?.findings])

  useEffect(() => {
    if (!resetWorkspaceScrollOnSelection.current || tab === 'exercises' || data?.exercise.id !== selectedId) return
    resetWorkspaceScrollOnSelection.current = false
    window.requestAnimationFrame(() => window.requestAnimationFrame(() => window.scrollTo({ top: 0, left: 0, behavior: 'instant' })))
  }, [tab, selectedId, data?.exercise.id])

  const withBusy = async (task: () => Promise<void>): Promise<boolean> => {
    setBusy(true); setError(''); setNotice('')
    try { await task(); return true } catch (err) { setError(err instanceof Error ? err.message : 'Something went wrong.'); return false }
    finally { setBusy(false) }
  }

  const selectExercise = (id: string, destination: Tab = 'overview') => {
    if (!id || reportExportLock.current) return
    resetWorkspaceScrollOnSelection.current = true
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' })
    if (id === selectedId && data?.exercise.id === id) { setTab(destination); return }
    setReportDownload({ status: 'idle' })
    void withBusy(async () => {
      setData(null)
      setSelectedId(id)
      localStorage.setItem('drillloop-selected-exercise', id)
      await refreshDetail(id)
      setTab(destination)
    })
  }

  const openReports = () => {
    setTab('reports')
    if (selectedId && data?.exercise.id !== selectedId) selectExercise(selectedId, 'reports')
  }

  const authHeaders = { 'Content-Type': 'application/json' }
  const canEdit = identity?.role === 'admin' || identity?.role === 'evaluator'
  const canReview = identity?.role === 'admin' || identity?.role === 'reviewer'
  const findingCounts = useMemo(() => ({
    proposed: data?.findings.filter(f => f.status === 'proposed').length || 0,
    approved: data?.findings.filter(f => f.status === 'approved').length || 0,
    improvement: data?.findings.filter(f => f.category === 'improvement').length || 0,
  }), [data])

  const refreshAccess = async () => {
    const [grants, users] = await Promise.all([
      api<AccessGrant[]>(`/exercises/${encodeURIComponent(selectedId)}/access`),
      api<AccessGrant[]>('/configured-users'),
    ])
    setAccessGrants(grants)
    setConfiguredUsers(users)
  }

  const openAccess = () => withBusy(async () => {
    await refreshAccess()
    setAccessOpen(true)
  })

  const grantAccess = (userId: string) => withBusy(async () => {
    await api(`/exercises/${encodeURIComponent(selectedId)}/access`, {
      method: 'POST', headers: authHeaders, body: JSON.stringify({ user_id: userId }),
    })
    await refreshAccess()
    setNotice('Exercise access granted using the account’s configured role.')
  })

  const revokeAccess = (userId: string) => withBusy(async () => {
    await api(`/exercises/${encodeURIComponent(selectedId)}/access/${encodeURIComponent(userId)}`, { method: 'DELETE' })
    await refreshAccess()
    setNotice('Exercise access revoked.')
  })

  const runAnalysis = () => withBusy(async () => {
    const result = await api<{ candidate_count: number; new_findings: number; model_status: string; objective_assessments: ObjectiveAssessment[] }>(`/exercises/${selectedId}/analyze`, { method: 'POST' })
    await refreshDetail()
    const unresolved = result.objective_assessments.filter(item => !item.state.startsWith('confirmed_')).length
    setNotice(`${result.candidate_count} evidence-linked draft(s) prepared; ${unresolved} objective(s) need more evidence or evaluator review. ${result.model_status}`)
  })

  const uploadFiles = async (files: File[]): Promise<boolean> => {
    if (!files.length || uploadLock.current) return false
    uploadLock.current = true
    setUploading(true)
    const succeeded = await withBusy(async () => {
      const form = new FormData()
      files.forEach(file => form.append('files', file))
      let result: { message: string }
      try {
        result = await api<{ message: string }>(`/exercises/${selectedId}/evidence`, { method: 'POST', body: form })
      } catch (err) {
        const uploadError = err as Error & { code?: string }
        if (uploadError.code === 'MALWARE_REJECTED') throw new Error('The upload scanner rejected this file. No source was imported. Choose a different file or contact your administrator if you think this is a mistake.')
        if (uploadError.code?.startsWith('SCANNER_') || uploadError.code === 'QUARANTINE_UNAVAILABLE') throw new Error('The required upload scan could not be completed, so no source was imported. Try again later or contact your administrator.')
        if (uploadError.code === 'PARSER_CAPACITY_EXHAUSTED') throw new Error('Evidence processing is busy. No files were imported. Wait a few seconds, then retry.')
        if (uploadError.code === 'PARSER_TIMEOUT') throw new Error('Evidence processing took too long, so no files were imported. Try a smaller file or retry.')
        throw err
      }
      await refreshDetail(); setNotice(result.message)
    })
    setUploading(false)
    uploadLock.current = false
    return succeeded
  }

  const transcribeFile = (file?: File) => {
    if (!file) return
    withBusy(async () => {
      const form = new FormData(); form.append('file', file)
      await api(`/exercises/${selectedId}/audio`, { method: 'POST', body: form })
      await refreshDetail(); setNotice('Audio transcript imported. Verify uncertain text against the recording.')
    })
  }

  const reviewFinding = async (finding: Finding, decision: 'approved' | 'rejected', note: string) => {
    if (decisionLock.current) return false
    decisionLock.current = true
    const saved = await withBusy(async () => {
      await api(`/findings/${finding.id}/review`, { method: 'POST', headers: authHeaders, body: JSON.stringify({ decision, note }) })
      await refreshDetail(); setNotice(`Finding ${decision}. The reviewer decision is recorded.`)
    })
    decisionLock.current = false
    return saved
  }

  const saveAction = (action: Action, form: HTMLFormElement) => withBusy(async () => {
    const values = new FormData(form)
    await api(`/actions/${action.id}`, { method: 'PUT', headers: authHeaders, body: JSON.stringify({
      title: values.get('title'),
      owner: String(values.get('owner') || '') || null, priority: values.get('priority'),
      due_date: String(values.get('due_date') || '') || null,
      acceptance_criteria: values.get('acceptance_criteria'),
    }) })
    await refreshDetail(); setNotice('Corrective action updated.')
  })

  const reviewAction = async (action: Action, decision: 'approved' | 'rejected', note: string) => {
    if (decisionLock.current) return false
    decisionLock.current = true
    const saved = await withBusy(async () => {
      await api(`/actions/${action.id}/review`, { method: 'POST', headers: authHeaders, body: JSON.stringify({ decision, note }) })
      await refreshDetail(); setNotice(`Corrective action ${decision}.`)
    })
    decisionLock.current = false
    return saved
  }

  const closeAction = async (action: Action, closure_evidence: string) => {
    if (decisionLock.current) return false
    decisionLock.current = true
    const saved = await withBusy(async () => {
      await api(`/actions/${action.id}/close`, { method: 'POST', headers: authHeaders, body: JSON.stringify({ closure_evidence }) })
      await refreshDetail(); setNotice('Closure evidence recorded and action closed.')
    })
    decisionLock.current = false
    return saved
  }

  const confirmReview = async (note: string) => {
    if (!pendingReview) return false
    const target = pendingReview
    const saved = target.kind === 'finding'
      ? await reviewFinding(target.record, target.decision, note)
      : await reviewAction(target.record, target.decision, note)
    if (saved) setPendingReview(null)
    return saved
  }

  const confirmClosure = async (closureEvidence: string) => {
    if (!closureTarget) return false
    const saved = await closeAction(closureTarget, closureEvidence)
    if (saved) setClosureTarget(null)
    return saved
  }

  const exportReport = async () => {
    if (!selectedId || reportExportLock.current || busy) return
    reportExportLock.current = true
    setBusy(true)
    setError('')
    setNotice('')
    setReportDownload({ status: 'preparing' })
    try {
      const blob = await api<Blob>(`/exercises/${encodeURIComponent(selectedId)}/report.pdf`)
      if (!(blob instanceof Blob) || blob.type !== 'application/pdf' || blob.size === 0) {
        throw new Error('The report service returned an empty or unsupported file. Please retry.')
      }
      if ((await blob.slice(0, 5).text()) !== '%PDF-') {
        throw new Error('The downloaded file is not a readable PDF. Please retry.')
      }
      const safeId = selectedId.replace(/[^a-zA-Z0-9._-]/g, '-')
      const filename = `${safeId}-AAR-IP.pdf`
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = filename
      anchor.style.display = 'none'
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
      setReportDownload({ status: 'started', filename })
    } catch (err) {
      const status = typeof err === 'object' && err !== null && 'status' in err ? Number(err.status) : undefined
      const message = status === 401
        ? 'Your session has expired. Sign in again, then retry the report download.'
        : status === 403
          ? 'Your account does not have permission to download this report. Ask a workspace administrator to check your access.'
          : status === 404
            ? 'This exercise report is not available to your account. Check the selected exercise or ask a workspace administrator.'
            : status && status >= 500
              ? 'DrillLoop could not prepare the PDF. Check the service connection, then retry.'
              : err instanceof Error
                ? err.message
                : 'DrillLoop could not prepare the PDF. Check the service connection, then retry.'
      setReportDownload({ status: 'failed', message })
    } finally {
      reportExportLock.current = false
      setBusy(false)
    }
  }

  const createExercise = () => withBusy(async () => {
    const expected_milestones = newForm.milestones.split('\n').map(line => line.trim()).filter(Boolean).map((expected, index) => ({ id: `M-${String(index + 1).padStart(2, '0')}`, expected, objective_id: '' }))
    const created = await api<Exercise>('/exercises', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
      id: newForm.id, title: newForm.title, scenario: newForm.scenario, exercise_date: newForm.exercise_date,
      duration_minutes: Number(newForm.duration_minutes), objectives: [], expected_milestones,
      criteria: [], evaluator_roles: newForm.evaluator_roles.split(',').map(x => x.trim()).filter(Boolean),
      participants: newForm.participants.split(',').map(x => x.trim()).filter(Boolean),
    }) })
    setSelectedId(created.id); localStorage.setItem('drillloop-selected-exercise', created.id); setCreateOpen(false); await refreshExercises(); await refreshDetail(created.id)
    setTab('objectives'); setNotice('Exercise created. Define its objectives before adding evidence.')
  })

  const saveObjectives = () => {
    const validationErrors = validateObjectiveDrafts(objectiveDraft)
    if (validationErrors.length) return
    if (!data || data.analysis_locked) return
    void withBusy(async () => {
    const objectives = objectiveDraft.map(draftToObjective)
    await api(`/exercises/${encodeURIComponent(selectedId)}/objectives`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ objectives, criteria: data?.exercise.criteria || [] }),
    })
    await refreshDetail()
    setObjectivesOpen(false)
    setNotice('Objectives saved. Review them before analyzing exercise evidence.')
    })
  }

  const loadFictionalDemo = () => withBusy(async () => {
    const seeded = await api<{ id: string }>('/demo/seed', { method: 'POST' })
    await refreshExercises()
    await refreshDetail(seeded.id)
    setTab('overview')
    setNotice('Fictional demo exercise opened. Its evidence and ground truth are synthetic.')
  })

  const selectedExercise = data?.exercise
  const filteredSources = data?.sources.filter(source => !sourceFilter || source.filename.toLowerCase().includes(sourceFilter.toLowerCase())) || []
  const syntheticSourceIds = new Set(data?.exercise.id === 'HOSP-PO-2026-01'
    ? data.sources.filter(source => DEMO_SOURCE_HASHES[source.filename] === source.sha256 && !data.audit_events.some(event => event.action === 'evidence_uploaded' && event.object_id === source.id)).map(source => source.id)
    : [])
  const openTimelineObservation = (observationId: string) => {
    setEvidenceOpen(null)
    setSourceOpen(null)
    setTimelineFocusId(observationId)
    setTab('timeline')
  }
  const hasPendingReview = Boolean(data?.findings.some(finding => finding.status === 'proposed') || data?.actions.some(action => action.status === 'proposed'))
  const exerciseState = !data ? 'No exercise selected' : hasPendingReview ? 'Review pending' : data.analysis_locked ? (data.findings.length || data.actions.length ? 'Review decisions recorded' : 'Analysis run') : data.sources.length ? 'Evidence imported' : 'Setup in progress'
  const openObjectiveEditor = () => {
    if (!data || !canEdit || data.analysis_locked) return
    setError('')
    setObjectiveDraft(data.exercise.objectives.map(objectiveToDraft))
    setObjectivesOpen(true)
  }
  const startCreateExercise = () => {
    setError('')
    setNewForm({ id: '', title: '', scenario: '', exercise_date: localDateInput(), duration_minutes: '120', evaluator_roles: '', participants: '', milestones: '' })
    setCreateOpen(true)
  }

  const signIn = async (event: React.FormEvent) => {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const result = await api<{ identity: Identity; csrf_token: string }>('/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(loginForm) })
      csrfTokenValue = result.csrf_token
      setIdentity(result.identity); setAuthenticated(true); setLoginForm({ username: '', password: '' })
      await loadWorkspace()
    } catch (err) { setError(err instanceof Error ? err.message : 'Sign in failed.') }
    finally { setBusy(false); setLoading(false) }
  }

  const signOut = () => withBusy(async () => {
    await api('/auth/logout', { method: 'POST' }); csrfTokenValue = ''; setIdentity(null); setData(null); setExercises([]); setAuthenticated(true); setNotice('')
  })

  if (loading) return <div className="loading-screen"><div className="brand-mark"><Activity size={24} /></div><LoaderCircle className="spin" /> Loading exercise workspace</div>

  if (!identity) return <main className="auth-screen"><form className="auth-card" onSubmit={signIn}><div className="brand-mark"><Activity size={21} /></div><p className="eyebrow">DRILLLOOP WORKSPACE</p><h1>Sign in</h1><p>Use your named account to access authorized exercises.</p>{error && <div className="alert error-alert" role="alert"><AlertTriangle size={17} /><span>{error}</span></div>}<label><span>USERNAME</span><input autoComplete="username" value={loginForm.username} onChange={event => setLoginForm({ ...loginForm, username: event.target.value })} required /></label><label><span>PASSWORD</span><input type="password" autoComplete="current-password" value={loginForm.password} onChange={event => setLoginForm({ ...loginForm, password: event.target.value })} required /></label><button className="button primary" type="submit" disabled={busy || !authenticated}>{busy ? 'Signing in…' : 'Sign in'}</button><small>Accounts are configured by the workspace administrator.</small></form></main>

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="DrillLoop workspace navigation">
        <div className="brand"><div className="brand-mark"><Activity size={21} strokeWidth={2.5} /></div><div><strong>drillloop</strong><span>EXERCISE INTELLIGENCE</span></div></div>
        <nav className="workspace-nav" aria-label="Workspace sections">
          <div className="workspace-label">WORKSPACE</div>
          <button className={`nav-link ${tab === 'exercises' ? 'active' : ''}`} aria-current={tab === 'exercises' ? 'page' : undefined} onClick={() => setTab('exercises')}><Gauge size={17} /> Exercises <span className="nav-count">{exercises.length}</span></button>
          <button className={`nav-link ${tab === 'actions' ? 'active' : ''}`} aria-current={tab === 'actions' ? 'page' : undefined} onClick={() => setTab('actions')}><ListChecks size={17} /> Corrective actions</button>
          <button className={`nav-link ${tab === 'evidence' ? 'active' : ''}`} aria-current={tab === 'evidence' ? 'page' : undefined} onClick={() => setTab('evidence')}><FolderOpen size={17} /> Evidence library</button>
          <button className={`nav-link ${tab === 'reports' ? 'active' : ''}`} aria-current={tab === 'reports' ? 'page' : undefined} onClick={openReports}><ClipboardList size={17} /> Reports</button>
        </nav>
        <div className="sidebar-divider" />
        <section className="exercise-context" aria-label="Selected exercise">
          <label className="workspace-label" htmlFor="exercise-picker">CURRENT EXERCISE</label>
          <div className="selected-exercise-card"><div className="exercise-avatar"><Activity size={16} /></div><div className="switcher-copy"><strong>{selectedExercise?.title || 'Choose an exercise'}</strong><span>{selectedExercise?.id || `${exercises.length} available`}</span></div></div>
          <select id="exercise-picker" className="exercise-switcher" aria-label="Select exercise" value={selectedId} onChange={e => selectExercise(e.target.value)}>
            <option value="">Select an exercise</option>
            {exercises.map(exercise => <option value={exercise.id} key={exercise.id}>{exercise.title} · {exercise.id}</option>)}
          </select>
        </section>
        <nav className="subnav" aria-label="Exercise sections">
          {(['overview', 'objectives', 'evidence', 'timeline', 'findings', 'actions', 'reports'] as Tab[]).map((item, index) => {
            const Icon = [Activity, CheckCircle2, FileText, Clock3, ShieldCheck, ListChecks, ClipboardList][index]
            const labels = ['Overview', 'Objectives', 'Evidence', 'Timeline', 'Findings', 'Corrective actions', 'Reports']
            return <button className={`subnav-link ${tab === item ? 'selected' : ''}`} aria-current={tab === item ? 'page' : undefined} key={item} onClick={() => item === 'reports' ? openReports() : setTab(item)}><Icon size={15} />{labels[index]}{item === 'findings' && findingCounts.proposed > 0 && <span className="tiny-count">{findingCounts.proposed}<span className="sr-only"> proposed</span></span>}</button>
          })}
        </nav>
        <div className="sidebar-bottom">
          <div className="local-box"><div className="local-icon"><LockKeyhole size={15} /></div><div><strong>Local-first workspace</strong><span>No cloud API required</span></div><span className="online-dot" /></div>
          <div className="profile-row"><div className="user-avatar">{initials(identity?.name || 'User')}</div><div><strong>{identity?.name}</strong><span>{identity?.role} access</span></div></div>
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div className="breadcrumbs">
            <span>Exercises</span>
            {tab !== 'exercises' && <>
              <ChevronRight size={14} />
              <strong>{selectedExercise?.title || 'Exercise workspace'}</strong>
              {selectedExercise && <span className="breadcrumb-id">{selectedExercise.id}</span>}
            </>}
          </div>
          <div className="topbar-actions">
            <span className="identity-label">{identity?.name} · {identity?.role}</span>
            <button className="text-link topbar-signout" onClick={() => void signOut()}>Sign out</button>
          </div>
        </header>

        <div className="content-wrap">
          {error && <div className="alert error-alert" role="alert"><AlertTriangle size={17} /><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError('')}><X size={15} /></button></div>}
          {notice && <div className="alert success-alert" role="status"><CheckCircle2 size={17} /><span>{notice}</span><button aria-label="Dismiss message" onClick={() => setNotice('')}><X size={15} /></button></div>}
          {tab === 'exercises' ? <ExerciseLibrary exercises={exercises} selectedId={selectedId} selectedState={data?.exercise.id === selectedId ? exerciseState : undefined} canEdit={Boolean(canEdit)} canSeed={Boolean(canEdit && capabilities?.synthetic_demo_seed_enabled)} onSeed={loadFictionalDemo} onCreate={startCreateExercise} onOpen={exercise => selectExercise(exercise.id, exercise.objectives.length ? 'overview' : 'objectives')} /> : !data ? tab === 'reports' ? <ReportsEmptyState selectedId={selectedId} busy={busy} hasExercises={exercises.length > 0} onChoose={() => setTab('exercises')} onCreate={startCreateExercise} onRetry={() => { if (selectedId) void withBusy(() => refreshDetail(selectedId)) }} canEdit={Boolean(canEdit)} /> : <EmptyState canEdit={Boolean(canEdit)} canSeed={Boolean(canEdit && capabilities?.synthetic_demo_seed_enabled)} onSeed={loadFictionalDemo} onCreate={startCreateExercise} /> : <>
            <div className="page-heading">
              <div className="heading-copy">
                <div className="eyebrow"><span className="eyebrow-dot" /> SELECTED EXERCISE <span className="heading-separator">/</span> {selectedExercise?.id}</div>
                <h1>{selectedExercise?.title}</h1>
                <p>{selectedExercise?.scenario}</p>
                <div className="heading-meta"><span><Clock3 size={14} /> {selectedExercise?.exercise_date} · {selectedExercise?.duration_minutes} minutes</span><span className="meta-divider" /><span><UsersIcon /> {selectedExercise?.participants.length} participating teams</span><StatusBadge status={exerciseState} /></div>
              </div>
              <div className="heading-buttons">
                {canEdit && <button className="button secondary" onClick={startCreateExercise}><Plus size={16} /> New exercise</button>}
                {canEdit && <button className="button secondary" onClick={() => void openAccess()} disabled={busy}><UsersIcon /> Manage access</button>}
                {canEdit && <button className="button primary" onClick={() => void runAnalysis()} disabled={busy || !selectedExercise?.objectives.length || Boolean(data.analysis_locked)} title={data.analysis_locked ? 'Analysis has already run; objectives and findings remain tied to that analysis.' : !selectedExercise?.objectives.length ? 'Add at least one objective before running analysis.' : undefined}><Sparkles size={16} />{busy ? 'Working…' : data.analysis_locked ? 'Analysis already run' : 'Run evidence analysis'}</button>}
              </div>
            </div>

            <div className="tabs-row">
              <div className="tabs" role="navigation" aria-label="Exercise pages">{(['overview', 'objectives', 'evidence', 'timeline', 'findings', 'actions', 'reports'] as Tab[]).map((item, index) => {
                const names = ['Overview', 'Objectives', 'Evidence', 'Timeline', 'Findings', 'Corrective actions', 'Reports']
                const count = item === 'evidence' ? data.sources.length : item === 'findings' ? data.findings.length : item === 'actions' ? data.actions.length : null
                return <button key={item} className={`tab ${tab === item ? 'active-tab' : ''}`} aria-current={tab === item ? 'page' : undefined} onClick={() => item === 'reports' ? openReports() : setTab(item)}>{names[index]}{count !== null && <span className="tab-count">{count}</span>}</button>
              })}</div>
              {tab !== 'reports' && <button className="export-btn" type="button" onClick={() => void exportReport()} disabled={busy}><ArrowDownToLine size={15} /> Export report + improvement plan (PDF)</button>}
            </div>

          {tab === 'overview' && <Overview data={data} counts={findingCounts} busy={busy} canEdit={Boolean(canEdit)} canReview={Boolean(canReview)} onTab={setTab} onEvidence={setEvidenceOpen} onAnalyze={() => void runAnalysis()} onEditObjectives={canEdit ? openObjectiveEditor : undefined} />}
            {tab === 'objectives' && <ObjectivesView data={data} canEdit={Boolean(canEdit)} onEdit={openObjectiveEditor} />}
            {tab === 'evidence' && <EvidenceView data={data} capabilities={capabilities} canEdit={Boolean(canEdit)} busy={busy} uploading={uploading} filteredSources={filteredSources} sourceFilter={sourceFilter} setSourceFilter={setSourceFilter} syntheticSourceIds={syntheticSourceIds} onUpload={uploadFiles} onSource={setSourceOpen} onEvidence={setEvidenceOpen} onGoTimeline={() => setTab('timeline')} onTranscribe={transcribeFile} />}
            {tab === 'timeline' && <TimelineView data={data} focusObservationId={timelineFocusId} onFocusConsumed={() => setTimelineFocusId('')} onEvidence={setEvidenceOpen} onGoEvidence={() => setTab('evidence')} />}
            {tab === 'findings' && <FindingsView data={data} busy={busy} canEdit={Boolean(canEdit)} canReview={Boolean(canReview)} identityName={identity.name} isSyntheticDemo={syntheticSourceIds.size > 0} onReview={(finding, decision) => setPendingReview({ kind: 'finding', record: finding, decision })} onEvidence={item => { const source = data.sources.find(candidate => candidate.id === item.source_id); if (source) { setSourceFocusObservationId(item.observation_id); setSourceOpen(source) } else setEvidenceOpen(item) }} />}
            {tab === 'actions' && <ActionsView data={data} busy={busy} canEdit={Boolean(canEdit)} canReview={Boolean(canReview)} identityName={identity.name} isSyntheticDemo={syntheticSourceIds.size > 0} onSave={saveAction} onReview={(action, decision) => setPendingReview({ kind: 'action', record: action, decision })} onClose={setClosureTarget} onEvidence={item => { const source = data.sources.find(candidate => candidate.id === item.source_id); if (source) { setSourceFocusObservationId(item.observation_id); setSourceOpen(source) } else setEvidenceOpen(item) }} />}
            {tab === 'reports' && <ReportsView data={data} busy={busy} download={reportDownload} onExport={() => void exportReport()} onTab={setTab} />}

            <footer className="page-footer"><span><ShieldCheck size={14} /> Original file, exact location, and file-integrity check are retained.</span><span>Source-linked · human review required · DrillLoop is not certified</span></footer>
          </>}
        </div>
      </main>
      {evidenceOpen && <EvidenceModal evidence={evidenceOpen} onClose={() => setEvidenceOpen(null)} />}
      {sourceOpen && data && <SourceModal source={sourceOpen} data={data} isSynthetic={syntheticSourceIds.has(sourceOpen.id)} focusedObservationId={sourceFocusObservationId} onTimeline={openTimelineObservation} onClose={() => { setSourceOpen(null); setSourceFocusObservationId('') }} />}
      {pendingReview && data && <ReviewDecisionModal target={pendingReview} data={data} busy={busy} errorMessage={error} onClose={() => setPendingReview(null)} onSubmit={confirmReview} />}
      {closureTarget && <ClosureEvidenceModal action={closureTarget} busy={busy} errorMessage={error} onClose={() => setClosureTarget(null)} onSubmit={confirmClosure} />}
      {accessOpen && <AccessModal grants={accessGrants} users={configuredUsers} currentUserId={identity.id} busy={busy} onGrant={grantAccess} onRevoke={revokeAccess} onClose={() => setAccessOpen(false)} />}
      {createOpen && canEdit && <CreateModal form={newForm} setForm={setNewForm} onClose={() => setCreateOpen(false)} onSubmit={createExercise} busy={busy} errorMessage={error} />}
      {objectivesOpen && <ObjectiveEditor value={objectiveDraft} onChange={setObjectiveDraft} onClose={() => setObjectivesOpen(false)} onSubmit={saveObjectives} busy={busy} errorMessage={error} />}
      {busy && <div className="busy-indicator" role="status"><LoaderCircle size={15} className="spin" /> {reportDownload.status === 'preparing' ? 'Preparing report PDF…' : uploading ? 'Checking and processing evidence…' : 'Saving review workspace…'}</div>}
    </div>
  )
}

function UsersIcon() { return <span className="users-glyph">◉</span> }

function AccessModal({ grants, users, currentUserId, busy, onGrant, onRevoke, onClose }: { grants: AccessGrant[]; users: AccessGrant[]; currentUserId: string; busy: boolean; onGrant: (userId: string) => void; onRevoke: (userId: string) => void; onClose: () => void }) {
  const [selectedUser, setSelectedUser] = useState('')
  const dialogRef = useAccessibleDialog<HTMLElement>(onClose)
  const candidates = users.filter(user => !grants.some(grant => grant.user_id === user.user_id))
  return <div className="modal-shade" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}><section ref={dialogRef} className="create-modal" role="dialog" aria-modal="true" aria-labelledby="access-heading" tabIndex={-1}>
    <div className="modal-head"><div className="modal-file-icon"><UsersIcon /></div><div><span>EXERCISE PERMISSIONS</span><h2 id="access-heading">Manage access</h2></div><button className="icon-button" onClick={onClose} aria-label="Close access management"><X size={18} /></button></div>
    <div className="create-form"><p>Accounts and roles are configured by the workspace administrator. A grant adds this exercise to that account; it does not change the account’s configured role.</p><div className="access-list">{grants.map(grant => <div className="access-row" key={grant.user_id}><div><strong>{grant.name}</strong><span>{grant.username} · {grant.role}</span></div>{grant.user_id === currentUserId ? <span>Current account</span> : <button className="button reject" disabled={busy} onClick={() => onRevoke(grant.user_id)}>Revoke</button>}</div>)}{grants.length === 0 && <p>No accounts currently have access.</p>}</div><label><span>GRANT TO CONFIGURED ACCOUNT</span><select value={selectedUser} onChange={event => setSelectedUser(event.target.value)}><option value="">Choose an account</option>{candidates.map(user => <option key={user.user_id} value={user.user_id}>{user.name} · {user.role}</option>)}</select></label><button className="button primary" disabled={busy || !selectedUser} onClick={() => { onGrant(selectedUser); setSelectedUser('') }}>Grant exercise access</button><small>Only configured accounts in your organization are listed. To deactivate an account, remove it from server configuration; removed accounts lose access on their next request.</small></div>
    <div className="modal-footer"><span>Changes are recorded in the exercise audit history.</span><button className="button secondary" onClick={onClose}>Done</button></div>
  </section></div>
}

function EmptyState({ onSeed, onCreate, canEdit, canSeed }: { onSeed: () => void; onCreate: () => void; canEdit: boolean; canSeed: boolean }) {
  return <div className="empty-workspace"><div className="empty-icon"><Zap size={26} /></div><p className="eyebrow">WELCOME TO DRILLLOOP</p><h1>Turn exercise evidence into verified improvement.</h1><p>Select an authorized exercise or create one to begin.</p>{canEdit && <div className="empty-buttons">{canSeed && <button className="button primary" onClick={onSeed}><Sparkles size={16} /> Load fictional demo</button>}<button className="button secondary" onClick={onCreate}><Plus size={16} /> Create exercise</button></div>}{!canEdit && <p>There are no exercises assigned to this account yet.</p>}{canSeed && <div className="synthetic-tag"><ShieldCheck size={14} /> Fictional training data only</div>}</div>
}

function ExerciseLibrary({ exercises, selectedId, selectedState, canEdit, canSeed, onCreate, onSeed, onOpen }: { exercises: Exercise[]; selectedId: string; selectedState?: string; canEdit: boolean; canSeed: boolean; onCreate: () => void; onSeed: () => void; onOpen: (exercise: Exercise) => void }) {
  const [query, setQuery] = useState('')
  const filtered = exercises.filter(exercise => `${exercise.title} ${exercise.id} ${exercise.scenario}`.toLowerCase().includes(query.trim().toLowerCase()))
  return <section className="exercise-library" aria-labelledby="exercise-library-heading">
    <div className="library-heading">
      <div><p className="eyebrow"><span className="eyebrow-dot" /> EXERCISE WORKSPACE</p><h1 id="exercise-library-heading">Exercises</h1><p>Choose an exercise to continue, or create one for your next drill.</p></div>
      {canEdit && <button className="button primary" onClick={onCreate}><Plus size={16} /> Create exercise</button>}
    </div>
    {exercises.length > 0 && <>
      <div className="library-guidance"><CheckCircle2 size={18} /><span><strong>Start with the exercise context, then define its objectives.</strong> Objectives describe what success looks like and should be in place before evidence analysis.</span></div>
      <div className="library-toolbar"><label className="library-search"><Search size={17} /><input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search by name, ID, or scenario" aria-label="Search exercises" /></label><span className="library-count">{filtered.length} of {exercises.length} {exercises.length === 1 ? 'exercise' : 'exercises'}</span></div>
      <div className="exercise-list" aria-label="Available exercises">
        {filtered.map(exercise => <article className={`exercise-list-row ${selectedId === exercise.id ? 'is-selected' : ''}`} key={exercise.id}>
          <div className="exercise-list-main"><div className="exercise-title-line"><h2>{exercise.title}</h2>{selectedId === exercise.id && <StatusBadge status="Selected" tone="info" />}{selectedId === exercise.id && selectedState && <StatusBadge status={selectedState} />}</div><div className="exercise-list-id">{exercise.id}</div><p>{exercise.scenario}</p><div className="exercise-list-meta"><span><Clock3 size={14} /> {formatExerciseDate(exercise.exercise_date)}</span><span><Activity size={14} /> {exercise.duration_minutes} minute exercise</span><span><CheckCircle2 size={14} /> {exercise.objectives.length} {exercise.objectives.length === 1 ? 'objective' : 'objectives'}</span>{(exercise.finding_count || 0) > 0 && <span>{exercise.finding_count} {exercise.finding_count === 1 ? 'finding' : 'findings'}</span>}{(exercise.action_count || 0) > 0 && <span>{exercise.action_count} {exercise.action_count === 1 ? 'action' : 'actions'}</span>}</div></div>
          <button className="button secondary exercise-open-button" onClick={() => onOpen(exercise)}>{selectedId === exercise.id ? 'Continue' : 'Open exercise'} <ChevronRight size={15} /></button>
        </article>)}
        {filtered.length === 0 && <div className="library-no-results"><Search size={21} /><strong>No matching exercises</strong><span>Try another name, exercise ID, or scenario.</span><button className="text-link" onClick={() => setQuery('')}>Clear search</button></div>}
      </div>
    </>}
    {exercises.length === 0 && <div className="library-empty"><div className="empty-icon"><Activity size={25} /></div><p className="eyebrow">YOUR EXERCISE WORKSPACE</p><h2>{canEdit ? 'Create your first exercise' : 'No exercises available'}</h2><p>{canEdit ? 'Add the name, scenario, and date. Next, you’ll define objectives that explain what success looks like.' : 'No exercises have been assigned to your account yet. Ask an exercise editor to grant access.'}</p>{canEdit && <div className="empty-buttons"><button className="button primary" onClick={onCreate}><Plus size={16} /> Create first exercise</button>{canSeed && <button className="button secondary" onClick={onSeed}><Sparkles size={16} /> Load fictional demo</button>}</div>}{canSeed && canEdit && <div className="synthetic-tag"><ShieldCheck size={14} /> Demo content and ground truth are fictional</div>}</div>}
  </section>
}

function formatExerciseDate(value: string): string {
  const date = new Date(`${value}T00:00:00Z`)
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeZone: 'UTC' }).format(date)
}

function ObjectivesView({ data, canEdit, onEdit }: { data: Detail; canEdit: boolean; onEdit: () => void }) {
  const objectives = data.exercise.objectives
  return <section className="objectives-page" aria-labelledby="objectives-page-heading">
    <div className="objectives-page-heading"><div><p className="eyebrow"><span className="eyebrow-dot" /> EXERCISE SETUP <span className="heading-separator">/</span> OBJECTIVES</p><h2 id="objectives-page-heading">Define what success looks like</h2><p>Objectives are the targets evaluators compare with source evidence. A description says what should happen; success criteria describe what evidence can support it.</p></div><div className="objective-page-actions"><span className="small-count">{objectives.length} {objectives.length === 1 ? 'objective' : 'objectives'}</span>{canEdit && !data.analysis_locked && <button className="button primary" onClick={onEdit}><CheckCircle2 size={16} /> {objectives.length ? 'Edit objectives' : 'Add objectives'}</button>}</div></div>
    {data.analysis_locked ? <div className="objective-lock-note" role="status"><LockKeyhole size={19} /><div><strong>Objectives are read-only after analysis</strong><p>Analysis has started for this exercise. Keeping these objectives unchanged preserves the context of existing findings and reviewer decisions. Review each objective and its original criteria below.</p></div></div> : !canEdit ? <div className="objective-lock-note permission" role="note"><LockKeyhole size={19} /><div><strong>Objective editing is limited to exercise editors</strong><p>Your account can review this exercise but does not have permission to change its objectives.</p></div></div> : <div className="objective-guide-note"><HelpCircle size={18} /><span>Add objectives before running analysis. If a criterion or source fact is missing or unclear, DrillLoop leaves the result for evaluator review instead of treating it as a failure.</span></div>}
    {objectives.length === 0 ? <div className="objectives-empty"><div className="empty-icon"><CheckCircle2 size={23} /></div><h3>No objectives configured</h3><p>Add the outcomes this exercise is intended to test. Clear criteria help evaluators understand what to look for in the records.</p>{canEdit && !data.analysis_locked && <button className="button primary" onClick={onEdit}><Plus size={15} /> Add the first objective</button>}</div> : <div className="objective-detail-list">{objectives.map((objective, index) => {
      const assessment = data.objective_assessments.find(item => item.objective_id === objective.id)
      const status = assessment ? assessment.state.replaceAll('_', ' ') : 'Not assessed yet'
      return <article className="objective-detail-card" key={objective.id}>
        <div className="objective-detail-top"><span className="objective-number">{String(index + 1).padStart(2, '0')}</span><span className="objective-id">{objective.id}</span><StatusBadge status={status} /></div>
        <div className="objective-detail-body"><h3>Objective description</h3><p>{objective.text}</p><div className="objective-success-criteria"><div><CheckCircle2 size={16} /><h4>Success criteria</h4></div><p>{objectiveRuleSummary(objective)}</p>{objective.evaluation_rule && <small>Configured phrases help match possible evidence in the exercise records. They do not replace evaluator review.</small>}</div></div>
      </article>
    })}</div>}
  </section>
}

function ReportsView({ data, busy, download, onExport, onTab }: { data: Detail; busy: boolean; download: ReportDownloadState; onExport: () => void; onTab: (tab: Tab) => void }) {
  const findings = {
    proposed: data.findings.filter(item => item.status === 'proposed').length,
    approved: data.findings.filter(item => item.status === 'approved').length,
    rejected: data.findings.filter(item => item.status === 'rejected').length,
  }
  const actions = {
    proposed: data.actions.filter(item => item.status === 'proposed').length,
    approved: data.actions.filter(item => item.status === 'approved').length,
    rejected: data.actions.filter(item => item.status === 'rejected').length,
    closed: data.actions.filter(item => item.status === 'closed').length,
  }
  const waitingForReview = findings.proposed + actions.proposed
  const openActions = data.actions.filter(item => item.status !== 'closed')
  const actionsWithoutClosureEvidence = openActions.filter(item => !item.closure_evidence.trim()).length
  const unsupportedFindings = data.findings.filter(item => item.supporting_evidence.length === 0)
  const reportHistoryEvents = data.audit_events.filter(item => ['finding_approved', 'finding_rejected', 'action_approved', 'action_rejected', 'action_closed'].includes(item.action))
  const assessmentUnknowns = data.objective_assessments.flatMap(item => item.unknowns.map(unknown => ({ objective: item.objective_id, text: unknown })))
  const assessmentConflicts = data.objective_assessments.flatMap(item => item.conflicts.map(conflict => ({ objective: item.objective_id, text: conflict })))
  const disclosureCount = data.timeline_conflicts.length + assessmentUnknowns.length + assessmentConflicts.length + unsupportedFindings.length
  const pendingLabel = waitingForReview === 0
    ? 'No proposed finding or action decisions are waiting'
    : `${findings.proposed} finding${findings.proposed === 1 ? '' : 's'} and ${actions.proposed} action${actions.proposed === 1 ? '' : 's'} awaiting reviewer decision`
  const safeId = data.exercise.id.replace(/[^a-zA-Z0-9._-]/g, '-')
  const expectedFilename = `${safeId}-AAR-IP.pdf`

  return <section className="reports-page" aria-labelledby="reports-heading" aria-busy={download.status === 'preparing'}>
    <div className="reports-page-heading">
      <div>
        <p className="reports-eyebrow"><ClipboardList size={15} /> FINAL WORKFLOW STEP <span aria-hidden="true">/</span> REPORTS</p>
        <h2 id="reports-heading">After-Action Report &amp; Improvement Plan</h2>
        <p>Review the exercise-specific contents and outstanding decisions before downloading the current PDF draft.</p>
      </div>
      <span className="reports-type-chip"><FileText size={16} /> AAR/IP · PDF</span>
    </div>

    <section className="reports-hero" aria-label="Selected report">
      <div className="reports-hero-main">
        <div className="reports-hero-icon" aria-hidden="true"><FileText size={23} /></div>
        <div className="reports-hero-copy">
          <span className="reports-overline">REPORT FOR THIS EXERCISE</span>
          <h3>{data.exercise.title}</h3>
          <p>{data.exercise.scenario}</p>
          <div className="reports-context">
            <span><strong>Exercise ID</strong>{data.exercise.id}</span>
            <span><strong>Exercise date</strong>{formatExerciseDate(data.exercise.exercise_date)}</span>
            <span><strong>Report type</strong>After-Action Report &amp; Improvement Plan</span>
          </div>
        </div>
      </div>
      <div className="reports-export-box">
        <span className="reports-draft-badge"><span aria-hidden="true" /> Draft report</span>
        <p>Exports the current exercise record. Pending findings and actions remain proposed; downloading does not approve or close them.</p>
        <button className="button primary reports-export-button" type="button" onClick={onExport} disabled={busy || download.status === 'preparing'}>
          {download.status === 'preparing' ? <LoaderCircle size={17} className="spin" /> : <ArrowDownToLine size={17} />}
          {download.status === 'preparing' ? 'Preparing PDF…' : 'Download report & improvement plan (PDF)'}
        </button>
        <small>Filename: <strong>{expectedFilename}</strong></small>
      </div>
    </section>

    {download.status === 'preparing' && <p className="reports-download-state is-loading" role="status" aria-live="polite"><LoaderCircle size={16} className="spin" /> Preparing the PDF from the latest exercise records…</p>}
    {download.status === 'started' && <div className="reports-download-state is-started" role="status" aria-live="polite"><CheckCircle2 size={18} /><span><strong>PDF received; browser download started.</strong><small>Look for {download.filename || expectedFilename} in your browser’s downloads.</small></span></div>}
    {download.status === 'failed' && <div className="reports-download-state is-failed" role="alert"><AlertTriangle size={18} /><span><strong>Report download failed.</strong><small>{download.message || 'Check the service connection and try again.'}</small></span><button className="button secondary" type="button" onClick={onExport} disabled={busy}>Retry download</button></div>}

    <section className="reports-readiness" aria-labelledby="reports-readiness-heading">
      <div className="reports-section-heading">
        <div><p className="reports-eyebrow">REVIEW &amp; READINESS</p><h3 id="reports-readiness-heading">What still needs attention?</h3></div>
        <span className="reports-available-chip"><Check size={14} /> Draft export available</span>
      </div>
      <p className="reports-readiness-intro">{pendingLabel}. You can export now; this status describes current records and is not an approval or certification.</p>
      <div className="reports-review-grid">
        <article className="reports-review-card">
          <div className="reports-review-card-heading"><ShieldCheck size={18} /><h4>Finding decisions</h4><button className="reports-text-link" type="button" onClick={() => onTab('findings')}>Review findings <ChevronRight size={14} /></button></div>
          <p>Current finding statuses in this exercise.</p>
          <div className="reports-count-row"><ReportCount label="Proposed" value={findings.proposed} tone="pending" /><ReportCount label="Approved" value={findings.approved} tone="approved" /><ReportCount label="Rejected" value={findings.rejected} tone="rejected" /></div>
        </article>
        <article className="reports-review-card">
          <div className="reports-review-card-heading"><ListChecks size={18} /><h4>Corrective actions</h4><button className="reports-text-link" type="button" onClick={() => onTab('actions')}>Open actions <ChevronRight size={14} /></button></div>
          <p>Open means the action is not recorded as closed.</p>
          <div className="reports-count-row"><ReportCount label="Proposed" value={actions.proposed} tone="pending" /><ReportCount label="Approved" value={actions.approved} tone="approved" /><ReportCount label="Rejected" value={actions.rejected} tone="rejected" /><ReportCount label="Closed" value={actions.closed} tone="closed" /></div>
        </article>
      </div>
      <div className="reports-readiness-foot">
        <span><strong>{openActions.length}</strong> open action{openActions.length === 1 ? '' : 's'}</span>
        <span><strong>{actionsWithoutClosureEvidence}</strong> open action{actionsWithoutClosureEvidence === 1 ? '' : 's'} without recorded closure evidence</span>
        <span><strong>{actions.closed}</strong> closed action{actions.closed === 1 ? '' : 's'} with closure evidence recorded</span>
      </div>
    </section>

    <section className="reports-contents" aria-labelledby="reports-contents-heading">
      <div className="reports-section-heading">
        <div><p className="reports-eyebrow">PDF CONTENTS</p><h3 id="reports-contents-heading">What this download contains</h3></div>
        <span className="reports-section-caption">Based on the current selected exercise</span>
      </div>
      <div className="reports-content-grid">
        <ReportContentCard icon={<Activity size={18} />} title="Exercise overview" count="Included" detail="Exercise ID, name, scenario, date, duration, and the current draft status." />
        <ReportContentCard icon={<CheckCircle2 size={18} />} title="Objectives & milestones" count={`${data.exercise.objectives.length} objectives · ${data.exercise.expected_milestones.length} milestones`} detail={data.exercise.objectives.length ? 'Objective IDs, descriptions, and expected milestones as currently recorded.' : 'No objectives are recorded yet, so this section will have no objective entries.'} />
        <ReportContentCard icon={<FolderOpen size={18} />} title="Timeline & source register" count={`${data.timeline.length} observations · ${data.sources.length} sources`} detail="Source filenames and locators, recorded time confidence, unresolved timing conflicts, and source file references." />
        <ReportContentCard icon={<ShieldCheck size={18} />} title="Findings & citations" count={`${data.findings.length} ${data.findings.length === 1 ? 'finding' : 'findings'}`} detail={data.findings.length ? 'Source wording and citations, analysis-time interpretation, and each finding’s current proposed, approved, or rejected status with available reviewer notes and attribution.' : 'No findings are recorded yet. The PDF will not invent findings or analysis.'} />
        <ReportContentCard icon={<ListChecks size={18} />} title="Improvement plan" count={`${data.actions.length} ${data.actions.length === 1 ? 'action' : 'actions'}`} detail={data.actions.length ? 'Linked finding, action text, acceptance criteria, owner and due date when recorded, priority, current reviewer decision/status, and recorded closure evidence when present.' : 'No corrective actions are recorded yet.'} />
        <ReportContentCard icon={<History size={18} />} title="Review & closure history" count={`${reportHistoryEvents.length} recorded events`} detail="Available reviewer decisions, names, timestamps and notes from the audit history, plus action closure attribution and evidence. Closure evidence is not independent verification of completed work." />
      </div>
    </section>

    <section className="reports-uncertainty" aria-labelledby="reports-uncertainty-heading">
      <div className="reports-section-heading">
        <div><p className="reports-eyebrow">DISCLOSURES</p><h3 id="reports-uncertainty-heading">Unresolved evidence &amp; report limitations</h3></div>
        <span className="reports-section-caption">{disclosureCount} recorded item{disclosureCount === 1 ? '' : 's'} to review</span>
      </div>
      {disclosureCount > 0 ? <ul className="reports-uncertainty-list">
        {data.timeline_conflicts.map(item => <li key={`timeline-${item.observation_id}`}><AlertTriangle size={16} /><span><strong>Unresolved timeline conflict</strong><small>{item.description} · {item.source_filename}, {item.source_locator}</small></span></li>)}
        {assessmentConflicts.map((item, index) => <li key={`conflict-${item.objective}-${index}`}><AlertTriangle size={16} /><span><strong>{item.objective || 'Objective'} · conflicting evidence</strong><small>{item.text}</small></span></li>)}
        {assessmentUnknowns.map((item, index) => <li key={`unknown-${item.objective}-${index}`}><HelpCircle size={16} /><span><strong>{item.objective || 'Objective'} · unresolved fact</strong><small>{item.text}</small></span></li>)}
        {unsupportedFindings.map(item => <li key={`unsupported-${item.id}`}><AlertTriangle size={16} /><span><strong>Finding has no linked source evidence</strong><small>{item.title} · reviewer assessment is needed before treating this as supported.</small></span></li>)}
      </ul> : <p className="reports-no-uncertainty"><CheckCircle2 size={17} /> No unresolved timing conflicts, objective unknowns, assessment conflicts, or findings without linked source evidence are recorded in the current exercise data.</p>}
      <p className="reports-human-note"><ShieldCheck size={16} /> DrillLoop records evaluator decisions and supplied closure evidence. It does not independently verify corrective work or certify exercise performance.</p>
    </section>

    {data.exercise.objectives.length === 0 && <ReportNextStep title="Add exercise objectives" detail="Objectives give evaluators a target to compare with source observations." label="Open objectives" onClick={() => onTab('objectives')} />}
    {data.exercise.objectives.length > 0 && data.sources.length === 0 && <ReportNextStep title="Add evidence sources" detail="The PDF can be downloaded now, but no source observations or citations are recorded yet." label="Open evidence" onClick={() => onTab('evidence')} />}
    {data.exercise.objectives.length > 0 && data.sources.length > 0 && !data.analysis_locked && <ReportNextStep title="Evidence analysis has not run" detail="No findings or corrective actions have been prepared by the analysis workflow. An exercise editor can start analysis from Overview." label="Open Overview" onClick={() => onTab('overview')} />}
  </section>
}

function ReportCount({ label, value, tone }: { label: string; value: number; tone: string }) {
  return <span className={`reports-count is-${tone}`}><strong>{value}</strong><small>{label}</small></span>
}

function ReportContentCard({ icon, title, count, detail }: { icon: React.ReactNode; title: string; count: string; detail: string }) {
  return <article className="reports-content-card"><div className="reports-content-card-icon">{icon}</div><div><div className="reports-content-card-top"><h4>{title}</h4><span>{count}</span></div><p>{detail}</p></div></article>
}

function ReportNextStep({ title, detail, label, onClick }: { title: string; detail: string; label: string; onClick: () => void }) {
  return <section className="reports-next-step" aria-label="Suggested next step"><div><strong>{title}</strong><p>{detail}</p></div><button className="button secondary" type="button" onClick={onClick}>{label}<ChevronRight size={15} /></button></section>
}

function ReportsEmptyState({ selectedId, busy, hasExercises, onChoose, onCreate, onRetry, canEdit }: { selectedId: string; busy: boolean; hasExercises: boolean; onChoose: () => void; onCreate: () => void; onRetry: () => void; canEdit: boolean }) {
  if (selectedId) return <section className="reports-empty" aria-labelledby="reports-empty-heading">
    <div className="reports-empty-icon"><FileText size={24} /></div>
    <p className="reports-eyebrow">REPORTS</p>
    <h2 id="reports-empty-heading">{busy ? 'Loading the selected exercise' : 'Exercise details are unavailable'}</h2>
    <p>{busy ? 'The report summary will appear when the exercise record is ready.' : 'DrillLoop could not load the selected exercise report context. Check the connection or your access, then try again.'}</p>
    {!busy && <div className="reports-empty-actions"><button className="button primary" type="button" onClick={onRetry}>Retry exercise details</button>{hasExercises && <button className="button secondary" type="button" onClick={onChoose}>Choose another exercise</button>}</div>}
  </section>
  return <section className="reports-empty" aria-labelledby="reports-empty-heading">
    <div className="reports-empty-icon"><FileText size={24} /></div>
    <p className="reports-eyebrow">REPORTS</p>
    <h2 id="reports-empty-heading">Select an exercise to prepare its report</h2>
    <p>Each PDF is generated from the currently selected exercise’s objectives, evidence, findings, decisions, and actions.</p>
    <div className="reports-empty-actions">{hasExercises ? <button className="button primary" type="button" onClick={onChoose}>Choose an exercise</button> : canEdit ? <button className="button primary" type="button" onClick={onCreate}><Plus size={15} /> Create an exercise</button> : <span>No exercises are assigned to this account yet. Ask a workspace administrator for access.</span>}</div>
  </section>
}

function Overview({ data, counts, busy, canEdit, canReview, onTab, onEvidence, onAnalyze, onEditObjectives }: { data: Detail; counts: { proposed: number; approved: number; improvement: number }; busy: boolean; canEdit: boolean; canReview: boolean; onTab: (tab: Tab) => void; onEvidence: (item: Support) => void; onAnalyze: () => void; onEditObjectives?: () => void }) {
  const strengths = data.findings.filter(item => item.category === 'strength')
  const improvements = data.findings.filter(item => item.category === 'improvement')
  const proposedActions = data.actions.filter(action => action.status === 'proposed').length
  const approvedActions = data.actions.filter(action => action.status === 'approved').length
  const closedActions = data.actions.filter(action => action.status === 'closed').length
  const unassessedObjectives = data.exercise.objectives.filter(objective => {
    const assessment = data.objective_assessments.find(item => item.objective_id === objective.id)
    return !assessment || !assessment.state.startsWith('confirmed_') || assessment.conflicts.length > 0 || assessment.unknowns.length > 0
  }).length
  const timeline = data.timeline.slice(0, 5)
  const nextAction = data.timeline_conflicts.length > 0
    ? { title: `Inspect ${data.timeline_conflicts.length} timing conflict${data.timeline_conflicts.length === 1 ? '' : 's'}`, description: 'Source times disagree. Both records and their locations stay visible until an evaluator reviews them.', label: 'Open timeline', icon: <AlertTriangle size={18} />, run: () => onTab('timeline') }
    : counts.proposed > 0
      ? { title: canReview ? `Review ${counts.proposed} proposed finding${counts.proposed === 1 ? '' : 's'}` : `Inspect ${counts.proposed} proposed finding${counts.proposed === 1 ? '' : 's'}`, description: 'Each draft includes its source wording and location. An authorized reviewer records the decision.', label: canReview ? 'Open finding review' : 'Inspect findings', icon: <ShieldCheck size={18} />, run: () => onTab('findings') }
      : proposedActions > 0
        ? { title: canReview ? `Review ${proposedActions} proposed corrective action${proposedActions === 1 ? '' : 's'}` : `Inspect ${proposedActions} proposed corrective action${proposedActions === 1 ? '' : 's'}`, description: 'Check the linked finding and action details. Approval and closure remain reviewer decisions.', label: canReview ? 'Open action review' : 'Inspect actions', icon: <ListChecks size={18} />, run: () => onTab('actions') }
        : data.exercise.objectives.length === 0 && onEditObjectives
          ? { title: 'Set exercise objectives', description: 'Add the targets evaluators will use before reviewing exercise evidence.', label: 'Add objectives', icon: <CheckCircle2 size={18} />, run: onEditObjectives }
          : data.sources.length === 0
            ? { title: canEdit ? 'Add evidence sources' : 'Inspect evidence', description: 'The exercise needs source records before it can build an evidence-backed review.', label: canEdit ? 'Open evidence library' : 'View evidence', icon: <FolderOpen size={18} />, run: () => onTab('evidence') }
            : !data.analysis_locked && canEdit
              ? { title: 'Run evidence analysis', description: 'Compare the imported records with the exercise objectives and prepare source-linked drafts.', label: busy ? 'Analysis in progress' : 'Run analysis', icon: <Sparkles size={18} />, run: onAnalyze }
              : !data.analysis_locked
                ? { title: 'Inspect exercise evidence', description: 'Evidence is available. An editor can run analysis when the exercise is ready.', label: 'Open evidence library', icon: <FolderOpen size={18} />, run: () => onTab('evidence') }
                : approvedActions > 0
                  ? { title: 'Follow up on approved actions', description: `${approvedActions} action${approvedActions === 1 ? ' is' : 's are'} approved and still need completion evidence before closure.`, label: 'Open action register', icon: <ListChecks size={18} />, run: () => onTab('actions') }
                  : unassessedObjectives > 0 && data.timeline.length > 0
                    ? { title: 'Inspect evidence for objectives needing review', description: 'Some objectives have no confirmed result from the available analysis. Check the source timeline.', label: 'Open evidence timeline', icon: <Clock3 size={18} />, run: () => onTab('timeline') }
                    : { title: 'Review or export the draft report', description: 'See which exercise records the PDF contains, what still needs review, and what limitations to disclose.', label: 'Open Reports', icon: <FileText size={18} />, run: () => onTab('reports') }

  const objectiveDetail = data.exercise.objectives.length === 0
    ? 'No objectives configured'
    : unassessedObjectives > 0
      ? `${unassessedObjectives} objective${unassessedObjectives === 1 ? '' : 's'} need${unassessedObjectives === 1 ? 's' : ''} review`
      : 'Assessment recorded for each objective'
  return <>
    <section className="overview-workflow" aria-label="Recommended next step and workflow">
      <div className="next-action-card">
        <div className="next-action-icon" aria-hidden="true">{nextAction.icon}</div>
        <div className="next-action-copy"><span className="section-kicker">RECOMMENDED NEXT STEP</span><h2>{nextAction.title}</h2><p>{nextAction.description}</p></div>
        <button className="button primary next-action-button" onClick={nextAction.run} disabled={busy}><span>{nextAction.label}</span><ChevronRight size={16} /></button>
      </div>
      <section className="workflow-card" aria-labelledby="workflow-heading">
        <SectionHeader title="Exercise workflow" description="Status from this exercise’s current records" headingId="workflow-heading" />
        <div className="workflow-steps">
          <WorkflowStep index="01" label="Evidence" detail={`${data.sources.length} source${data.sources.length === 1 ? '' : 's'} · ${data.timeline.length} observations`} status={data.sources.length ? 'Added' : 'Needs evidence'} tone={data.sources.length ? 'success' : 'warning'} onClick={() => onTab('evidence')} />
          <WorkflowStep index="02" label="Analysis" detail={data.analysis_locked ? 'Analysis has been run' : data.sources.length ? 'Ready when an editor runs it' : 'Waiting for source evidence'} status={data.analysis_locked ? 'Run' : data.sources.length ? 'Ready' : 'Waiting'} tone={data.analysis_locked ? 'info' : data.sources.length ? 'warning' : 'neutral'} onClick={!data.analysis_locked && canEdit ? onAnalyze : undefined} />
          <WorkflowStep index="03" label="Finding review" detail={data.findings.length ? `${counts.proposed} proposed · ${counts.approved} approved` : 'No findings prepared'} status={counts.proposed ? 'Decision needed' : data.findings.length ? 'Reviewed' : 'Waiting'} tone={counts.proposed ? 'warning' : data.findings.length ? 'success' : 'neutral'} onClick={() => onTab('findings')} />
          <WorkflowStep index="04" label="Corrective actions" detail={data.actions.length ? `${proposedActions} proposed · ${approvedActions} approved · ${closedActions} closed` : 'No actions prepared'} status={proposedActions ? 'Review needed' : data.actions.length ? 'In progress' : 'Waiting'} tone={proposedActions ? 'warning' : data.actions.length ? 'info' : 'neutral'} onClick={() => onTab('actions')} />
          <WorkflowStep index="05" label="Draft report" detail="Review contents and download the PDF" status="Available" tone="info" onClick={() => onTab('reports')} />
        </div>
      </section>
    </section>

    <section className="overview-snapshot" aria-labelledby="snapshot-heading">
      <SectionHeader title="Exercise snapshot" description="A quick view of objectives, evidence, decisions, and follow-up" headingId="snapshot-heading" />
      <div className="metrics-grid">
        <SummaryCard label="Objectives" value={String(data.exercise.objectives.length)} detail={objectiveDetail} icon={<CheckCircle2 size={19} />} tone="teal" />
        <SummaryCard label="Evidence sources" value={String(data.sources.length)} detail={`${data.timeline.length} extracted observation${data.timeline.length === 1 ? '' : 's'}`} icon={<FolderOpen size={19} />} tone="blue" />
        <SummaryCard label="Proposed findings" value={String(counts.proposed)} detail={`${data.findings.length} total · ${counts.approved} approved`} icon={<ShieldCheck size={19} />} tone="amber" />
        <SummaryCard label="Corrective actions" value={String(data.actions.length)} detail={`${proposedActions} proposed · ${approvedActions} approved`} icon={<ListChecks size={19} />} tone="violet" />
      </div>
    </section>

    <div className="overview-grid">
      <section className="panel timeline-panel">
        <SectionHeader title="Evidence timeline" description="Extracted observations with source locations" headingId="timeline-preview-heading" action={<button className="text-link" onClick={() => onTab('timeline')}>Full timeline <ChevronRight size={14} /></button>} />
        <div className="timeline-preview">
          {timeline.map((event, index) => <div className={`timeline-row ${event.time_confidence === 'uncertain' ? 'uncertain-row' : ''}`} key={event.id}>
            <div className="timeline-time">{shortTime(event.event_time_normalized)}</div><div className={`timeline-marker ${index === 0 ? 'first' : ''}`}><span /></div>
            <div className="timeline-event"><strong>{event.text}</strong><button className="source-link" onClick={() => onEvidence({ source_id: event.source_id, source_filename: event.source_filename, observation_id: event.id, source_locator: event.source_locator, text: event.text, event_time_normalized: event.event_time_normalized, time_confidence: event.time_confidence })}><FileText size={12} /> {event.source_filename} · {event.source_locator}</button></div>
            {event.time_confidence !== 'certain' && <span className={`certainty-pill ${event.time_confidence}`}>{timeLabel(event.time_confidence)}</span>}
          </div>)}
          {timeline.length === 0 && <EmptyPanel icon={<Clock3 size={21} />} title="No source observations yet" description="Add exercise notes or an event log to begin the timeline." action={<button className="button secondary" onClick={() => onTab('evidence')}>Open evidence library</button>} />}
        </div>
        {timeline.length > 0 && <button className="panel-bottom-link" onClick={() => onTab('timeline')}>Explore full event timeline <ChevronRight size={15} /></button>}
      </section>
      <section className="panel findings-panel">
        <SectionHeader title="Proposed findings" description="Source-linked drafts for evaluator review" headingId="finding-preview-heading" action={<button className="text-link" onClick={() => onTab('findings')}>View all <ChevronRight size={14} /></button>} />
        <div className="finding-summary"><span><i className="dot improvement" /> Areas for improvement <b>{improvements.length}</b></span><span><i className="dot strength" /> Strengths <b>{strengths.length}</b></span></div>
        <div className="finding-list-mini">
          {data.findings.slice(0, 4).map(finding => <button className="mini-finding" key={finding.id} onClick={() => onTab('findings')}>
            <span className={`finding-icon ${finding.category}`}>{finding.category === 'strength' ? <Check size={15} /> : <AlertTriangle size={14} />}</span>
            <span className="mini-finding-copy"><strong>{finding.title}</strong><small>{finding.objective_id || 'Objective mapping needed'} <span>·</span> {finding.evidence_ids.length} evidence links</small></span>
            <StatusBadge status={finding.status} /><ChevronRight size={14} className="mini-chevron" />
          </button>)}
          {data.findings.length === 0 && <EmptyPanel icon={<ShieldCheck size={21} />} title={data.analysis_locked ? 'No findings prepared for review' : 'No findings prepared yet'} description={data.analysis_locked ? 'The current analysis created no proposed findings. Objective results and source evidence remain available for evaluator review.' : 'Add exercise objectives and source material, then run evidence analysis to prepare source-linked drafts.'} />}
        </div>
        {data.findings.length > 0 && <div className="human-review-note"><ShieldCheck size={15} /><span><strong>Human decision stays with the evaluator.</strong><br />Proposed findings are not approved until an authorized reviewer decides.</span></div>}
        {data.findings.length > 0 && <button className="panel-bottom-link" onClick={() => onTab('findings')}>Review all findings <ChevronRight size={15} /></button>}
      </section>
    </div>

    <div className="bottom-grid">
      <section className="panel objective-panel"><SectionHeader title="Exercise objectives" description="Targets evaluators compare with source evidence" headingId="objective-preview-heading" action={<div className="objective-heading-actions"><span className="small-count">{data.exercise.objectives.length} objectives</span><button className="text-link" onClick={() => onTab('objectives')}>View details</button>{onEditObjectives && (data.analysis_locked ? <span className="objective-preview-locked"><LockKeyhole size={13} /> Read-only</span> : <button className="text-link" onClick={onEditObjectives}>Edit objectives</button>)}</div>} />
        {data.exercise.objectives.map((objective, index) => {
          const assessment = data.objective_assessments.find(item => item.objective_id === objective.id)
          const state = assessment?.state.replaceAll('_', ' ') || 'needs review'
          return <div className="objective-row" key={objective.id}><span className="objective-number">{String(index + 1).padStart(2, '0')}</span><span className="objective-id">{objective.id}</span><p>{objective.text}</p><StatusBadge status={state} /></div>
        })}
        {data.exercise.objectives.length === 0 && <EmptyPanel icon={<CheckCircle2 size={21} />} title="No objectives configured" description="Analysis stays paused until an editor adds the exercise targets." action={onEditObjectives ? <button className="button secondary" onClick={onEditObjectives}>Add objectives</button> : undefined} />}
      </section>
      <section className="panel action-preview"><SectionHeader title="Corrective actions" description="Improvement tasks and their current review status" headingId="action-preview-heading" action={<button className="text-link" onClick={() => onTab('actions')}>View register <ChevronRight size={14} /></button>} />
        {data.actions.slice(0, 3).map(action => <div className="action-preview-row" key={action.id}><span className={`priority-line ${action.priority}`} /><span className="action-preview-copy"><strong>{action.title}</strong><small>{action.owner || <span className="owner-missing">Owner not assigned</span>}</small></span><StatusBadge status={action.status === 'closed' ? 'closed' : action.status} /></div>)}
        {data.actions.length === 0 && <EmptyPanel icon={<ListChecks size={21} />} title="No actions prepared" description="Proposed improvement actions appear after findings are reviewed." />}
        {data.actions.length > 0 && <button className="button secondary full-width" onClick={() => onTab('actions')} disabled={busy}><ListChecks size={15} /> Open corrective action register</button>}
      </section>
    </div>
  </>
}

function SummaryCard({ label, value, detail, icon, tone }: { label: string; value: string; detail: string; icon: React.ReactNode; tone: string }) {
  return <article className={`metric-card summary-card ${tone}`}><div className={`metric-icon ${tone}`}>{icon}</div><div className="metric-content"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div></article>
}

function StatusBadge({ status, tone }: { status: string; tone?: 'neutral' | 'success' | 'warning' | 'danger' | 'info' }) {
  const normalized = status.toLowerCase()
  const derivedTone = tone || (['approved', 'closed', 'confirmed success', 'confirmed_success', 'review decisions recorded', 'reviewed'].includes(normalized) ? 'success' : normalized === 'rejected' || normalized.includes('confirmed failure') || normalized.includes('confirmed_failure') ? 'danger' : normalized.includes('proposed') || normalized.includes('review') || normalized.includes('needs') || normalized.includes('conflict') ? 'warning' : normalized === 'waiting' || normalized.includes('not ') ? 'neutral' : 'info')
  return <span className={`status-badge ${derivedTone}`}><span className="status-badge-mark" aria-hidden="true" />{status}</span>
}

function SectionHeader({ title, description, action, headingId }: { title: string; description: string; action?: React.ReactNode; headingId?: string }) {
  return <div className="panel-heading section-header"><div><h2 id={headingId}>{title}</h2><p>{description}</p></div>{action && <div className="section-header-action">{action}</div>}</div>
}

function WorkflowStep({ index, label, detail, status, tone, onClick }: { index: string; label: string; detail: string; status: string; tone: 'neutral' | 'success' | 'warning' | 'danger' | 'info'; onClick?: () => void }) {
  const content = <><span className="workflow-index">{index}</span><span className="workflow-step-copy"><strong>{label}</strong><small>{detail}</small></span><StatusBadge status={status} tone={tone} /></>
  return onClick
    ? <button className="workflow-step" onClick={onClick}>
      {content}<ChevronRight size={15} className="workflow-chevron" />
    </button>
    : <div className="workflow-step">{content}</div>
}

function EmptyPanel({ icon, title, description, action }: { icon: React.ReactNode; title: string; description: string; action?: React.ReactNode }) {
  return <div className="empty-panel"><span className="empty-panel-icon">{icon}</span><strong>{title}</strong><p>{description}</p>{action && <div className="empty-panel-action">{action}</div>}</div>
}

function EvidenceView({ data, capabilities, canEdit, busy, uploading, filteredSources, sourceFilter, setSourceFilter, syntheticSourceIds, onUpload, onSource, onEvidence, onGoTimeline, onTranscribe }: { data: Detail; capabilities: Capabilities | null; canEdit: boolean; busy: boolean; uploading: boolean; filteredSources: Source[]; sourceFilter: string; setSourceFilter: (value: string) => void; syntheticSourceIds: Set<string>; onUpload: (files: File[]) => Promise<boolean>; onSource: (source: Source) => void; onEvidence: (item: Support) => void; onGoTimeline: () => void; onTranscribe: (file?: File) => void }) {
  const [dragging, setDragging] = useState(false)
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [selectionError, setSelectionError] = useState('')
  const conflictIds = new Set(data.timeline_conflicts.map(item => item.observation_id))
  const observations = [...data.timeline].sort((left, right) => (left.event_time_normalized || '9999').localeCompare(right.event_time_normalized || '9999'))
  const validateSelection = (files: File[]) => {
    if (files.length > 10) return 'Choose up to 10 files in one upload.'
    const unsupported = files.find(file => !/\.(txt|md|log|csv|json|pdf)$/i.test(file.name))
    if (unsupported) return `${unsupported.name} is not a supported evidence format. Choose TXT, MD, LOG, CSV, JSON, or selectable-text PDF.`
    if (files.some(file => file.size === 0)) return 'One or more selected files are empty. Choose a file that contains evidence.'
    if (files.some(file => file.size > 15 * 1024 * 1024)) return 'Each file must be 15 MB or smaller.'
    if (files.reduce((total, file) => total + file.size, 0) > 30 * 1024 * 1024) return 'The selected files exceed the 30 MB batch limit. Remove a file and try again.'
    return ''
  }
  const handleFileList = (files: FileList | null) => {
    if (busy) return
    const next = files ? Array.from(files) : []
    if (!next.length) return
    setSelectedFiles(next)
    setSelectionError(validateSelection(next))
  }
  const submitUpload = async () => {
    if (!selectedFiles.length || selectionError || busy) return
    if (await onUpload(selectedFiles)) {
      setSelectedFiles([])
      setSelectionError('')
    }
  }
  const isFictionalExercise = data.exercise.id === 'HOSP-PO-2026-01'
  const totalObservations = data.timeline.length
  const supportedDescription = 'TXT, MD, LOG, CSV, JSON, or selectable-text PDF. Up to 15 MB per file, 10 files, and 30 MB per upload.'
  return <div className="tab-page et-page">
    <div className="et-page-head">
      <div className="et-page-copy"><p className="et-eyebrow">SOURCE RECORDS</p><h2 id="evidence-page-title">Evidence</h2><p>Review uploaded records and the observations extracted from each one.</p></div>
      <div className="et-page-actions"><div className="et-exercise-context"><span>SELECTED EXERCISE</span><strong>{data.exercise.title}</strong><small>{data.exercise.id}</small></div>{canEdit && <label className="button primary et-select-files"><Upload size={17} /> Select evidence files<input className="et-native-file" aria-describedby="evidence-upload-guidance" type="file" multiple disabled={busy} accept=".txt,.md,.log,.csv,.json,.pdf,text/plain,text/markdown,text/csv,application/json,application/pdf" onChange={event => { handleFileList(event.currentTarget.files); event.currentTarget.value = '' }} /></label>}</div>
    </div>
    {isFictionalExercise && <div className="et-fictional-banner"><Sparkles size={17} /><p><strong>Fictional demo exercise.</strong> Preloaded records are synthetic. Later imports are labeled as uploaded sources.</p></div>}
    {canEdit && <section className={`et-dropzone ${dragging ? 'is-dragging' : ''}`} onDragOver={event => { event.preventDefault(); setDragging(true) }} onDragLeave={event => { if (event.currentTarget === event.target) setDragging(false) }} onDrop={event => { event.preventDefault(); setDragging(false); handleFileList(event.dataTransfer.files) }} aria-label="Evidence file drop area">
      <div className="et-drop-icon"><Upload size={20} /></div><div><strong>Or drop files here</strong><p id="evidence-upload-guidance">{supportedDescription} PDF must contain selectable text. PDFs are limited to 250 pages; structured evidence to 10,000 records.</p></div>
    </section>}
    {selectedFiles.length > 0 && <section className="et-upload-review" aria-labelledby="selected-files-heading">
      <div className="et-upload-review-head"><div><h3 id="selected-files-heading">Selected files</h3><p>{uploading ? 'The server is checking and extracting these files.' : `${selectedFiles.length} file${selectedFiles.length === 1 ? '' : 's'} selected for review before import`}</p></div><button type="button" className="et-text-button" onClick={() => { setSelectedFiles([]); setSelectionError('') }} disabled={busy}>Clear selection</button></div>
      <ul className="et-selected-files">{selectedFiles.map((file, index) => <li key={`${file.name}-${file.size}-${index}`}><FileText size={17} /><span><strong title={file.name}>{file.name}</strong><small>{file.size === 0 ? 'Empty file' : file.size < 1024 * 1024 ? `${Math.max(1, Math.round(file.size / 1024))} KB` : `${(file.size / (1024 * 1024)).toFixed(2)} MB`}</small></span><button type="button" className="et-remove-file" aria-label={`Remove ${file.name}`} onClick={() => { const rest = selectedFiles.filter((_, fileIndex) => fileIndex !== index); setSelectedFiles(rest); setSelectionError(validateSelection(rest)) }} disabled={busy}><X size={16} /></button></li>)}</ul>
      {selectionError && <p className="et-inline-error" role="alert"><AlertTriangle size={16} />{selectionError}</p>}
      {uploading && <p className="et-upload-status" role="status"><LoaderCircle className="spin" size={16} /> Checking and extracting the selected files. This may take a moment.</p>}
      <div className="et-upload-review-footer"><span>No source is added until the server finishes checking and extracting the files.</span><button type="button" className="button primary" onClick={() => void submitUpload()} disabled={busy || Boolean(selectionError)}><Upload size={15} />{uploading ? 'Processing evidence…' : `Upload ${selectedFiles.length} file${selectedFiles.length === 1 ? '' : 's'}`}</button></div>
    </section>}
    {!canEdit && <div className="et-readonly-note"><LockKeyhole size={16} /> Evidence is available for review. An editor can add more source records.</div>}
    <section className="et-section" aria-labelledby="evidence-sources-heading">
      <div className="et-section-head"><div><h3 id="evidence-sources-heading">Evidence sources <span className="et-count">{data.sources.length}</span></h3><p>Each source keeps its original filename, extraction result, and scan state where available.</p></div><label className="et-search"><Search size={17} /><span className="sr-only">Search evidence sources by filename</span><input value={sourceFilter} onChange={event => setSourceFilter(event.target.value)} placeholder="Search filenames" />{sourceFilter && <button type="button" onClick={() => setSourceFilter('')} aria-label="Clear source search"><X size={15} /></button>}</label></div>
      {filteredSources.length > 0 ? <div className="et-source-grid">{filteredSources.map(source => {
        const synthetic = syntheticSourceIds.has(source.id)
        const count = source.observation_count
        const sourceTypeIcon = source.kind === 'csv' ? <Activity size={19} /> : source.kind === 'transcript' ? <AudioLines size={19} /> : source.kind === 'pdf' ? <FileText size={19} /> : <MessageSquareText size={19} />
         return <button type="button" className="et-source-card" key={source.id} onClick={() => onSource(source)}>
          <span className={`et-source-icon ${source.kind}`}>{sourceTypeIcon}</span><span className="et-source-card-copy"><span className="et-source-name-row"><strong title={source.filename}>{source.filename}</strong><span className="et-source-type">{source.kind}</span></span><span className="et-source-summary">{count} extracted observation{count === 1 ? '' : 's'} · SHA-256 {source.sha256.slice(0, 12)}…</span><span className="et-source-badges"><span className={`et-source-badge ${synthetic ? 'synthetic' : 'uploaded'}`}>{synthetic ? 'Fictional demo source' : 'Uploaded source'}</span><span className={`et-scan-badge ${source.scan_status}`}>{scanLabel(source.scan_status)}</span></span></span><ChevronRight size={18} className="et-source-chevron" aria-hidden="true" />
        </button>
      })}</div> : data.sources.length ? <div className="et-empty et-empty-search"><Search size={23} /><h4>No source matches “{sourceFilter}”</h4><p>Clear the search to see all {data.sources.length} source{data.sources.length === 1 ? '' : 's'}.</p><button type="button" className="button secondary" onClick={() => setSourceFilter('')}>Show all sources</button></div> : <div className="et-empty"><div className="et-empty-icon"><FolderOpen size={23} /></div><h4>Upload exercise evidence to begin</h4><p>Add notes, logs, transcripts, or selectable-text reports. DrillLoop will keep each extracted observation linked to its source location.</p></div>}
    </section>
    <section className="et-section et-observations-section" aria-labelledby="extracted-observations-heading">
      <div className="et-section-head"><div><h3 id="extracted-observations-heading">Extracted observations <span className="et-count">{totalObservations}</span></h3><p>Exact extracted wording stays connected to its source and locator.</p></div><button type="button" className="et-inline-link" onClick={onGoTimeline}>Open timeline <ChevronRight size={15} /></button></div>
      {observations.length ? <div className="et-observation-list">{observations.map(observation => {
        const source = data.sources.find(item => item.id === observation.source_id)
        const conflict = conflictIds.has(observation.id)
        return <article className={`et-observation ${conflict ? 'has-conflict' : ''}`} key={observation.id}>
          <div className="et-observation-time"><strong>{conflict ? 'No agreed event time' : timelineTime(observation.event_time_normalized, data.exercise.exercise_date)}</strong><span>{conflict ? `Source note time · ${timelineTime(observation.event_time_normalized, data.exercise.exercise_date)}` : eventTimeLabel(observation.time_confidence)}</span></div>
          <div className="et-observation-copy"><p>{observation.text}</p><span className="et-observation-ref">{observation.source_filename} <span aria-hidden="true">·</span> {observation.source_locator}</span>{isTranscript(source) && <small className="et-locator-help">Transcript segment offsets locate speech in the recording; they are not event times.</small>}</div>
          <div className="et-observation-actions">{observation.recognition_confidence !== null && <span className={`et-recognition ${observation.recognition_confidence < .75 ? 'low' : ''}`}>Speech match {Math.round(observation.recognition_confidence * 100)}%</span>}<button type="button" className="et-inline-link" onClick={() => onEvidence({ source_id: observation.source_id, source_filename: observation.source_filename, observation_id: observation.id, source_locator: observation.source_locator, text: observation.text, event_time_normalized: observation.event_time_normalized, time_confidence: observation.time_confidence })}><FileText size={15} /> Open source record</button></div>
        </article>
      })}</div> : <div className="et-empty et-empty-compact"><FileText size={21} /><p>Extracted observations will appear here after evidence is imported.</p></div>}
      {data.timeline_conflicts.length > 0 && <div className="et-conflict-summary"><AlertTriangle size={18} /><div><strong>{data.timeline_conflicts.length} timing issue{data.timeline_conflicts.length === 1 ? '' : 's'} need reviewer attention</strong><p>Open the timeline to review the original wording and any different times it names. DrillLoop leaves the disagreement unresolved.</p></div></div>}
    </section>
    <details className="et-audio-details"><summary><AudioLines size={18} /><span><strong>Optional offline audio transcription</strong><small>Uses a locally configured model, when available</small></span><span className={`et-asr-state ${capabilities?.asr.available ? 'available' : 'unavailable'}`}>{capabilities?.asr.available ? 'Model available' : 'Model unavailable'}</span></summary><div className="et-audio-body"><p>{capabilities?.asr.note || 'Provide a local model directory to enable audio transcription.'} Transcripts need human checking. Speaker separation is not provided.</p><dl><div><dt>Software</dt><dd>{capabilities?.asr.package_version || 'Not installed'}</dd></div><div><dt>Language</dt><dd>Detected at runtime</dd></div><div><dt>Speaker separation</dt><dd>Not provided</dd></div></dl>{canEdit && <label className={`button secondary et-audio-select ${!capabilities?.asr.available || busy ? 'disabled-look' : ''}`}>Choose audio file<input className="et-native-file" type="file" accept="audio/wav,audio/mpeg,audio/mp4,audio/flac,audio/ogg,.wav,.mp3,.m4a,.flac,.ogg" disabled={!capabilities?.asr.available || busy} onChange={event => { onTranscribe(event.currentTarget.files?.[0]); event.currentTarget.value = '' }} /></label>}</div></details>
  </div>
}

function TimelineView({ data, focusObservationId, onFocusConsumed, onEvidence, onGoEvidence }: { data: Detail; focusObservationId: string; onFocusConsumed: () => void; onEvidence: (item: Support) => void; onGoEvidence: () => void }) {
  const [query, setQuery] = useState('')
  const [sourceId, setSourceId] = useState('')
  const [timeFilter, setTimeFilter] = useState<'all' | 'recorded' | 'needs-review' | 'missing'>('all')
  useEffect(() => {
    if (!focusObservationId) return
    const frame = window.requestAnimationFrame(() => {
      const target = document.getElementById(`timeline-event-${focusObservationId}`)
      target?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      target?.focus({ preventScroll: true })
      onFocusConsumed()
    })
    return () => window.cancelAnimationFrame(frame)
  }, [focusObservationId, onFocusConsumed])
  const conflictByObservation = new Map(data.timeline_conflicts.map(item => [item.observation_id, item]))
  const matches = (event: Observation) => {
    if (sourceId && event.source_id !== sourceId) return false
    const conflict = conflictByObservation.has(event.id)
    const hasTime = Boolean(event.event_time_normalized) && event.time_confidence !== 'unknown'
    const needsReview = conflict || event.time_confidence === 'uncertain' || event.time_confidence === 'medium'
    if (timeFilter === 'recorded' && (!hasTime || conflict)) return false
    if (timeFilter === 'needs-review' && !needsReview) return false
    if (timeFilter === 'missing' && (hasTime || conflict)) return false
    const normalizedQuery = query.trim().toLocaleLowerCase()
    return !normalizedQuery || `${event.text} ${event.source_filename} ${event.source_locator} ${event.event_time_raw || ''} ${event.event_time_normalized || ''}`.toLocaleLowerCase().includes(normalizedQuery)
  }
  const filtered = data.timeline.filter(matches)
  const conflicts = filtered.filter(event => conflictByObservation.has(event.id))
  const chronological = filtered.filter(event => !conflictByObservation.has(event.id) && Boolean(event.event_time_normalized) && event.time_confidence !== 'unknown').sort((left, right) => (left.event_time_normalized || '').localeCompare(right.event_time_normalized || '') || left.source_filename.localeCompare(right.source_filename) || left.source_locator.localeCompare(right.source_locator))
  const withoutTime = filtered.filter(event => !conflictByObservation.has(event.id) && (!event.event_time_normalized || event.time_confidence === 'unknown'))
  const activeFilters = Boolean(query || sourceId || timeFilter !== 'all')
  const resetFilters = () => { setQuery(''); setSourceId(''); setTimeFilter('all') }
  const openRecord = (event: Observation) => onEvidence({ source_id: event.source_id, source_filename: event.source_filename, observation_id: event.id, source_locator: event.source_locator, text: event.text, event_time_normalized: event.event_time_normalized, time_confidence: event.time_confidence })
  const renderEvent = (event: Observation, kind: 'ordered' | 'conflict' | 'unknown') => {
    const conflict = conflictByObservation.get(event.id)
    const source = data.sources.find(item => item.id === event.source_id)
    const mentionedTimes = conflict ? timeMentions(event.text) : []
    const statusText = kind === 'conflict' ? 'Timing disagreement · not ordered' : kind === 'unknown' ? 'Event time not recorded' : eventTimeLabel(event.time_confidence)
    return <article className={`et-timeline-event ${kind} ${event.time_confidence}`} id={`timeline-event-${event.id}`} tabIndex={-1} key={event.id}>
      <div className="et-event-rail" aria-hidden="true"><span className="et-event-dot" /><span className="et-event-line" /></div>
      <div className="et-event-card">
        <div className="et-event-header"><div className="et-event-time">{kind === 'ordered' ? <><time dateTime={event.event_time_normalized || undefined}>{timelineTime(event.event_time_normalized, data.exercise.exercise_date)}</time><span>{statusText}</span></> : <><strong>{kind === 'conflict' ? 'Time disagreement' : 'No event time recorded'}</strong><span>{statusText}</span></>}</div><span className="et-event-badges"><span className={`et-event-kind ${event.observation_type}`}>{event.observation_type.replace(/_/g, ' ')}</span>{event.recognition_confidence !== null && <span className={`et-recognition ${event.recognition_confidence < .75 ? 'low' : ''}`}>Speech match {Math.round(event.recognition_confidence * 100)}%</span>}</span></div>
        <p className="et-event-text">{event.text}</p>
        {kind === 'conflict' && <div className="et-conflict-detail"><div className="et-conflict-detail-heading"><AlertTriangle size={17} /><strong>Two records report different times. Review the originals before drawing a conclusion.</strong></div><p>This source explicitly marks the event time as unresolved. DrillLoop has not selected a time or placed this observation in chronological order.</p>{mentionedTimes.length > 0 && <div className="et-times-mentioned"><span>Times mentioned in this source text</span>{mentionedTimes.map(time => <strong key={time}>{time}</strong>)}</div>}<small>Time attached to this note: {timelineTime(event.event_time_normalized, data.exercise.exercise_date)} · this is separate from the disputed event time.</small></div>}
        {kind === 'unknown' && <p className="et-unknown-note">This observation remains outside the ordered timeline because the source does not provide a reliable event time.</p>}
        <div className="et-event-source"><span><FileText size={15} /> {event.source_filename} <span aria-hidden="true">·</span> {event.source_locator}</span><button type="button" className="et-inline-link" onClick={() => openRecord(event)}>Open source record <ChevronRight size={15} /></button></div>
        {isTranscript(source) && <p className="et-locator-help">Transcript segment offsets are source locations, not event timestamps.</p>}
      </div>
    </article>
  }
  return <div className="tab-page et-page">
    <div className="et-page-head et-timeline-head"><div className="et-page-copy"><p className="et-eyebrow">EVENT SEQUENCE</p><h2 id="timeline-page-title">Timeline</h2><p>See what the records say happened and when. Disputed and missing times stay separate from the ordered events.</p></div><div className="et-timeline-counts"><span><strong>{chronological.length}</strong><small>ordered</small></span><span><strong>{conflicts.length}</strong><small>unresolved</small></span><span><strong>{withoutTime.length}</strong><small>no event time</small></span></div></div>
    <div className="et-timeline-note"><HelpCircle size={17} /><p>Only source-reported event times are used for chronology. Transcript offsets locate speech in the recording; they do not establish event time. Disputed or missing times stay unplaced.</p></div>
    {data.timeline.length === 0 ? <div className="et-empty et-timeline-empty"><div className="et-empty-icon"><Clock3 size={24} /></div><h4>Timeline starts with source evidence</h4><p>Upload an exercise log or notes. Observations will appear with their source location and any time found in the record.</p><button type="button" className="button primary" onClick={onGoEvidence}>Open evidence library</button></div> : <>
      <section className="et-timeline-toolbar" aria-label="Timeline filters"><label className="et-timeline-search"><Search size={17} /><span className="sr-only">Search timeline events and source references</span><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search events or source references" />{query && <button type="button" aria-label="Clear event search" onClick={() => setQuery('')}><X size={15} /></button>}</label><label className="et-filter-control"><span>Source</span><select value={sourceId} onChange={event => setSourceId(event.target.value)}><option value="">All sources</option>{data.sources.map(source => <option key={source.id} value={source.id}>{source.filename}</option>)}</select></label><label className="et-filter-control"><span>Timing</span><select value={timeFilter} onChange={event => setTimeFilter(event.target.value as typeof timeFilter)}><option value="all">All timing states</option><option value="recorded">Time available</option><option value="needs-review">Needs review</option><option value="missing">No event time</option></select></label>{activeFilters && <button type="button" className="et-reset-filters" onClick={resetFilters}>Show all events</button>}</section>
      {filtered.length === 0 ? <div className="et-empty et-filter-empty"><Search size={23} /><h4>No events match these filters</h4><p>Try another source or timing state.</p><button type="button" className="button secondary" onClick={resetFilters}>Show all events</button></div> : <div className="et-timeline-groups">
        {chronological.length > 0 && <section className="et-timeline-group" aria-labelledby="ordered-events-heading"><div className="et-group-heading"><div><span className="et-group-kicker">CHRONOLOGICAL</span><h3 id="ordered-events-heading">Events with a recorded time <span>{chronological.length}</span></h3></div><p>Ordered by the timestamp available in each source.</p></div><div className="et-timeline-list">{chronological.map(event => renderEvent(event, 'ordered'))}</div></section>}
        {conflicts.length > 0 && <section className="et-timeline-group et-conflict-group" aria-labelledby="conflict-events-heading"><div className="et-group-heading"><div><span className="et-group-kicker">REVIEW NEEDED</span><h3 id="conflict-events-heading">Conflicting or unresolved times <span>{conflicts.length}</span></h3></div><p>These records are kept outside the time order until reviewed.</p></div><div className="et-timeline-list">{conflicts.map(event => renderEvent(event, 'conflict'))}</div></section>}
      {withoutTime.length > 0 && <section className="et-timeline-group et-unknown-group" aria-labelledby="unknown-events-heading"><div className="et-group-heading"><div><span className="et-group-kicker">UNPLACED</span><h3 id="unknown-events-heading">No reliable event time <span>{withoutTime.length}</span></h3></div><p>Listed by source reference only; no event order is inferred.</p></div><div className="et-timeline-list">{withoutTime.map(event => renderEvent(event, 'unknown'))}</div></section>}
      </div>}
    </>}
  </div>
}

function SourceModal({ source, data, isSynthetic, focusedObservationId, onTimeline, onClose }: { source: Source; data: Detail; isSynthetic: boolean; focusedObservationId: string; onTimeline: (observationId: string) => void; onClose: () => void }) {
  const dialogRef = useAccessibleDialog<HTMLElement>(onClose)
  const observations = data.timeline.filter(item => item.source_id === source.id)
  const provenance = source.provenance
  useEffect(() => {
    if (!focusedObservationId) return
    document.getElementById(`source-observation-${focusedObservationId}`)?.scrollIntoView({ block: 'nearest' })
  }, [focusedObservationId])
  return <div className="modal-shade et-modal-shade" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}><section ref={dialogRef} className="et-source-modal" role="dialog" aria-modal="true" aria-labelledby="source-detail-heading" tabIndex={-1}>
    <div className="et-modal-heading"><div className="et-modal-file-icon"><FileText size={19} /></div><div><span>SOURCE DETAILS</span><h2 id="source-detail-heading" title={source.filename}>{source.filename}</h2><small>{source.kind} · {observations.length} extracted observation{observations.length === 1 ? '' : 's'}</small></div><button type="button" className="icon-button" onClick={onClose} aria-label="Close source details"><X size={18} /></button></div>
    {isSynthetic && <div className="et-modal-fictional"><Sparkles size={16} /><strong>Fictional synthetic demo evidence</strong></div>}
    <div className="et-source-status-row"><span className="et-source-badge uploaded">{isSynthetic ? 'Seeded demo source' : 'Uploaded source'}</span><span className={`et-scan-badge ${source.scan_status}`}>{scanLabel(source.scan_status)}</span><span>{observations.length} observation{observations.length === 1 ? '' : 's'} extracted</span></div>
    <div className="et-source-modal-body"><h3>Extracted observations</h3><p>Wording is preserved from the source. Locators identify a row, line, page, or transcript segment when available.</p>
      {observations.length ? <div className="et-source-observation-list">{observations.map(observation => <article id={`source-observation-${observation.id}`} className={`et-source-observation ${focusedObservationId === observation.id ? 'et-source-observation-focused' : ''}`} key={observation.id}><div className="et-source-observation-top"><span><MapPin size={14} /> {observation.source_locator}</span><span>{observation.event_time_raw ? `Source time: ${observation.event_time_raw}` : 'No explicit event time'}</span></div><blockquote>{observation.text}</blockquote><div className="et-source-observation-actions"><span>{eventTimeLabel(observation.time_confidence)}{observation.recognition_confidence !== null ? ` · Speech match ${Math.round(observation.recognition_confidence * 100)}%` : ''}</span><button type="button" className="et-inline-link" onClick={() => onTimeline(observation.id)}>View on timeline <ChevronRight size={15} /></button></div></article>)}</div> : <div className="et-empty et-empty-compact"><p>No observations were extracted from this file.</p></div>}
      {source.kind === 'transcript' && <p className="et-locator-help">Segment offsets locate transcript text inside the recording. They are not event timestamps unless the source explicitly includes an event time.</p>}
      <details className="et-source-provenance"><summary>Source reference and processing details</summary><dl><div><dt>Source ID</dt><dd>{source.id}</dd></div><div><dt>SHA-256 file fingerprint</dt><dd>{source.sha256}</dd></div><div><dt>Media type</dt><dd>{source.mime_type}</dd></div>{typeof provenance.model === 'string' && <div><dt>Transcript model</dt><dd>{provenance.model}</dd></div>}{typeof provenance.language === 'string' && <div><dt>Transcript language value</dt><dd>{provenance.language}</dd></div>}</dl></details>
    </div>
    <div className="et-modal-footer"><span>Original file remains linked to this source record.</span><div><a className="button secondary" href={`/api/sources/${source.id}/download`}><ArrowDownToLine size={15} /> Download original file</a><button type="button" className="button secondary" onClick={onClose}>Close</button></div></div>
  </section></div>
}

function actionLabel(value: string) {
  return ({ finding_approved: 'Finding approved', finding_rejected: 'Finding rejected', finding_edited: 'Finding details edited', action_approved: 'Action approved', action_rejected: 'Action rejected', action_updated: 'Action details updated', action_closed: 'Closure evidence recorded' } as Record<string, string>)[value] || value.replace(/_/g, ' ')
}

function eventTime(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

function AuditHistory({ events }: { events: AuditEvent[] }) {
  if (!events.length) return <p className="fa-history-empty">No reviewer decision has been recorded.</p>
  return <details className="fa-audit-history"><summary><History size={15} /> Review and change history <span>{events.length}</span></summary><ol>{events.map((event, index) => <li key={`${event.action}-${event.created_at}-${index}`}><span className="fa-history-mark" aria-hidden="true" /><div><strong>{actionLabel(event.action)}</strong><span>{event.actor} · {eventTime(event.created_at)}</span>{typeof event.details?.note === 'string' && event.details.note.trim() && <p>Reviewer note: {event.details.note}</p>}{typeof event.details?.closure_evidence === 'string' && event.details.closure_evidence.trim() && <blockquote>{event.details.closure_evidence}</blockquote>}</div></li>)}</ol></details>
}

function WorkflowStatus({ status, finding = false }: { status: string; finding?: boolean }) {
  const Icon = status === 'approved' || status === 'closed' ? CheckCircle2 : status === 'rejected' ? XCircle : Clock3
  const label = status === 'proposed' ? (finding ? 'Proposed · needs review' : 'Proposed') : status.charAt(0).toUpperCase() + status.slice(1)
  return <span className={`fa-status fa-status--${status}`}><Icon size={14} aria-hidden="true" />{label}</span>
}

function FindingEvidence({ evidence, onEvidence }: { evidence: Support[]; onEvidence: (item: Support) => void }) {
  return <section className="fa-evidence" aria-label="Observed evidence"><div className="fa-section-label"><div><FileCheck2 size={17} /><h4>Observed evidence · source wording</h4></div><span>{evidence.length} cited record{evidence.length === 1 ? '' : 's'}</span></div>
    {evidence.length ? <div className="fa-evidence-list">{evidence.map(item => <button className="fa-evidence-link" key={item.observation_id} onClick={() => onEvidence(item)}><span className="fa-evidence-file"><FileText size={17} /></span><span className="fa-evidence-copy"><strong>{item.source_filename}</strong><small>{item.source_locator}{item.event_time_normalized ? ` · Source time ${shortTime(item.event_time_normalized)}` : ''}</small><q>{item.text}</q></span><ChevronRight size={17} className="fa-evidence-chevron" /></button>)}</div> : <div className="fa-evidence-missing"><AlertTriangle size={17} /><p><strong>Source support is unavailable.</strong> This finding has no source wording to inspect. Keep it under evaluator review; approval is disabled.</p></div>}
  </section>
}

function FindingWorkflow({ finding, actions }: { finding: Finding; actions: Action[] }) {
  const statusText = finding.status === 'proposed' ? 'Awaiting reviewer decision' : `${finding.status.charAt(0).toUpperCase()}${finding.status.slice(1)}${finding.reviewer ? ` by ${finding.reviewer}` : ''}`
  const actionClosed = actions.some(action => action.status === 'closed')
  const actionClass = actionClosed ? 'is-complete' : finding.status === 'approved' && actions.length ? 'is-current' : 'is-pending'
  const actionSummary = actions.length ? actions.map(action => action.status === 'closed' ? 'Closure evidence recorded' : action.status === 'approved' ? 'Approved · closure evidence needed' : action.status === 'rejected' ? 'Rejected · may be reviewed again' : 'Proposed').join(', ') : 'No linked action'
  const decisionClass = finding.status === 'proposed' ? 'is-current' : finding.status === 'rejected' ? 'is-rejected' : 'is-complete'
  return <section className="fa-workflow" aria-label="Finding and corrective action workflow"><div className="fa-workflow-step is-complete"><span>1</span><div><strong>Finding proposed</strong><small>Source-linked analysis draft</small></div></div><ChevronRight size={16} aria-hidden="true" /><div className={`fa-workflow-step ${decisionClass}`}><span>2</span><div><strong>Human decision</strong><small>{statusText}</small></div></div><ChevronRight size={16} aria-hidden="true" /><div className={`fa-workflow-step ${actionClass}`}><span>3</span><div><strong>Corrective action</strong><small>{actionSummary}</small></div></div></section>
}

function FindingsView({ data, busy, canEdit, canReview, identityName, isSyntheticDemo, onReview, onEvidence }: { data: Detail; busy: boolean; canEdit: boolean; canReview: boolean; identityName: string; isSyntheticDemo: boolean; onReview: (finding: Finding, decision: 'approved' | 'rejected') => void; onEvidence: (item: Support) => void }) {
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('all')
  const [objectiveId, setObjectiveId] = useState('all')
  const proposed = data.findings.filter(finding => finding.status === 'proposed').length
  const visible = data.findings.filter(finding => {
    const objective = data.exercise.objectives.find(item => item.id === finding.objective_id)
    const matchQuery = `${finding.title} ${finding.code} ${finding.observation} ${finding.interpretation} ${objective?.text || ''} ${finding.supporting_evidence.map(item => `${item.source_filename} ${item.source_locator}`).join(' ')}`.toLowerCase().includes(query.trim().toLowerCase())
    const matchObjective = objectiveId === 'all' || (objectiveId === '' ? !finding.objective_id || !data.exercise.objectives.some(item => item.id === finding.objective_id) : finding.objective_id === objectiveId)
    return matchQuery && (status === 'all' || finding.status === status) && matchObjective
  })
  return <div className="tab-page fa-page">
    <header className="fa-page-heading"><div><p className="fa-eyebrow">EVALUATION FINDINGS</p><h2>Findings</h2><p>Review each proposed conclusion against the original source wording. Evidence, analysis and your decision stay clearly separated.</p></div><div className="fa-heading-count"><strong>{data.findings.length}</strong><span>finding{data.findings.length === 1 ? '' : 's'}</span><span className="fa-count-divider" /><strong>{proposed}</strong><span>need review</span></div></header>
    {isSyntheticDemo && <div className="fa-fictional"><Sparkles size={16} /><strong>Fictional synthetic demo data</strong><span>These exercise events and records are not real operational evidence.</span></div>}
    <div className={`fa-access-note ${canReview ? 'is-reviewer' : canEdit ? 'is-editor' : 'is-viewer'}`}><LockKeyhole size={17} /><span>{canReview ? <>Review decisions will be recorded as <strong>{identityName}</strong>.</> : canEdit ? 'Evaluator access · you can view findings and edit action details; a reviewer must record decisions.' : 'Viewer access · decisions and action edits are not available to this account.'}</span></div>
    <section className="fa-process-strip" aria-label="Evaluation workflow"><span className="fa-process-current"><i>1</i> Proposed finding</span><ChevronRight size={15} /><span><i>2</i> Human decision</span><ChevronRight size={15} /><span><i>3</i> Corrective action</span></section>
    {data.findings.length > 0 && <section className="fa-toolbar" aria-label="Findings filters"><label className="fa-search"><Search size={17} /><span className="sr-only">Search findings</span><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search findings, objectives or sources" />{query && <button type="button" aria-label="Clear finding search" onClick={() => setQuery('')}><X size={15} /></button>}</label><label className="fa-filter"><span>Status</span><select value={status} onChange={event => setStatus(event.target.value)}><option value="all">All statuses</option><option value="proposed">Proposed · needs review</option><option value="approved">Approved</option><option value="rejected">Rejected</option></select></label><label className="fa-filter"><span>Objective</span><select value={objectiveId} onChange={event => setObjectiveId(event.target.value)}><option value="all">All objectives</option>{data.exercise.objectives.map(item => <option key={item.id} value={item.id}>{item.id} · {item.text}</option>)}{data.findings.some(item => !item.objective_id || !data.exercise.objectives.some(objective => objective.id === item.objective_id)) && <option value="">No objective linked</option>}</select></label><span className="fa-result-count">{visible.length} of {data.findings.length}</span></section>}
    {visible.length ? <div className="fa-finding-list">{visible.map((finding, index) => {
      const objective = data.exercise.objectives.find(item => item.id === finding.objective_id)
      const linkedActions = data.actions.filter(action => action.finding_id === finding.id)
      const assessment = data.objective_assessments.find(item => item.objective_id === finding.objective_id)
      const conflictIds = new Set(data.timeline_conflicts.map(item => item.observation_id))
      const evidenceConflicts = finding.supporting_evidence.filter(item => conflictIds.has(item.observation_id) || item.time_confidence === 'conflicting')
      const unknowns = [...new Set([...(assessment?.unknowns || []), ...(assessment?.conflicts || [])])]
      const hasNoSupport = finding.supporting_evidence.length === 0
      return <details className="fa-finding-card" key={finding.id} open={index === 0}>
        <summary className="fa-finding-summary">
          <div className="fa-finding-head"><span className={`fa-kind-icon ${finding.category}`} aria-hidden="true">{finding.category === 'strength' ? <Check size={18} /> : <AlertTriangle size={18} />}</span><div className="fa-finding-title"><p className="fa-finding-kicker">{finding.category === 'strength' ? 'OBSERVED STRENGTH' : 'AREA FOR IMPROVEMENT'} <span>·</span> {finding.code}</p><h3>{finding.title}</h3></div><WorkflowStatus status={finding.status} finding /></div>
          <div className="fa-finding-summary-meta"><span className="fa-summary-objective">{objective ? <><strong>{objective.id}</strong><span>{objective.text}</span></> : <span className="is-missing"><AlertTriangle size={14} /> No objective linked</span>}</span><span className={`fa-summary-evidence ${hasNoSupport ? 'is-missing' : ''}`}>{hasNoSupport ? <><AlertTriangle size={14} /> No source support</> : <><FileCheck2 size={14} /> {finding.supporting_evidence.length} cited record{finding.supporting_evidence.length === 1 ? '' : 's'}</>}</span><span className="fa-expand-hint">{index === 0 ? 'Review details' : 'Open review details'} <ChevronDown size={15} /></span></div>
        </summary>
        <div className="fa-finding-details">
        <FindingEvidence evidence={finding.supporting_evidence} onEvidence={onEvidence} />
        <div className="fa-analysis-grid is-single"><section className="fa-analysis-card is-interpretation"><span className="fa-analysis-label"><Sparkles size={16} /> Objective-based interpretation</span><p>{finding.interpretation}</p></section></div>
        <section className={`fa-uncertainty ${hasNoSupport || evidenceConflicts.length || unknowns.length || !objective ? 'needs-attention' : ''}`}><span className="fa-analysis-label"><AlertTriangle size={16} /> Uncertainty and missing information</span>{hasNoSupport ? <p>Source evidence is not available in this record. The reviewer must resolve this before approving.</p> : <>{evidenceConflicts.length > 0 && <p><strong>Conflicting source timing:</strong> {evidenceConflicts.map(item => `${item.source_filename}, ${item.source_locator}`).join('; ')}. Open each source record before deciding.</p>}{unknowns.length > 0 ? <ul>{unknowns.map(item => <li key={item}>{item}</li>)}</ul> : !evidenceConflicts.length && <p>{objective ? 'No additional unknowns or conflicts were recorded for the linked objective.' : 'The objective mapping is missing; evaluator review is needed to confirm how this finding should be assessed.'}</p>}</>}</section>
        <FindingWorkflow finding={finding} actions={linkedActions} />
        {(finding.review_note || finding.status !== 'proposed') && <div className={`fa-review-outcome ${finding.status === 'rejected' ? 'is-rejected' : ''}`}>{finding.status === 'rejected' ? <XCircle size={17} /> : <CheckCircle2 size={17} />}<span><strong>Reviewer decision: {finding.status === 'approved' ? 'Approved' : finding.status === 'rejected' ? 'Rejected' : finding.status}{finding.reviewer ? ` by ${finding.reviewer}` : ''}</strong>{finding.review_note && <small>Reviewer note: {finding.review_note}</small>}</span></div>}
        {finding.status === 'proposed' && <div className="fa-review-footer"><p>{hasNoSupport ? 'Resolve source support before a reviewer can approve this finding.' : canReview ? 'Review the source quotations and uncertainties before recording your decision.' : 'Awaiting a decision from an authorized reviewer.'}</p>{canReview && <div className="fa-review-actions"><button className="button reject" onClick={() => onReview(finding, 'rejected')} disabled={busy}><XCircle size={16} /> Reject finding</button><button className="button primary" onClick={() => onReview(finding, 'approved')} disabled={busy || hasNoSupport} title={hasNoSupport ? 'Source support is required before approval' : undefined}><CheckCircle2 size={16} /> Approve finding</button></div>}</div>}
        <AuditHistory events={data.audit_events.filter(event => event.object_id === finding.id)} />
        <p className="fa-confidence">Rule-based match confidence: <strong>{finding.confidence}</strong>. This is not a reviewer decision.</p>
        </div>
      </details>
    })}</div> : data.findings.length === 0 ? <div className="fa-empty"><span className="fa-empty-icon"><ShieldCheck size={25} /></span><p className="fa-eyebrow">NO FINDINGS YET</p><h3>{data.analysis_locked ? 'No finding proposals were produced' : 'Start with objectives and source evidence'}</h3><p>{data.analysis_locked ? 'The current analysis did not produce findings for this exercise. Review the evidence and objective assessments if more information is needed.' : 'Add exercise objectives and source files, then run evidence analysis. Any findings will appear here as proposals for human review.'}</p></div> : <div className="fa-empty fa-filter-empty"><Search size={23} /><h3>No findings match these filters</h3><p>Change the search, status or objective filter to see more results.</p><button type="button" className="button secondary" onClick={() => { setQuery(''); setStatus('all'); setObjectiveId('all') }}>Clear filters</button></div>}
    <div className="fa-trust-note"><ShieldCheck size={17} /><p><strong>Human decision stays with the evaluator.</strong> DrillLoop preserves source wording and drafts an evaluation. Approval or rejection is recorded only when an authorized reviewer acts.</p></div>
  </div>
}

function ActionsView({ data, busy, canEdit, canReview, identityName, isSyntheticDemo, onSave, onReview, onClose, onEvidence }: { data: Detail; busy: boolean; canEdit: boolean; canReview: boolean; identityName: string; isSyntheticDemo: boolean; onSave: (action: Action, form: HTMLFormElement) => Promise<boolean>; onReview: (action: Action, decision: 'approved' | 'rejected') => void; onClose: (action: Action) => void; onEvidence: (item: Support) => void }) {
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('all')
  const [unsavedActionIds, setUnsavedActionIds] = useState<Set<string>>(new Set())
  const visible = data.actions.filter(action => `${action.title} ${action.finding_title} ${action.owner || ''} ${action.acceptance_criteria}`.toLowerCase().includes(query.trim().toLowerCase()) && (status === 'all' || action.status === status))
  const counts = { proposed: data.actions.filter(item => item.status === 'proposed').length, approved: data.actions.filter(item => item.status === 'approved').length, rejected: data.actions.filter(item => item.status === 'rejected').length, closed: data.actions.filter(item => item.status === 'closed').length }
  return <div className="tab-page fa-page">
    <header className="fa-page-heading"><div><p className="fa-eyebrow">IMPROVEMENT PLAN</p><h2>Corrective actions</h2><p>Track the work linked to approved findings. Owners and due dates appear only when assigned; closure requires a human reviewer to record supporting evidence.</p></div><div className="fa-heading-count"><strong>{data.actions.length}</strong><span>actions</span><span className="fa-count-divider" /><strong>{counts.closed}</strong><span>closed</span></div></header>
    {isSyntheticDemo && <div className="fa-fictional"><Sparkles size={16} /><strong>Fictional synthetic demo data</strong><span>Any names, assignments and closure references are for demonstration only.</span></div>}
    <div className={`fa-access-note ${canReview ? 'is-reviewer' : canEdit ? 'is-editor' : 'is-viewer'}`}><LockKeyhole size={17} /><span>{canReview ? <>Review and closure decisions will be recorded as <strong>{identityName}</strong>.</> : canEdit ? 'Evaluator access · you can update action details; a reviewer must approve or close actions.' : 'Viewer access · action details are available in read-only mode.'}</span></div>
    <section className="fa-action-stats" aria-label="Corrective action status counts"><div><span className="fa-stat-dot proposed" /><strong>{counts.proposed}</strong><span>Proposed</span></div><div><span className="fa-stat-dot approved" /><strong>{counts.approved}</strong><span>Approved</span></div><div><span className="fa-stat-dot rejected" /><strong>{counts.rejected}</strong><span>Rejected</span></div><div><span className="fa-stat-dot closed" /><strong>{counts.closed}</strong><span>Closed</span></div></section>
    {data.actions.length > 0 && <section className="fa-toolbar fa-action-toolbar" aria-label="Corrective action filters"><label className="fa-search"><Search size={17} /><span className="sr-only">Search corrective actions</span><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search actions, findings or owners" />{query && <button type="button" aria-label="Clear action search" onClick={() => setQuery('')}><X size={15} /></button>}</label><label className="fa-filter"><span>Status</span><select value={status} onChange={event => setStatus(event.target.value)}><option value="all">All statuses</option><option value="proposed">Proposed</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="closed">Closed</option></select></label><span className="fa-result-count">{visible.length} of {data.actions.length}</span></section>}
    {visible.length ? <div className="fa-action-list">{visible.map((action, index) => {
      const linkedFinding = data.findings.find(finding => finding.id === action.finding_id)
      const linkedEvidence = linkedFinding?.supporting_evidence.filter(item => action.evidence_ids.includes(item.observation_id)) || []
      const events = data.audit_events.filter(event => event.object_id === action.id)
      const approvalEvent = events.find(event => event.action === 'action_approved')
      const closureEvent = events.find(event => event.action === 'action_closed')
      const isUnsaved = unsavedActionIds.has(action.id)
      const blockedReason = isUnsaved ? 'Save action details before approval.' : linkedFinding?.status !== 'approved' ? 'Approve the linked finding first.' : !action.owner ? 'Assign an owner before approval.' : !action.due_date ? 'Set a due date before approval.' : ''
      const displayOwner = action.owner || 'Not assigned'
      const displayDue = action.due_date || 'Not set'
      return <details className={`fa-action-card ${!action.owner ? 'has-gap' : ''}`} key={action.id} open={index === 0}>
        <summary className="fa-action-summary">
          <div className="fa-action-card-top"><div className="fa-priority"><span className={`fa-priority-mark ${action.priority}`} aria-hidden="true" /><span>Priority</span><strong>{action.priority}</strong></div><WorkflowStatus status={action.status} /></div>
          <h3>{action.title}</h3>
          <div className="fa-action-summary-linked"><span className="fa-label">ADDRESSES FINDING</span><strong>{action.finding_title || 'Finding reference unavailable'}</strong><span className={`fa-mini-state fa-mini-state--${linkedFinding?.status || 'unknown'}`}>{linkedFinding?.status ? linkedFinding.status.charAt(0).toUpperCase() + linkedFinding.status.slice(1) : 'Not linked'}</span></div>
          <div className="fa-action-summary-meta"><span><UserRound size={15} /><small>Owner</small><strong>{displayOwner}</strong></span><span><CalendarDays size={15} /><small>Due date</small><strong>{displayDue}</strong></span><span className="fa-expand-hint">{index === 0 ? 'View action details' : 'Open action details'} <ChevronDown size={15} /></span></div>
        </summary>
        <div className="fa-action-details">
        <section className="fa-acceptance"><span className="fa-section-label"><CheckCircle2 size={16} /> ACCEPTANCE CRITERIA</span><p>{action.acceptance_criteria || 'No acceptance criteria recorded.'}</p></section>
        {linkedEvidence.length > 0 && <section className="fa-action-evidence"><div className="fa-section-label"><FileCheck2 size={16} /><h4>Finding evidence</h4><span>{linkedEvidence.length} record{linkedEvidence.length === 1 ? '' : 's'}</span></div><div>{linkedEvidence.map(item => <button className="fa-evidence-link" key={item.observation_id} onClick={() => onEvidence(item)}><span className="fa-evidence-file"><FileText size={16} /></span><span className="fa-evidence-copy"><strong>{item.source_filename}</strong><small>{item.source_locator}</small><q>{item.text}</q></span><ChevronRight size={16} className="fa-evidence-chevron" /></button>)}</div></section>}
        {action.evidence_ids.length > 0 && linkedEvidence.length === 0 && <div className="fa-evidence-missing"><AlertTriangle size={17} /><p><strong>Linked source records are unavailable.</strong> {action.evidence_ids.length} reference{action.evidence_ids.length === 1 ? '' : 's'} could not be opened from this exercise.</p></div>}
        {canEdit && action.status !== 'closed' && <details className="fa-action-edit"><summary>Edit action details</summary><form className="fa-edit-form" onChange={event => {
          const form = event.currentTarget
          const values = new FormData(form)
          const changed = String(values.get('title')) !== action.title || (String(values.get('owner') || '') || null) !== action.owner || String(values.get('priority')) !== action.priority || (String(values.get('due_date') || '') || null) !== action.due_date || String(values.get('acceptance_criteria')) !== action.acceptance_criteria
          setUnsavedActionIds(current => { const next = new Set(current); if (changed) next.add(action.id); else next.delete(action.id); return next })
        }} onSubmit={async event => { event.preventDefault(); if (event.currentTarget.reportValidity()) { const saved = await onSave(action, event.currentTarget); if (saved) setUnsavedActionIds(current => { const next = new Set(current); next.delete(action.id); return next }) } }}>
          <label className="fa-edit-title"><span>Action title</span><input name="title" defaultValue={action.title} required minLength={4} maxLength={240} aria-describedby={`action-title-help-${action.id}`} /><small id={`action-title-help-${action.id}`}>Describe the improvement work in plain language.</small></label>
          <label><span>Owner</span><input name="owner" defaultValue={action.owner || ''} maxLength={160} placeholder="Name a person or accountable team" aria-describedby={`action-owner-help-${action.id}`} /><small id={`action-owner-help-${action.id}`}>An owner is required before a reviewer can approve this action.</small></label>
          <label><span>Priority</span><select name="priority" defaultValue={action.priority}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option></select></label>
          <label><span>Due date</span><input name="due_date" type="date" defaultValue={action.due_date || ''} aria-describedby={`action-date-help-${action.id}`} /><small id={`action-date-help-${action.id}`}>Set a date before approval. Leave blank until assigned.</small></label>
          <label className="fa-edit-criteria"><span>Acceptance criteria</span><textarea name="acceptance_criteria" defaultValue={action.acceptance_criteria} required minLength={8} maxLength={4000} rows={3} aria-describedby={`action-criteria-help-${action.id}`} /><small id={`action-criteria-help-${action.id}`}>State what evidence will show the work is complete (8–4,000 characters).</small></label>
          {!action.owner && <p className="fa-field-warning"><AlertTriangle size={16} /> An owner must be assigned and saved before approval.</p>}
          <div className="fa-edit-actions"><button type="submit" className="button secondary" disabled={busy}><Check size={15} /> Save action</button>{isUnsaved && <span className="fa-unsaved-hint" role="status">Unsaved changes · save before approval.</span>}</div>
        </form></details>}
        {action.status === 'approved' && <div className="fa-approved-note"><CheckCircle2 size={17} /><span><strong>Approved{approvalEvent ? ` by ${approvalEvent.actor}` : ''}</strong>{approvalEvent && <small>{eventTime(approvalEvent.created_at)}</small>}{isUnsaved && <small>Save the open action details before recording closure.</small>}</span>{canReview && <button className="button primary" onClick={() => onClose(action)} disabled={busy || isUnsaved}><FileCheck2 size={16} /> Record closure evidence</button>}</div>}
        {action.status === 'closed' && <div className="fa-closure-record"><CheckCircle2 size={18} /><div><strong>Closure evidence recorded</strong><span>{closureEvent ? `Closed by ${closureEvent.actor} · ${eventTime(closureEvent.created_at)}` : 'Reviewer identity is not available in the current history.'}</span><blockquote>{action.closure_evidence}</blockquote><small>A reviewer recorded this evidence. DrillLoop has not independently verified real-world completion.</small></div></div>}
        {action.status !== 'closed' && action.status !== 'approved' && <div className="fa-action-next"><p>{action.status === 'rejected' ? 'This action was rejected. A reviewer may record a new decision while it remains open.' : blockedReason || (canReview ? 'Action is ready for reviewer decision.' : 'Awaiting a reviewer decision.')}{action.status === 'proposed' && blockedReason && <span> {canEdit && (!action.owner || !action.due_date) ? 'Open “Edit action details” to update the assigned fields.' : ''}</span>}</p>{canReview && <div className="fa-review-actions"><button className="button reject" onClick={() => onReview(action, 'rejected')} disabled={busy}><XCircle size={16} /> Reject action</button><button className="button primary" onClick={() => onReview(action, 'approved')} disabled={busy || Boolean(blockedReason)} title={blockedReason || undefined}><CheckCircle2 size={16} /> {action.status === 'rejected' ? 'Approve action again' : 'Approve action'}</button></div>}</div>}
        {action.status === 'approved' && <div className="fa-closure-help"><FileCheck2 size={16} /><span>Closure is available only to an authorized reviewer after supporting evidence is recorded.</span></div>}
        <AuditHistory events={events} />
        <div className="fa-action-workflow"><span className="fa-label">WORKFLOW</span><span>{linkedFinding?.status || 'Finding unavailable'}</span><ChevronRight size={14} /><span>{action.status === 'closed' ? 'Closure evidence recorded' : action.status}</span></div>
        </div>
      </details>
    })}</div> : data.actions.length === 0 ? <div className="fa-empty"><span className="fa-empty-icon"><ListChecks size={25} /></span><p className="fa-eyebrow">NO CORRECTIVE ACTIONS</p><h3>No actions are linked to this exercise yet</h3><p>Actions are prepared from improvement findings. Review the findings and their linked objectives to understand what is available for follow-up.</p></div> : <div className="fa-empty fa-filter-empty"><Search size={23} /><h3>No actions match these filters</h3><p>Change the search or status filter to see more results.</p><button type="button" className="button secondary" onClick={() => { setQuery(''); setStatus('all') }}>Clear filters</button></div>}
    <div className="fa-trust-note"><LockKeyhole size={17} /><p>Named-user access controls review decisions. Action approval requires an approved linked finding, owner and due date. Closure records supporting information and reviewer attribution.</p></div>
  </div>
}

function ReviewDecisionModal({ target, data, busy, errorMessage, onClose, onSubmit }: { target: ReviewTarget; data: Detail; busy: boolean; errorMessage: string; onClose: () => void; onSubmit: (note: string) => Promise<boolean> }) {
  const dialogRef = useAccessibleDialog<HTMLElement>(onClose)
  const [note, setNote] = useState('')
  const isFinding = target.kind === 'finding'
  const title = target.record.title
  const linkedFinding = isFinding ? target.record : data.findings.find(finding => finding.id === target.record.finding_id)
  const evidenceCount = isFinding ? target.record.supporting_evidence.length : target.record.evidence_ids.length
  const heading = `${target.decision === 'approved' ? 'Approve' : 'Reject'} this ${isFinding ? 'finding' : 'action'}?`
  const actionLabel = target.decision === 'approved' ? 'Approve' : 'Reject'
  return <div className="modal-shade fa-modal-shade" onMouseDown={event => { if (event.target === event.currentTarget && !busy) onClose() }}><section ref={dialogRef} className="fa-decision-modal" role="dialog" aria-modal="true" aria-labelledby="review-decision-heading" aria-describedby="review-decision-explanation" tabIndex={-1}><form onSubmit={event => { event.preventDefault(); void onSubmit(note.trim()) }}>
    <div className="fa-modal-heading"><span className={`fa-modal-icon ${target.decision}`} aria-hidden="true">{target.decision === 'approved' ? <CheckCircle2 size={21} /> : <XCircle size={21} />}</span><div><p className="fa-eyebrow">HUMAN REVIEW · {target.kind.toUpperCase()}</p><h2 id="review-decision-heading">{heading}</h2></div><button type="button" className="icon-button" onClick={onClose} aria-label="Close review decision" disabled={busy}><X size={18} /></button></div>
    <div className="fa-modal-content"><div className="fa-review-subject"><span>{isFinding ? 'FINDING' : 'CORRECTIVE ACTION'}</span><strong>{title}</strong>{!isFinding && <small>Linked finding: {linkedFinding?.title || 'Finding information unavailable'}</small>}<small>{evidenceCount} linked source reference{evidenceCount === 1 ? '' : 's'}</small></div>
      <p id="review-decision-explanation" className="fa-decision-explanation">{isFinding ? target.decision === 'approved' ? 'Approval records your decision that this source-linked finding is accepted for this exercise. It also allows its related corrective action to proceed to review. DrillLoop does not independently verify the event.' : 'Rejection records that this proposed finding is not accepted for this exercise. Finding decisions cannot be changed after they are recorded.' : target.decision === 'approved' ? 'Approval records your decision to accept this corrective action. The linked finding must be approved, and an owner and due date must be assigned.' : 'Rejection records that this proposed corrective action is not accepted. An open action can be reviewed again before it is closed.'}</p>
      <label className="fa-review-note"><span>Reviewer note <small>Optional</small></span><textarea value={note} onChange={event => setNote(event.target.value)} maxLength={3000} rows={3} placeholder="Add context for the audit history, if useful." aria-describedby="review-note-help" /><small id="review-note-help">Up to 3,000 characters. This note will be stored with your decision.</small></label>
      {errorMessage && <div className="fa-modal-error" role="alert"><AlertTriangle size={16} />{errorMessage}</div>}
    </div>
    <div className="fa-modal-footer"><span>Recorded as {target.decision} by the signed-in reviewer.</span><button type="button" className="button secondary" onClick={onClose} disabled={busy}>Cancel</button><button type="submit" className={`button ${target.decision === 'approved' ? 'primary' : 'danger'}`} disabled={busy}>{busy && <LoaderCircle size={15} className="spin" />}{busy ? 'Recording decision…' : <>{target.decision === 'approved' ? <CheckCircle2 size={16} /> : <XCircle size={16} />}{actionLabel} {isFinding ? 'finding' : 'action'}</>}</button></div>
  </form></section></div>
}

function ClosureEvidenceModal({ action, busy, errorMessage, onClose, onSubmit }: { action: Action; busy: boolean; errorMessage: string; onClose: () => void; onSubmit: (evidence: string) => Promise<boolean> }) {
  const dialogRef = useAccessibleDialog<HTMLElement>(onClose)
  const [evidence, setEvidence] = useState('')
  const [attempted, setAttempted] = useState(false)
  const trimmedLength = evidence.trim().length
  const invalid = attempted && trimmedLength < 12
  return <div className="modal-shade fa-modal-shade" onMouseDown={event => { if (event.target === event.currentTarget && !busy) onClose() }}><section ref={dialogRef} className="fa-decision-modal" role="dialog" aria-modal="true" aria-labelledby="closure-heading" aria-describedby="closure-explanation" tabIndex={-1}><form noValidate onSubmit={event => { event.preventDefault(); setAttempted(true); if (trimmedLength >= 12) void onSubmit(evidence.trim()) }}>
    <div className="fa-modal-heading"><span className="fa-modal-icon approved" aria-hidden="true"><FileCheck2 size={21} /></span><div><p className="fa-eyebrow">ACTION CLOSURE</p><h2 id="closure-heading">Record closure evidence</h2></div><button type="button" className="icon-button" onClick={onClose} aria-label="Close closure evidence form" disabled={busy}><X size={18} /></button></div>
    <div className="fa-modal-content"><div className="fa-review-subject"><span>APPROVED ACTION</span><strong>{action.title}</strong><small>Owner: {action.owner || 'Not assigned'} · Due: {action.due_date || 'Not set'}</small><small>Acceptance criteria: {action.acceptance_criteria}</small></div>
      <p id="closure-explanation" className="fa-decision-explanation">Record the supporting reference a reviewer considered, such as a dated retest record or approved document. A human reviewer is responsible for deciding whether it is sufficient; DrillLoop does not verify work in the real world.</p>
      <label className="fa-review-note"><span>Closure evidence <small>Required</small></span><textarea value={evidence} onChange={event => setEvidence(event.target.value)} required minLength={12} maxLength={4000} rows={4} placeholder="Describe the evidence or enter its source and reference." aria-invalid={invalid} aria-describedby="closure-evidence-help" /><small id="closure-evidence-help">Enter at least 12 characters and up to 4,000. Do not include information that is not part of the supporting record.</small></label>
      {invalid && <div className="fa-modal-error" role="alert"><AlertTriangle size={16} />Add at least 12 characters of closure evidence.</div>}
      {errorMessage && <div className="fa-modal-error" role="alert"><AlertTriangle size={16} />{errorMessage}</div>}
    </div>
    <div className="fa-modal-footer"><span>Closure is recorded with the signed-in reviewer’s identity.</span><button type="button" className="button secondary" onClick={onClose} disabled={busy}>Cancel</button><button type="submit" className="button primary" disabled={busy}>{busy && <LoaderCircle size={15} className="spin" />}{busy ? 'Recording closure…' : <><FileCheck2 size={16} /> Record closure evidence</>}</button></div>
  </form></section></div>
}

function EvidenceModal({ evidence, onClose }: { evidence: Support; onClose: () => void }) {
  const dialogRef = useAccessibleDialog<HTMLElement>(onClose)
  return <div className="modal-shade" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}><section ref={dialogRef} className="evidence-modal" role="dialog" aria-modal="true" aria-labelledby="evidence-heading" tabIndex={-1}>
    <div className="modal-head"><div className="modal-file-icon"><FileText size={19} /></div><div><span>ORIGINAL SOURCE EVIDENCE</span><h2 id="evidence-heading">{evidence.source_filename}</h2></div><button className="icon-button" onClick={onClose} aria-label="Close source view"><X size={18} /></button></div>
    <div className="source-metadata"><span><strong>Exact location</strong>{evidence.source_locator}</span><span><strong>Event time</strong>{evidence.event_time_normalized ? shortTime(evidence.event_time_normalized) : 'Unresolved'}</span><span><strong>Time quality</strong>{timeLabel(evidence.time_confidence)}</span></div><div className="source-quote"><div className="quote-mark">“</div><p>{evidence.text}</p><span>Exact extracted text · no paraphrase</span></div>
    <div className="modal-footer"><span>Evidence record · {evidence.observation_id.slice(0, 12)}</span><a className="button secondary" href={`/api/sources/${evidence.source_id}/download`}><ArrowDownToLine size={14} /> Download original file</a><button className="button secondary" onClick={onClose}>Close source view</button></div>
  </section></div>
}

type CreateForm = { id: string; title: string; scenario: string; exercise_date: string; duration_minutes: string; evaluator_roles: string; participants: string; milestones: string }
function CreateModal({ form, setForm, onClose, onSubmit, busy, errorMessage }: { form: CreateForm; setForm: React.Dispatch<React.SetStateAction<CreateForm>>; onClose: () => void; onSubmit: () => void; busy: boolean; errorMessage: string }) {
  const dialogRef = useAccessibleDialog<HTMLElement>(onClose)
  const [attempted, setAttempted] = useState(false)
  const update = (field: keyof typeof form, value: string) => setForm(current => ({ ...current, [field]: value }))
  const idValid = form.id.trim().length >= 3 && form.id.trim().length <= 80 && /^[\p{L}\p{N}_-]+$/u.test(form.id.trim())
  const titleValid = form.title.trim().length >= 3 && form.title.trim().length <= 200
  const scenarioValid = form.scenario.trim().length >= 10
  const duration = Number(form.duration_minutes)
  const durationValid = Number.isInteger(duration) && duration > 0 && duration <= 1440
  const validationSummary = [!idValid && 'Check the exercise ID.', !form.exercise_date && 'Choose the exercise date.', !titleValid && 'Enter an exercise name between 3 and 200 characters.', !scenarioValid && 'Describe the scenario in at least 10 characters.', !durationValid && 'Enter a whole number from 1 to 1,440 minutes.'].filter(Boolean).join(' ')
  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    setAttempted(true)
    if (idValid && titleValid && scenarioValid && form.exercise_date && durationValid) onSubmit()
  }
  return <div className="modal-shade"><section ref={dialogRef} className="create-modal create-exercise-modal" role="dialog" aria-modal="true" aria-labelledby="create-heading" tabIndex={-1}><form noValidate onSubmit={handleSubmit}>
    <div className="modal-head"><div className="modal-file-icon"><Plus size={19} /></div><div><span>EXERCISE SETUP · STEP 1 OF 2</span><h2 id="create-heading">Create an exercise</h2></div><button type="button" className="icon-button" onClick={onClose} aria-label="Close exercise form"><X size={18} /></button></div>
    <div className="create-form">
      {errorMessage && <div className="form-error-summary" role="alert">{errorMessage}</div>}
      {attempted && validationSummary && <div className="form-error-summary" role="alert">{validationSummary}</div>}
      <p className="create-intro">Start with the exercise context. You’ll define objectives next, before adding evidence.</p>
      <div className="form-two">
        <label><span>EXERCISE ID <b>Required</b></span><input value={form.id} maxLength={80} onChange={event => update('id', event.target.value)} placeholder="EXERCISE-2026-02" aria-invalid={attempted && !idValid} aria-describedby="exercise-id-help exercise-id-error" /><small id="exercise-id-help">Letters, numbers, hyphens, or underscores. Must be unique.</small>{attempted && !idValid && <small id="exercise-id-error" className="field-error">Enter at least 3 valid characters.</small>}</label>
        <label><span>EXERCISE DATE <b>Required</b></span><input type="date" value={form.exercise_date} onChange={event => update('exercise_date', event.target.value)} aria-invalid={attempted && !form.exercise_date} />{attempted && !form.exercise_date && <small className="field-error">Choose the exercise date.</small>}</label>
      </div>
      <label><span>EXERCISE NAME <b>Required</b></span><input value={form.title} maxLength={200} onChange={event => update('title', event.target.value)} placeholder="Night shift communications exercise" aria-invalid={attempted && !titleValid} aria-describedby="exercise-name-help exercise-name-error" /><small id="exercise-name-help">A short, recognizable name for the exercise list.</small>{attempted && !titleValid && <small id="exercise-name-error" className="field-error">Enter a name between 3 and 200 characters.</small>}</label>
      <label><span>SCENARIO AND SCOPE <b>Required</b></span><textarea rows={3} value={form.scenario} onChange={event => update('scenario', event.target.value)} placeholder="Describe the simulated situation and what the exercise covers." aria-invalid={attempted && !scenarioValid} aria-describedby="scenario-help scenario-error" /><small id="scenario-help">Explain the situation participants will respond to. This helps evaluators understand the context.</small>{attempted && !scenarioValid && <small id="scenario-error" className="field-error">Add at least 10 characters describing the scenario.</small>}</label>
      <div className="form-two duration-row"><label><span>EXERCISE DURATION <b>Required</b></span><div className="duration-input"><input type="number" min="1" max="1440" step="1" value={form.duration_minutes} onChange={event => update('duration_minutes', event.target.value)} aria-label="Exercise duration in minutes" aria-invalid={attempted && !durationValid} /><span>minutes</span></div>{attempted && !durationValid && <small className="field-error">Enter a whole number from 1 to 1,440 minutes.</small>}</label><p className="form-hint"><HelpCircle size={15} /> Used to describe the planned exercise length. Objective time targets are configured separately.</p></div>
      <details className="optional-exercise-details"><summary>Optional exercise details</summary><div className="optional-exercise-fields"><label><span>EVALUATOR ROLES</span><input value={form.evaluator_roles} onChange={event => update('evaluator_roles', event.target.value)} placeholder="Facilities, Clinical" /><small>Comma-separated roles or teams responsible for evaluation.</small></label><label><span>PARTICIPANTS / TEAMS</span><input value={form.participants} onChange={event => update('participants', event.target.value)} placeholder="Incident Command, ICU" /><small>Comma-separated participant groups.</small></label><label><span>EXPECTED MILESTONES</span><textarea rows={2} value={form.milestones} onChange={event => update('milestones', event.target.value)} placeholder="Generator stable and essential circuits checked" /><small>One expected milestone per line.</small></label></div></details>
    </div>
    <div className="modal-footer"><span>Next: define the objectives evaluators will use to review evidence.</span><div><button type="button" className="button secondary" onClick={onClose}>Cancel</button><button type="submit" className="button primary" disabled={busy}><Plus size={14} /> Create exercise</button></div></div>
  </form></section></div>
}
