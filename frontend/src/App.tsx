import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, AlertTriangle, ArrowDownToLine, AudioLines, Check, CheckCircle2,
  ChevronRight, Circle, Clock3, FileAudio, FileCheck2, FileText, Filter, FolderOpen,
  Gauge, HelpCircle, ListChecks, LoaderCircle, LockKeyhole,
  MessageSquareText, Plus, Search, ShieldCheck, Sparkles, Upload,
  X, XCircle, Zap,
} from 'lucide-react'

type Tab = 'overview' | 'evidence' | 'timeline' | 'findings' | 'actions'
type Source = { id: string; filename: string; kind: string; mime_type: string; sha256: string; provenance: Record<string, unknown>; scan_status: 'clean' | 'not_scanned'; observation_count: number }
type Observation = { id: string; source_id: string; source_filename: string; text: string; event_time_raw: string | null; event_time_normalized: string | null; time_confidence: string; source_locator: string; observation_type: string; extraction_method: string; recognition_confidence: number | null }
type Support = { source_id: string; source_filename: string; observation_id: string; source_locator: string; text: string; event_time_normalized: string | null; time_confidence: string }
type Finding = { id: string; code: string; title: string; category: 'strength' | 'improvement'; objective_id: string | null; observation: string; interpretation: string; evidence_ids: string[]; evidence_labels: string[]; confidence: string; status: string; review_note: string; reviewer: string | null; supporting_evidence: Support[] }
type Action = { id: string; finding_id: string; finding_title: string; title: string; evidence_ids: string[]; owner: string | null; priority: string; due_date: string | null; acceptance_criteria: string; status: string; reviewer_decision: string; reviewer: string | null; closure_evidence: string }
type Objective = { id: string; text: string; evaluation_rule?: Record<string, unknown> }
type ObjectiveAssessment = { objective_id: string | null; objective_text: string; state: string; rule_type: string | null; threshold_seconds: number | null; elapsed_seconds: number[]; evidence: { observation_id: string; source_id: string; source_locator: string; source_wording: string; timestamp: string | null; time_confidence: string }[]; unknowns: string[]; conflicts: string[] }
type Exercise = { id: string; title: string; scenario: string; exercise_date: string; duration_minutes: number; objectives: Objective[]; criteria: string[]; evaluator_roles: string[]; participants: string[]; expected_milestones: { id: string; expected: string; objective_id: string }[] }
type Detail = { exercise: Exercise; objective_assessments: ObjectiveAssessment[]; analysis_locked: boolean; sources: Source[]; timeline: Observation[]; timeline_conflicts: { observation_id: string; source_id: string; source_filename: string; source_locator: string; description: string }[]; findings: Finding[]; actions: Action[]; audit_events: { actor: string; action: string; object_id: string; created_at: string }[] }
type Identity = { id: string; username: string; name: string; role: 'admin' | 'evaluator' | 'reviewer' | 'viewer'; organization_id: string }
type AccessGrant = { user_id: string; username: string; name: string; role: Identity['role'] }
type Capabilities = { asr: { available: boolean; package_version: string | null; model_path_configured: boolean; note: string }; analysis: { mode: string; cloud_api_required: boolean }; review: { required_identity: boolean; review_roles: string[] }; synthetic_demo_seed_enabled?: boolean }

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

function parseObjectives(value: string): Objective[] {
  return value.split('\n').map(line => line.trim()).filter(Boolean).map((line, index) => {
    const [definition, ...clauses] = line.split('|').map(part => part.trim())
    const colon = definition.indexOf(':')
    const id = colon > 0 ? definition.slice(0, colon).trim() : `OBJ-${String(index + 1).padStart(2, '0')}`
    const text = colon > 0 ? definition.slice(colon + 1).trim() : definition
    const values = Object.fromEntries(clauses.map(clause => {
      const split = clause.indexOf('=')
      return split > 0 ? [clause.slice(0, split).trim().toLowerCase(), clause.slice(split + 1).trim()] : ['', '']
    }).filter(([key]) => key))
    const terms = (key: string) => String(values[key] || '').split(';').map(item => item.trim()).filter(Boolean)
    const within = String(values.within || '').match(/^(\d+(?:\.\d+)?)\s*(s|sec|seconds?|m|min|minutes?|h|hours?)$/i)
    let evaluation_rule: Record<string, unknown> | undefined
    if (values.missing || values.present) {
      evaluation_rule = { type: 'required_field', missing_terms: terms('missing'), present_terms: terms('present') }
    } else if (values.match) {
      evaluation_rule = { type: 'event_presence', terms: terms('match') }
    } else if (values.claim) {
      evaluation_rule = { type: 'reported_duration', start_terms: terms('start'), completion_terms: terms('complete'), claim_terms: terms('claim') }
    } else if (values.start || values.complete || within) {
      const unit = within?.[2].toLowerCase() || 's'
      const multiplier = unit.startsWith('h') ? 3600 : unit.startsWith('m') ? 60 : 1
      evaluation_rule = {
        type: 'elapsed_time',
        ...(within ? { threshold_seconds: Math.round(Number(within[1]) * multiplier) } : {}),
        start_terms: terms('start'), completion_terms: terms('complete'),
        completion_claim_terms: terms('completion_claim'),
      }
    }
    return { id, text, ...(evaluation_rule ? { evaluation_rule } : {}) }
  })
}

function ObjectiveEditor({ value, onChange, onClose, onSubmit, busy }: { value: string; onChange: (value: string) => void; onClose: () => void; onSubmit: () => void; busy: boolean }) {
  const dialogRef = useAccessibleDialog<HTMLElement>(onClose)
  return <div className="modal-shade"><section ref={dialogRef} className="create-modal objective-editor" role="dialog" aria-modal="true" aria-labelledby="objectives-heading" tabIndex={-1}>
    <div className="modal-head"><div className="modal-file-icon"><Check size={19} /></div><div><span>EXERCISE SETUP</span><h2 id="objectives-heading">Edit objectives</h2></div><button className="icon-button" onClick={onClose} aria-label="Close objective editor"><X size={18} /></button></div>
    <div className="create-form"><label><span>OBJECTIVES · one per line; ID: wording | rule=value</span><textarea rows={10} value={value} onChange={event => onChange(event.target.value)} /></label><div className="objective-rule-help"><HelpCircle size={14} /><span>For elapsed time, define <code>within=5m</code>, <code>start=phrase</code>, and <code>complete=phrase</code>. Editing is locked after analysis begins to protect existing findings and decisions.</span></div></div>
    <div className="modal-footer"><span>Unclear or missing rules remain Needs review.</span><div><button className="button secondary" onClick={onClose}>Cancel</button><button className="button primary" onClick={onSubmit} disabled={busy}><Check size={14} /> Save objectives</button></div></div>
  </section></div>
}

function formatObjectives(objectives: Objective[]): string {
  return objectives.map(objective => {
    const rule = objective.evaluation_rule
    if (!rule || typeof rule.type !== 'string') return `${objective.id}: ${objective.text}`
    const clauses: string[] = []
    const list = (key: string) => Array.isArray(rule[key]) ? (rule[key] as unknown[]).filter((item): item is string => typeof item === 'string').join('; ') : ''
    if (rule.type === 'elapsed_time') {
      if (typeof rule.threshold_seconds === 'number') clauses.push(`within=${rule.threshold_seconds}s`)
      if (list('start_terms')) clauses.push(`start=${list('start_terms')}`)
      if (list('completion_terms')) clauses.push(`complete=${list('completion_terms')}`)
      if (list('completion_claim_terms')) clauses.push(`completion_claim=${list('completion_claim_terms')}`)
    } else if (rule.type === 'reported_duration') {
      if (list('start_terms')) clauses.push(`start=${list('start_terms')}`)
      if (list('completion_terms')) clauses.push(`complete=${list('completion_terms')}`)
      if (list('claim_terms')) clauses.push(`claim=${list('claim_terms')}`)
    } else if (rule.type === 'event_presence' && list('terms')) clauses.push(`match=${list('terms')}`)
    else if (rule.type === 'required_field') {
      if (list('missing_terms')) clauses.push(`missing=${list('missing_terms')}`)
      if (list('present_terms')) clauses.push(`present=${list('present_terms')}`)
    }
    return `${objective.id}: ${objective.text}${clauses.map(clause => ` | ${clause}`).join('')}`
  }).join('\n')
}

const api = async <T,>(path: string, options: RequestInit = {}): Promise<T> => {
  const url = path.startsWith('/api') ? path : `/api${path}`
  const headers = new Headers(options.headers)
  if (options.method && !['GET', 'HEAD', 'OPTIONS'].includes(options.method.toUpperCase()) && csrfTokenValue && !url.endsWith('/auth/login')) headers.set('X-CSRF-Token', csrfTokenValue)
  const response = await fetch(url, { ...options, headers, credentials: 'same-origin' })
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const data = await response.json()
      message = data.detail?.message || data.detail?.code || data.detail || message
    } catch { /* Keep HTTP status message. */ }
    if (response.status === 401 && !url.endsWith('/auth/login') && !url.endsWith('/auth/session')) window.dispatchEvent(new Event('drillloop-auth-expired'))
    throw Object.assign(new Error(message), { status: response.status })
  }
  if (response.headers.get('content-type')?.includes('application/pdf')) return await response.blob() as T
  return await response.json() as T
}

const initials = (name: string) => name.split(' ').map(part => part[0]).join('').slice(0, 2).toUpperCase()
const shortTime = (value: string | null) => value ? value.slice(value.indexOf('T') + 1, value.indexOf('T') + 9) : 'Time unresolved'
const timeLabel = (value: string) => ({ certain: 'Time recorded', medium: 'Time recognized', uncertain: 'Time uncertain', unknown: 'Time missing' }[value] || value)

export default function App() {
  const [exercises, setExercises] = useState<Exercise[]>([])
  const [selectedId, setSelectedId] = useState(() => localStorage.getItem('drillloop-selected-exercise') || '')
  const [data, setData] = useState<Detail | null>(null)
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null)
  const [identity, setIdentity] = useState<Identity | null>(null)
  const [authenticated, setAuthenticated] = useState(false)
  const [loginForm, setLoginForm] = useState({ username: '', password: '' })
  const [tab, setTab] = useState<Tab>('overview')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [sourceFilter, setSourceFilter] = useState('')
  const [evidenceOpen, setEvidenceOpen] = useState<Support | null>(null)
  const [accessOpen, setAccessOpen] = useState(false)
  const [accessGrants, setAccessGrants] = useState<AccessGrant[]>([])
  const [configuredUsers, setConfiguredUsers] = useState<AccessGrant[]>([])
  const [createOpen, setCreateOpen] = useState(false)
  const [objectivesOpen, setObjectivesOpen] = useState(false)
  const [objectiveDraft, setObjectiveDraft] = useState('')
  const [newForm, setNewForm] = useState({ id: '', title: '', scenario: '', exercise_date: new Date().toISOString().slice(0, 10), duration_minutes: '120', objectives: '', evaluator_roles: '', participants: '', milestones: '' })

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
    const list = await api<(Exercise & { finding_count: number })[]>('/exercises')
    setExercises(list)
    if (!list.some(item => item.id === selectedId) && list[0]) setSelectedId(list[0].id)
    if (list.length === 0) setLoading(false)
  }, [selectedId])

  const refreshDetail = useCallback(async (id = selectedId) => {
    const detail = await api<Detail>(`/exercises/${encodeURIComponent(id)}`)
    setData(detail)
  }, [selectedId])

  const loadWorkspace = async () => {
    const [list, caps] = await Promise.all([api<(Exercise & { finding_count: number })[]>('/exercises'), api<Capabilities>('/capabilities')])
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

  const withBusy = async (task: () => Promise<void>) => {
    setBusy(true); setError(''); setNotice('')
    try { await task() } catch (err) { setError(err instanceof Error ? err.message : 'Something went wrong.') }
    finally { setBusy(false) }
  }

  const selectExercise = (id: string) => {
    if (!id || id === selectedId) return
    void withBusy(async () => {
      setData(null)
      setSelectedId(id)
      localStorage.setItem('drillloop-selected-exercise', id)
      await refreshDetail(id)
      setTab('overview')
    })
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

  const uploadFiles = (files: FileList | null) => {
    if (!files?.length) return
    withBusy(async () => {
      const form = new FormData()
      Array.from(files).forEach(file => form.append('files', file))
      const result = await api<{ message: string }>(`/exercises/${selectedId}/evidence`, { method: 'POST', body: form })
      await refreshDetail(); setNotice(result.message)
    })
  }

  const transcribeFile = (file?: File) => {
    if (!file) return
    withBusy(async () => {
      const form = new FormData(); form.append('file', file)
      await api(`/exercises/${selectedId}/audio`, { method: 'POST', body: form })
      await refreshDetail(); setNotice('Audio transcript imported. Verify uncertain text against the recording.')
    })
  }

  const reviewFinding = (finding: Finding, decision: 'approved' | 'rejected') => withBusy(async () => {
    await api(`/findings/${finding.id}/review`, { method: 'POST', headers: authHeaders, body: JSON.stringify({ decision, note: '' }) })
    await refreshDetail(); setNotice(`Finding ${decision}. The reviewer decision is recorded.`)
  })

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

  const reviewAction = (action: Action, decision: 'approved' | 'rejected') => withBusy(async () => {
    await api(`/actions/${action.id}/review`, { method: 'POST', headers: authHeaders, body: JSON.stringify({ decision, note: '' }) })
    await refreshDetail(); setNotice(`Corrective action ${decision}.`)
  })

  const closeAction = (action: Action) => {
    const closure_evidence = window.prompt('Add closure evidence (for example, an exercise ID, test record, or approved document reference).')
    if (!closure_evidence) return
    withBusy(async () => {
      await api(`/actions/${action.id}/close`, { method: 'POST', headers: authHeaders, body: JSON.stringify({ closure_evidence }) })
      await refreshDetail(); setNotice('Closure evidence recorded and action closed.')
    })
  }

  const exportReport = async () => withBusy(async () => {
    const blob = await api<Blob>(`/exercises/${selectedId}/report.pdf`)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = `${selectedId}-AAR-IP.pdf`; anchor.click()
    URL.revokeObjectURL(url); setNotice('Draft after-action report and improvement plan exported as PDF.')
  })

  const createExercise = () => withBusy(async () => {
    const objectives = parseObjectives(newForm.objectives)
    const expected_milestones = newForm.milestones.split('\n').map(line => line.trim()).filter(Boolean).map((expected, index) => ({ id: `M-${String(index + 1).padStart(2, '0')}`, expected, objective_id: objectives[0]?.id || '' }))
    const created = await api<Exercise>('/exercises', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
      id: newForm.id, title: newForm.title, scenario: newForm.scenario, exercise_date: newForm.exercise_date,
      duration_minutes: Number(newForm.duration_minutes), objectives, expected_milestones,
      criteria: [], evaluator_roles: newForm.evaluator_roles.split(',').map(x => x.trim()).filter(Boolean),
      participants: newForm.participants.split(',').map(x => x.trim()).filter(Boolean),
    }) })
    setSelectedId(created.id); localStorage.setItem('drillloop-selected-exercise', created.id); setCreateOpen(false); await refreshExercises(); await refreshDetail(created.id)
    setTab('overview'); setNotice('Exercise created. Upload evidence to start its review.')
  })

  const saveObjectives = () => withBusy(async () => {
    const objectives = parseObjectives(objectiveDraft)
    await api(`/exercises/${encodeURIComponent(selectedId)}/objectives`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ objectives, criteria: data?.exercise.criteria || [] }),
    })
    await refreshDetail()
    setObjectivesOpen(false)
    setNotice('Objectives saved. Analysis has not run for this exercise yet.')
  })

  const selectedExercise = data?.exercise
  const filteredSources = data?.sources.filter(source => !sourceFilter || source.filename.toLowerCase().includes(sourceFilter.toLowerCase())) || []

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

  if (!identity) return <div className="auth-screen"><form className="auth-card" onSubmit={signIn}><div className="brand-mark"><Activity size={21} /></div><p className="eyebrow">DRILLLOOP WORKSPACE</p><h1>Sign in</h1><p>Use your named account to access authorized exercises.</p>{error && <div className="alert error-alert" role="alert"><AlertTriangle size={17} /><span>{error}</span></div>}<label><span>USERNAME</span><input autoComplete="username" value={loginForm.username} onChange={event => setLoginForm({ ...loginForm, username: event.target.value })} required /></label><label><span>PASSWORD</span><input type="password" autoComplete="current-password" value={loginForm.password} onChange={event => setLoginForm({ ...loginForm, password: event.target.value })} required /></label><button className="button primary" type="submit" disabled={busy || !authenticated}>{busy ? 'Signing in…' : 'Sign in'}</button><small>Accounts are configured by the workspace administrator.</small></form></div>

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark"><Activity size={21} strokeWidth={2.5} /></div><div><strong>drillloop</strong><span>EXERCISE INTELLIGENCE</span></div></div>
        <div className="workspace-label">WORKSPACE</div>
        <button className="nav-link active"><Gauge size={17} /> Exercises <span className="nav-count">{exercises.length}</span></button>
        <button className="nav-link" onClick={() => setTab('actions')}><ListChecks size={17} /> Improvement plan</button>
        <button className="nav-link" onClick={() => setTab('evidence')}><FolderOpen size={17} /> Evidence library</button>
        <div className="sidebar-divider" />
        <div className="workspace-label">CURRENT EXERCISE</div>
        <select id="exercise-picker" className="exercise-switcher" aria-label="Select exercise" value={selectedId} onChange={e => selectExercise(e.target.value)}>
          <option value="">Select an exercise</option>
          {exercises.map(exercise => <option value={exercise.id} key={exercise.id}>{exercise.title} · {exercise.id}</option>)}
        </select>
        <div className="subnav">
          {(['overview', 'evidence', 'timeline', 'findings', 'actions'] as Tab[]).map((item, index) => {
            const Icon = [Activity, FileText, Clock3, ShieldCheck, ListChecks][index]
            const labels = ['Overview', 'Evidence', 'Timeline', 'Findings', 'Actions']
            return <button className={`subnav-link ${tab === item ? 'selected' : ''}`} key={item} onClick={() => setTab(item)}><Icon size={15} />{labels[index]}{item === 'findings' && findingCounts.proposed > 0 && <span className="tiny-count">{findingCounts.proposed}</span>}</button>
          })}
        </div>
        <div className="sidebar-bottom">
          <div className="local-box"><div className="local-icon"><LockKeyhole size={15} /></div><div><strong>Local-first workspace</strong><span>No cloud API required</span></div><span className="online-dot" /></div>
          <div className="profile-row"><div className="user-avatar">{initials(identity?.name || 'User')}</div><div><strong>{identity?.name}</strong><span>{identity?.role} access</span></div><button className="text-link" onClick={() => void signOut()}>Sign out</button></div>
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div className="breadcrumbs"><span>Exercises</span><ChevronRight size={14} /><strong>{selectedExercise?.id || 'New exercise'}</strong></div>
          <div className="topbar-actions">
            <span className="identity-label">{identity?.name} · {identity?.role}</span>
            <button className="avatar-small" title="Sign out" onClick={() => void signOut()}>{initials(identity?.name || 'User')}</button>
          </div>
        </header>

        <div className="content-wrap">
          {error && <div className="alert error-alert" role="alert"><AlertTriangle size={17} /><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError('')}><X size={15} /></button></div>}
          {notice && <div className="alert success-alert" role="status"><CheckCircle2 size={17} /><span>{notice}</span><button aria-label="Dismiss message" onClick={() => setNotice('')}><X size={15} /></button></div>}
          {!data ? <EmptyState canEdit={Boolean(canEdit)} canSeed={Boolean(canEdit && capabilities?.synthetic_demo_seed_enabled)} onSeed={() => withBusy(async () => { const seeded = await api<{ id: string }>('/demo/seed', { method: 'POST' }); await refreshExercises(); await refreshDetail(seeded.id) })} onCreate={() => setCreateOpen(true)} /> : <>
            <div className="page-heading">
              <div className="heading-copy">
                <div className="eyebrow"><span className="eyebrow-dot" /> EXERCISE WORKSPACE <span className="heading-separator">/</span> {selectedExercise?.id}</div>
                <h1>{selectedExercise?.title}</h1>
                <p>{selectedExercise?.scenario}</p>
                <div className="heading-meta"><span><Clock3 size={14} /> {selectedExercise?.exercise_date} · {selectedExercise?.duration_minutes} minutes</span><span className="meta-divider" /><span><UsersIcon /> {selectedExercise?.participants.length} participating teams</span><span className="draft-pill"><Circle size={7} fill="currentColor" /> DRAFT REVIEW</span></div>
              </div>
              <div className="heading-buttons">
                {canEdit && <button className="button secondary" onClick={() => setCreateOpen(true)}><Plus size={16} /> New exercise</button>}
                {canEdit && <button className="button secondary" onClick={() => void openAccess()} disabled={busy}><UsersIcon /> Manage access</button>}
                {canEdit && <button className="button primary" onClick={() => void runAnalysis()} disabled={busy}><Sparkles size={16} />{busy ? 'Working…' : 'Run evidence analysis'}</button>}
              </div>
            </div>

            <div className="tabs-row">
              <div className="tabs">{(['overview', 'evidence', 'timeline', 'findings', 'actions'] as Tab[]).map((item, index) => {
                const names = ['Overview', 'Evidence', 'Timeline', 'Findings', 'Corrective actions']
                const count = item === 'evidence' ? data.sources.length : item === 'findings' ? data.findings.length : item === 'actions' ? data.actions.length : null
                return <button key={item} className={`tab ${tab === item ? 'active-tab' : ''}`} onClick={() => setTab(item)}>{names[index]}{count !== null && <span className="tab-count">{count}</span>}</button>
              })}</div>
              <button className="export-btn" onClick={() => void exportReport()} disabled={busy}><ArrowDownToLine size={15} /> Export report + improvement plan</button>
            </div>

            {tab === 'overview' && <Overview data={data} counts={findingCounts} busy={busy} onTab={setTab} onEvidence={setEvidenceOpen} onEditObjectives={canEdit ? () => { setObjectiveDraft(formatObjectives(data.exercise.objectives)); setObjectivesOpen(true) } : undefined} />}
            {tab === 'evidence' && <EvidenceView data={data} capabilities={capabilities} canEdit={Boolean(canEdit)} filteredSources={filteredSources} sourceFilter={sourceFilter} setSourceFilter={setSourceFilter} onUpload={uploadFiles} onTranscribe={transcribeFile} />}
            {tab === 'timeline' && <TimelineView data={data} onEvidence={setEvidenceOpen} />}
            {tab === 'findings' && <FindingsView data={data} busy={busy} canReview={Boolean(canReview)} onReview={reviewFinding} onEvidence={setEvidenceOpen} />}
            {tab === 'actions' && <ActionsView data={data} busy={busy} canEdit={Boolean(canEdit)} canReview={Boolean(canReview)} onSave={saveAction} onReview={reviewAction} onClose={closeAction} />}

            <footer className="page-footer"><span><ShieldCheck size={14} /> Original file, exact location, and file-integrity check are retained.</span><span>Source-linked · human review required · DrillLoop is not certified</span></footer>
          </>}
        </div>
      </main>
      {evidenceOpen && <EvidenceModal evidence={evidenceOpen} onClose={() => setEvidenceOpen(null)} />}
      {accessOpen && <AccessModal grants={accessGrants} users={configuredUsers} currentUserId={identity.id} busy={busy} onGrant={grantAccess} onRevoke={revokeAccess} onClose={() => setAccessOpen(false)} />}
      {createOpen && canEdit && <CreateModal form={newForm} setForm={setNewForm} onClose={() => setCreateOpen(false)} onSubmit={createExercise} busy={busy} />}
      {objectivesOpen && <ObjectiveEditor value={objectiveDraft} onChange={setObjectiveDraft} onClose={() => setObjectivesOpen(false)} onSubmit={saveObjectives} busy={busy} />}
      {busy && <div className="busy-indicator"><LoaderCircle size={15} className="spin" /> Saving review workspace…</div>}
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

function Overview({ data, counts, busy, onTab, onEvidence, onEditObjectives }: { data: Detail; counts: { proposed: number; approved: number; improvement: number }; busy: boolean; onTab: (tab: Tab) => void; onEvidence: (item: Support) => void; onEditObjectives?: () => void }) {
  const strengths = data.findings.filter(item => item.category === 'strength')
  const improvements = data.findings.filter(item => item.category === 'improvement')
  const approvedActions = data.actions.filter(action => action.status === 'approved' || action.status === 'closed').length
  const pendingActions = data.actions.filter(action => action.status === 'proposed' || action.status === 'approved').length
  const timeline = data.timeline.slice(0, 6)
  return <>
    <div className="metrics-grid">
      <Metric label="Evidence sources" value={String(data.sources.length).padStart(2, '0')} detail={`${data.timeline.length} extracted observations`} icon={<FolderOpen size={18} />} tone="teal" />
      <Metric label="Timeline events" value={String(data.timeline.length).padStart(2, '0')} detail={`${data.timeline_conflicts.length} timing conflict flagged`} icon={<Clock3 size={18} />} tone="blue" />
      <Metric label="Draft findings" value={String(counts.proposed).padStart(2, '0')} detail={`${counts.approved} approved by reviewer`} icon={<ShieldCheck size={18} />} tone="amber" />
      <Metric label="Improvement actions" value={String(data.actions.length).padStart(2, '0')} detail={`${approvedActions} approved · ${pendingActions} open`} icon={<ListChecks size={18} />} tone="violet" />
    </div>

    {data.timeline_conflicts.length > 0 && <div className="conflict-banner"><div className="conflict-icon"><AlertTriangle size={17} /></div><div><strong>{data.timeline_conflicts.length} timing conflict(s) need evaluator reconciliation</strong><span>Conflicting source statements remain visible with their locators; the system leaves resolution to an evaluator.</span></div><button onClick={() => onTab('timeline')}>Review conflict <ChevronRight size={14} /></button></div>}

    <div className="overview-grid">
      <section className="panel timeline-panel">
        <div className="panel-heading"><div><h2>Exercise timeline</h2><p>Normalized from uploaded evidence · source-linked</p></div><button className="text-link" onClick={() => onTab('timeline')}>Full timeline <ChevronRight size={14} /></button></div>
        <div className="timeline-preview">
          {timeline.map((event, index) => <div className={`timeline-row ${event.time_confidence === 'uncertain' ? 'uncertain-row' : ''}`} key={event.id}>
            <div className="timeline-time">{shortTime(event.event_time_normalized)}</div><div className={`timeline-marker ${index === 0 ? 'first' : ''}`}><span /></div>
            <div className="timeline-event"><strong>{event.text}</strong><button className="source-link" onClick={() => onEvidence({ source_id: event.source_id, source_filename: event.source_filename, observation_id: event.id, source_locator: event.source_locator, text: event.text, event_time_normalized: event.event_time_normalized, time_confidence: event.time_confidence })}><FileText size={12} /> {event.source_filename} · {event.source_locator}</button></div>
            {event.time_confidence !== 'certain' && <span className={`certainty-pill ${event.time_confidence}`}>{timeLabel(event.time_confidence)}</span>}
          </div>)}
          {timeline.length === 0 && <div className="muted-empty">Add notes or event logs to build the exercise timeline.</div>}
        </div>
        <button className="panel-bottom-link" onClick={() => onTab('timeline')}>Explore full event timeline <ChevronRight size={15} /></button>
      </section>
      <section className="panel findings-panel">
        <div className="panel-heading"><div><h2>Evaluator findings</h2><p>Evidence-backed observations for review</p></div><button className="icon-button" onClick={() => onTab('findings')}><Filter size={15} /></button></div>
        <div className="finding-summary"><span><i className="dot improvement" /> Areas for improvement <b>{improvements.length}</b></span><span><i className="dot strength" /> Strengths <b>{strengths.length}</b></span></div>
        <div className="finding-list-mini">
          {data.findings.slice(0, 4).map(finding => <button className="mini-finding" key={finding.id} onClick={() => onTab('findings')}>
            <span className={`finding-icon ${finding.category}`}>{finding.category === 'strength' ? <Check size={15} /> : <AlertTriangle size={14} />}</span>
            <span className="mini-finding-copy"><strong>{finding.title}</strong><small>{finding.objective_id || 'Objective mapping needed'} <span>·</span> {finding.evidence_ids.length} evidence links</small></span>
            <span className={`status-chip ${finding.status}`}>{finding.status}</span><ChevronRight size={14} className="mini-chevron" />
          </button>)}
          {data.findings.length === 0 && <div className="muted-empty">Run evidence analysis to prepare candidate findings.</div>}
        </div>
        <div className="human-review-note"><ShieldCheck size={15} /><span><strong>Evaluator review required</strong><br />Automated drafts are not approved findings until a reviewer confirms them.</span></div>
        <button className="panel-bottom-link" onClick={() => onTab('findings')}>Review all findings <ChevronRight size={15} /></button>
      </section>
    </div>

      <div className="bottom-grid">
      <section className="panel objective-panel"><div className="panel-heading"><div><h2>Exercise objectives</h2><p>Performance criteria agreed before exercise play</p></div><div className="objective-heading-actions"><span className="small-count">{data.exercise.objectives.length} objectives</span>{onEditObjectives && <button className="text-link" onClick={onEditObjectives} disabled={data.analysis_locked} title={data.analysis_locked ? 'Objectives are locked after analysis to protect existing findings' : 'Edit objective wording and measurable rules'}>Edit objectives</button>}</div></div>
        {data.exercise.objectives.map((objective, index) => {
          const assessment = data.objective_assessments.find(item => item.objective_id === objective.id)
          const state = assessment?.state.replaceAll('_', ' ') || 'needs review'
          return <div className="objective-row" key={objective.id}><span className="objective-number">{String(index + 1).padStart(2, '0')}</span><span className="objective-id">{objective.id}</span><p>{objective.text}</p><span className="objective-findings">{state}</span></div>
        })}
        {data.exercise.objectives.length === 0 && <div className="incomplete-objectives"><AlertTriangle size={16} /><span>No objectives are configured. Analysis is paused until the exercise owner adds at least one.</span></div>}
      </section>
      <section className="panel action-preview"><div className="panel-heading"><div><h2>Improvement plan</h2><p>Proposed actions from evaluator findings</p></div><button className="text-link" onClick={() => onTab('actions')}>View register <ChevronRight size={14} /></button></div>
        {data.actions.slice(0, 3).map(action => <div className="action-preview-row" key={action.id}><span className={`priority-line ${action.priority}`} /><span className="action-preview-copy"><strong>{action.title}</strong><small>{action.owner || <span className="owner-missing">Owner not assigned</span>}</small></span><span className={`status-chip ${action.status === 'closed' ? 'approved' : action.status}`}>{action.status.replace('_', ' ')}</span></div>)}
        {data.actions.length === 0 && <div className="muted-empty">Actions will appear when improvement findings are drafted.</div>}
        <button className="button secondary full-width" onClick={() => onTab('actions')} disabled={busy}><ListChecks size={15} /> Open corrective action register</button>
      </section>
    </div>
    <div className="pipeline-strip"><div className="pipeline-title"><Sparkles size={16} /><strong>Offline evidence workflow</strong><span>Human-in-the-loop by design</span></div><div className="pipeline-steps"><span><i>1</i>Extract</span><ChevronRight size={13} /><span><i>2</i>Map to objectives</span><ChevronRight size={13} /><span><i>3</i>Attach evidence</span><ChevronRight size={13} /><span><i>4</i>Evaluator review</span></div><div className="pipeline-status"><span className="online-dot" /> {busy ? 'Processing' : 'Ready'}</div></div>
  </>
}

function Metric({ label, value, detail, icon, tone }: { label: string; value: string; detail: string; icon: React.ReactNode; tone: string }) {
  return <div className="metric-card"><div className={`metric-icon ${tone}`}>{icon}</div><div className="metric-content"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div><div className={`metric-accent ${tone}`} /></div>
}

function EvidenceView({ data, capabilities, canEdit, filteredSources, sourceFilter, setSourceFilter, onUpload, onTranscribe }: { data: Detail; capabilities: Capabilities | null; canEdit: boolean; filteredSources: Source[]; sourceFilter: string; setSourceFilter: (value: string) => void; onUpload: (files: FileList | null) => void; onTranscribe: (file?: File) => void }) {
  const [dragging, setDragging] = useState(false)
  const observations = data.timeline
  return <div className="tab-page">
    <div className="section-title-row"><div><h2>Evidence library</h2><p>Every imported record retains its source, location, and integrity hash.</p></div>{canEdit && <label className="button primary upload-button"><Upload size={15} /> Add evidence<input type="file" multiple accept=".txt,.md,.csv,.json,.pdf,text/plain,text/csv,application/pdf,application/json" onChange={e => onUpload(e.target.files)} /></label>}</div>
    {canEdit && <div className={`upload-drop ${dragging ? 'dragging' : ''}`} onDragOver={e => { e.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); onUpload(e.dataTransfer.files) }}>
      <div className="upload-icon"><Upload size={21} /></div><div><strong>Drop exercise notes, logs, or reports here</strong><span>TXT, CSV, JSON transcript, or selectable-text PDF · 15 MB max per file</span></div><label className="button secondary small-button">Browse files<input type="file" multiple accept=".txt,.md,.csv,.json,.pdf" onChange={e => onUpload(e.target.files)} /></label>
    </div>}
    <div className="section-header-line"><h3>Imported sources <span className="count-badge">{data.sources.length}</span></h3><div className="search-box"><Search size={14} /><input value={sourceFilter} onChange={e => setSourceFilter(e.target.value)} placeholder="Search sources" /></div></div>
    <div className="source-grid">
      {filteredSources.map(source => <div className="source-card" key={source.id}><div className={`source-type-icon ${source.kind}`}>{source.kind === 'csv' ? <Activity size={18} /> : source.kind === 'transcript' ? <AudioLines size={18} /> : source.kind === 'pdf' ? <FileText size={18} /> : <MessageSquareText size={18} />}</div><div className="source-card-main"><div className="source-name-row"><strong>{source.filename}</strong><span className="source-kind">{source.kind}</span></div><p>{source.observation_count} observations · integrity check {source.sha256.slice(0, 12)}…</p><div className="source-tags"><span><FileCheck2 size={12} /> Imported</span><span>{source.scan_status === 'clean' ? 'Malware scan passed' : 'Not malware-scanned'}</span>{source.kind === 'transcript' && <span className="transcript-model">{String(source.provenance.model || 'Transcript')} · {String(source.provenance.language || 'language ?')}</span>}</div></div><button className="icon-button" title="View extracted observations" onClick={() => document.getElementById(`observations-${source.id}`)?.scrollIntoView({ behavior: 'smooth' })}><ChevronRight size={16} /></button></div>)}
      {filteredSources.length === 0 && <div className="empty-card">No evidence source matches that search.</div>}
    </div>
    <div className="section-header-line observations-heading"><div><h3>Extracted observations</h3><p>Text is preserved exactly as imported; timeline normalization is shown separately.</p></div></div>
    <div className="observation-list">{observations.map(obs => <div className="observation-row" key={obs.id} id={`observations-${obs.source_id}`}><div className="observation-time">{shortTime(obs.event_time_normalized)}</div><div className="observation-body"><p>{obs.text}</p><span>{obs.source_filename} · {obs.source_locator}</span></div><span className={`certainty-pill ${obs.time_confidence}`}>{timeLabel(obs.time_confidence)}</span>{obs.recognition_confidence !== null && <span className={`recognition-pill ${obs.recognition_confidence < .75 ? 'low' : ''}`}>Speech-to-text match {Math.round(obs.recognition_confidence * 100)}%</span>}</div>)}</div>
    {data.timeline_conflicts.length > 0 && <div className="conflict-detail"><AlertTriangle size={16} /><div><strong>Conflicting timing note retained</strong>{data.timeline_conflicts.map(item => <p key={item.observation_id}>{item.description} <span>{item.source_filename} · {item.source_locator}</span></p>)}</div></div>}
    <div className="asr-card"><div className="asr-head"><div className="asr-icon"><FileAudio size={19} /></div><div><h3>Offline audio transcription</h3><p>Optional faster-whisper speech-to-text · runs locally · no cloud service</p></div><span className={`asr-state ${capabilities?.asr.available ? 'ready' : 'unavailable'}`}><i />{capabilities?.asr.available ? 'Model ready' : 'Model unavailable'}</span></div><div className="asr-details"><div><span>Software</span><strong>{capabilities?.asr.package_version || 'Not installed'}</strong></div><div><span>Language</span><strong>Detected at runtime</strong></div><div><span>Speaker separation</span><strong>Not provided</strong></div></div><div className="asr-footer"><span>{capabilities?.asr.note || 'Provide a local model directory to enable audio transcription.'}</span>{canEdit && <label className={`button secondary small-button ${!capabilities?.asr.available ? 'disabled-look' : ''}`}>Choose audio<input type="file" accept="audio/wav,audio/mpeg,audio/mp4,audio/flac,audio/ogg,.wav,.mp3,.m4a,.flac,.ogg" onChange={e => onTranscribe(e.target.files?.[0])} /></label>}</div></div>
  </div>
}

function TimelineView({ data, onEvidence }: { data: Detail; onEvidence: (item: Support) => void }) {
  const sorted = [...data.timeline].sort((a, b) => (a.event_time_normalized || '9999').localeCompare(b.event_time_normalized || '9999'))
  return <div className="tab-page"><div className="section-title-row"><div><h2>Reconstructed timeline</h2><p>Time order is derived from explicit timestamps only. Missing times remain unplaced.</p></div><div className="timeline-legend"><span><i className="legend-dot certain" /> Time available</span><span><i className="legend-dot uncertain" /> Uncertain</span><span><i className="legend-dot missing" /> Missing</span></div></div>
    {data.timeline_conflicts.length > 0 && <div className="conflict-banner wide"><div className="conflict-icon"><AlertTriangle size={17} /></div><div><strong>Time conflict · not resolved by the system</strong>{data.timeline_conflicts.map(item => <span key={item.observation_id}>{item.description} · {item.source_filename}, {item.source_locator}</span>)}</div></div>}
    <div className="full-timeline">{sorted.map(event => <div className={`full-event ${event.time_confidence}`} key={event.id}><div className="full-time"><strong>{shortTime(event.event_time_normalized)}</strong><span>{timeLabel(event.time_confidence)}</span></div><div className="full-track"><div className="full-dot" /><div className="full-line" /></div><div className="full-event-card"><div className="event-card-head"><span className={`event-type-tag ${event.observation_type}`}>{event.observation_type.replace('_', ' ')}</span><span className="source-locator-tag"><FileText size={12} /> {event.source_filename} · {event.source_locator}</span></div><p>{event.text}</p><div className="event-card-foot"><span>{event.extraction_method === 'asr' ? 'Speech-to-text result · reviewer must check' : 'Source text preserved'}</span><button className="text-link" onClick={() => onEvidence({ source_id: event.source_id, source_filename: event.source_filename, observation_id: event.id, source_locator: event.source_locator, text: event.text, event_time_normalized: event.event_time_normalized, time_confidence: event.time_confidence })}>View source <ChevronRight size={13} /></button></div></div></div>)}
      {sorted.length === 0 && <div className="empty-card">No events to display yet. Import text notes or a CSV event log.</div>}</div>
    <div className="timeline-note"><HelpCircle size={15} /><span>Events with matching times are placed together. Ambiguous references and timing conflicts are shown as provided; the timeline never invents an event order.</span></div>
  </div>
}

function FindingsView({ data, busy, canReview, onReview, onEvidence }: { data: Detail; busy: boolean; canReview: boolean; onReview: (finding: Finding, decision: 'approved' | 'rejected') => void; onEvidence: (item: Support) => void }) {
  return <div className="tab-page"><div className="section-title-row"><div><h2>Finding review</h2><p>Proposed claims are separated from their interpretation and source evidence.</p></div><div className="review-guard"><LockKeyhole size={14} /> {canReview ? 'Authorized reviewer' : 'Read-only · reviewer access required'}</div></div>
    <div className="finding-review-list">{data.findings.map(finding => <article className="finding-card" key={finding.id}><div className="finding-card-top"><div className={`finding-icon large ${finding.category}`}>{finding.category === 'strength' ? <Check size={17} /> : <AlertTriangle size={16} />}</div><div className="finding-title-block"><div className="finding-kicker">{finding.category === 'strength' ? 'OBSERVED STRENGTH' : 'AREA FOR IMPROVEMENT'} <span>·</span> {finding.code}</div><h3>{finding.title}</h3></div><span className={`status-chip ${finding.status}`}>{finding.status}</span></div>
      <div className="finding-objective"><span>LINKED OBJECTIVE</span><strong>{finding.objective_id || 'Unmapped · reviewer mapping required'}</strong><small>{data.exercise.objectives.find(obj => obj.id === finding.objective_id)?.text || 'No objective mapping available'}</small></div>
      <div className="finding-analysis"><div><span className="analysis-label"><EyeIcon /> Observation</span><p>{finding.observation}</p></div><div><span className="analysis-label"><Sparkles size={13} /> Evaluator interpretation</span><p>{finding.interpretation}</p></div></div>
      <div className="citation-block"><div className="citation-head"><span><FileCheck2 size={14} /> SUPPORTING EVIDENCE</span><span>{finding.supporting_evidence.length} linked record{finding.supporting_evidence.length === 1 ? '' : 's'}</span></div><div className="citation-list">{finding.supporting_evidence.map(item => <button className="citation-row" key={item.observation_id} onClick={() => onEvidence(item)}><span className="citation-file"><FileText size={14} /></span><span><strong>{item.source_filename}</strong><small>{item.source_locator} · “{item.text.slice(0, 180)}”</small></span><ChevronRight size={14} /></button>)}</div></div>
      <div className="finding-card-footer"><div className="finding-confidence"><span className={`confidence-dot ${finding.confidence}`} /> Rule-based match · {finding.confidence} confidence <span className="footer-dot">·</span> {finding.status === 'proposed' ? 'Awaiting evaluator decision' : `${finding.status} by ${finding.reviewer || 'reviewer'}`}</div>{canReview && finding.status === 'proposed' && <div className="review-buttons"><button className="button reject" onClick={() => onReview(finding, 'rejected')} disabled={busy}><XCircle size={15} /> Reject</button><button className="button approve" onClick={() => onReview(finding, 'approved')} disabled={busy}><CheckCircle2 size={15} /> Approve finding</button></div>}</div>
      {finding.review_note && <div className="review-note"><strong>Reviewer note:</strong> {finding.review_note}</div>}
    </article>)}
    {data.findings.length === 0 && <div className="empty-card tall"><ShieldCheck size={25} /><h3>No findings prepared yet</h3><p>Import evidence, make sure objectives are present, then run the offline evidence analysis.</p></div>}</div>
    <div className="safety-note"><ShieldCheck size={16} /><span><strong>Human decision stays with the evaluator.</strong> DrillLoop drafts and cites; only an authorized reviewer can approve or reject findings.</span></div>
  </div>
}

function EyeIcon() { return <Search size={13} /> }

function ActionsView({ data, busy, canEdit, canReview, onSave, onReview, onClose }: { data: Detail; busy: boolean; canEdit: boolean; canReview: boolean; onSave: (action: Action, form: HTMLFormElement) => void; onReview: (action: Action, decision: 'approved' | 'rejected') => void; onClose: (action: Action) => void }) {
  return <div className="tab-page"><div className="section-title-row"><div><h2>Corrective-action register</h2><p>Approval and closure require an authorized reviewer and verifiable completion evidence.</p></div><div className="register-summary"><span>{data.actions.filter(a => a.status !== 'closed').length} open</span><span className="register-sep" /><span>{data.actions.filter(a => a.status === 'closed').length} closed</span></div></div>
    <div className="action-review-list">{data.actions.map(action => <article className={`action-card ${action.owner ? '' : 'owner-gap'}`} key={action.id}><div className="action-card-head"><div className={`action-priority ${action.priority}`}><i />{action.priority}</div><span className="action-linked-finding"><ShieldCheck size={13} /> {action.finding_title}</span><span className={`status-chip ${action.status === 'closed' ? 'approved' : action.status}`}>{action.status.replace('_', ' ')}</span></div>
      <p className="action-support">Linked to {action.evidence_ids.length} source observation{action.evidence_ids.length === 1 ? '' : 's'} and its reviewed finding.</p>
      <form className="action-edit-grid" onSubmit={e => { e.preventDefault(); onSave(action, e.currentTarget) }}>
        <label className="action-title-label"><span>CORRECTIVE ACTION</span><input name="title" defaultValue={action.title} disabled={!canEdit || action.status === 'closed'} /></label>
        <label><span>RESPONSIBLE OWNER / TEAM</span><input name="owner" defaultValue={action.owner || ''} placeholder="Assign a person or team" disabled={!canEdit || action.status === 'closed'} className={!action.owner ? 'missing-input' : ''} /></label>
        <label><span>PRIORITY</span><select name="priority" defaultValue={action.priority} disabled={!canEdit || action.status === 'closed'}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option></select></label>
        <label><span>DUE DATE</span><input name="due_date" type="date" defaultValue={action.due_date || ''} disabled={!canEdit || action.status === 'closed'} /></label>
        <label className="acceptance-label"><span>HOW TO VERIFY COMPLETION</span><textarea name="acceptance_criteria" defaultValue={action.acceptance_criteria} rows={2} disabled={!canEdit || action.status === 'closed'} /></label>
        {action.owner === null && <div className="owner-gap-note"><AlertTriangle size={15} /><span><strong>Owner missing in source register.</strong> This action cannot be approved until an accountable role or team is assigned.</span></div>}
        {(action.status !== 'closed' && (canEdit || (canReview && action.status === 'proposed'))) && <div className="action-controls">{canEdit && <button type="submit" className="button secondary" disabled={busy}><Check size={14} /> Save action</button>}{canReview && action.status === 'proposed' && <><button type="button" className="button reject" onClick={() => onReview(action, 'rejected')} disabled={busy}><XCircle size={14} /> Reject</button><button type="button" className="button approve" onClick={() => onReview(action, 'approved')} disabled={busy || !action.owner || !action.due_date || data.findings.find(f => f.id === action.finding_id)?.status !== 'approved'} title={!action.owner ? 'Assign an owner first' : !action.due_date ? 'Set a due date first' : data.findings.find(f => f.id === action.finding_id)?.status !== 'approved' ? 'Approve linked finding first' : ''}><CheckCircle2 size={14} /> Approve action</button></>}</div>}
      </form>
      {action.status === 'approved' && <div className="closure-row"><span><CheckCircle2 size={16} /> Approved by {action.reviewer || 'reviewer'} · closure evidence required</span>{canReview && <button className="button primary" onClick={() => onClose(action)} disabled={busy}><FileCheck2 size={14} /> Record closure</button>}</div>}
      {action.status === 'closed' && <div className="closure-record"><CheckCircle2 size={16} /><span><strong>Closed by {action.reviewer || 'reviewer'}</strong><br />{action.closure_evidence}</span></div>}
    </article>)}
      {data.actions.length === 0 && <div className="empty-card tall"><ListChecks size={25} /><h3>No corrective actions</h3><p>Evidence-backed improvement findings will generate proposed actions for review.</p></div>}</div>
    <div className="safety-note"><LockKeyhole size={15} /><span>Named-user permissions control edits and review decisions. An action cannot close until an authorized reviewer approves it and records proof that the work is complete.</span></div>
  </div>
}

function EvidenceModal({ evidence, onClose }: { evidence: Support; onClose: () => void }) {
  const dialogRef = useAccessibleDialog<HTMLElement>(onClose)
  return <div className="modal-shade" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}><section ref={dialogRef} className="evidence-modal" role="dialog" aria-modal="true" aria-labelledby="evidence-heading" tabIndex={-1}>
    <div className="modal-head"><div className="modal-file-icon"><FileText size={19} /></div><div><span>ORIGINAL SOURCE EVIDENCE</span><h2 id="evidence-heading">{evidence.source_filename}</h2></div><button className="icon-button" onClick={onClose} aria-label="Close source view"><X size={18} /></button></div>
    <div className="source-metadata"><span><strong>Exact location</strong>{evidence.source_locator}</span><span><strong>Event time</strong>{evidence.event_time_normalized ? shortTime(evidence.event_time_normalized) : 'Unresolved'}</span><span><strong>Time quality</strong>{timeLabel(evidence.time_confidence)}</span></div><div className="source-quote"><div className="quote-mark">“</div><p>{evidence.text}</p><span>Exact extracted text · no paraphrase</span></div>
    <div className="modal-footer"><span>Evidence record · {evidence.observation_id.slice(0, 12)}</span><a className="button secondary" href={`/api/sources/${evidence.source_id}/download`}><ArrowDownToLine size={14} /> Download original file</a><button className="button secondary" onClick={onClose}>Close source view</button></div>
  </section></div>
}

type CreateForm = { id: string; title: string; scenario: string; exercise_date: string; duration_minutes: string; objectives: string; evaluator_roles: string; participants: string; milestones: string }
function CreateModal({ form, setForm, onClose, onSubmit, busy }: { form: CreateForm; setForm: React.Dispatch<React.SetStateAction<CreateForm>>; onClose: () => void; onSubmit: () => void; busy: boolean }) {
  const dialogRef = useAccessibleDialog<HTMLElement>(onClose)
  const update = (field: keyof typeof form, value: string) => setForm({ ...form, [field]: value })
  return <div className="modal-shade"><section ref={dialogRef} className="create-modal" role="dialog" aria-modal="true" aria-labelledby="create-heading" tabIndex={-1}><div className="modal-head"><div className="modal-file-icon"><Plus size={19} /></div><div><span>EXERCISE SETUP</span><h2 id="create-heading">Create an exercise</h2></div><button className="icon-button" onClick={onClose} aria-label="Close exercise form"><X size={18} /></button></div><div className="create-form">
    <div className="form-two"><label><span>EXERCISE ID</span><input value={form.id} onChange={e => update('id', e.target.value)} placeholder="EXERCISE-2026-02" /></label><label><span>DATE</span><input type="date" value={form.exercise_date} onChange={e => update('exercise_date', e.target.value)} /></label></div>
    <label><span>EXERCISE NAME</span><input value={form.title} onChange={e => update('title', e.target.value)} placeholder="Night shift communications exercise" /></label>
    <label><span>SCENARIO</span><textarea rows={3} value={form.scenario} onChange={e => update('scenario', e.target.value)} placeholder="Describe the simulated situation and scope." /></label>
    <label><span>OBJECTIVES · one per line; prefix with ID: to set an ID</span><textarea rows={5} value={form.objectives} onChange={e => update('objectives', e.target.value)} placeholder={'OBJ-01: Restore essential services within 5 minutes | within=5m | start=power supply failed | complete=essential circuits restored'} /></label>
    <div className="objective-rule-help"><HelpCircle size={14} /><span>For a measurable elapsed-time rule, add <code>within=5m</code>, <code>start=source phrase</code>, and <code>complete=source phrase</code>, separated by |. Separate alternative phrases with semicolons. Unclear rules stay in Needs review.</span></div>
    <label><span>EXPECTED MILESTONES · one per line</span><textarea rows={2} value={form.milestones} onChange={e => update('milestones', e.target.value)} placeholder="Generator stable and essential circuits checked" /></label>
    <div className="form-two"><label><span>EVALUATOR ROLES · comma-separated</span><input value={form.evaluator_roles} onChange={e => update('evaluator_roles', e.target.value)} placeholder="Facilities, Clinical" /></label><label><span>PARTICIPANTS / TEAMS · comma-separated</span><input value={form.participants} onChange={e => update('participants', e.target.value)} placeholder="Incident Command, ICU" /></label></div>
    <div className="form-two"><label><span>DURATION · MINUTES</span><input type="number" value={form.duration_minutes} onChange={e => update('duration_minutes', e.target.value)} /></label><div className="form-hint"><HelpCircle size={14} /> Objectives without a clear rule remain Needs review; missing evidence is not treated as failure.</div></div>
    </div><div className="modal-footer"><span>Exercise data is stored in the configured local database.</span><div><button className="button secondary" onClick={onClose}>Cancel</button><button className="button primary" onClick={onSubmit} disabled={busy || !form.id || !form.title || !form.scenario}><Plus size={14} /> Create exercise</button></div></div></section></div>
}
