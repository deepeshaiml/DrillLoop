import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Activity, AlertTriangle, ArrowDownToLine, AudioLines, Check, CheckCircle2, ChevronDown,
  ChevronRight, Circle, Clock3, FileAudio, FileCheck2, FileText, Filter, FolderOpen,
  Gauge, HeartPulse, HelpCircle, ListChecks, LoaderCircle, LockKeyhole,
  MessageSquareText, Plus, Search, ShieldCheck, Sparkles, Upload,
  X, XCircle, Zap,
} from 'lucide-react'

type Tab = 'overview' | 'evidence' | 'timeline' | 'findings' | 'actions'
type Source = { id: string; filename: string; kind: string; mime_type: string; sha256: string; provenance: Record<string, unknown>; observation_count: number }
type Observation = { id: string; source_id: string; source_filename: string; text: string; event_time_raw: string | null; event_time_normalized: string | null; time_confidence: string; source_locator: string; observation_type: string; extraction_method: string; recognition_confidence: number | null }
type Support = { source_id: string; source_filename: string; observation_id: string; source_locator: string; text: string; event_time_normalized: string | null; time_confidence: string }
type Finding = { id: string; code: string; title: string; category: 'strength' | 'improvement'; objective_id: string | null; observation: string; interpretation: string; evidence_ids: string[]; evidence_labels: string[]; confidence: string; status: string; review_note: string; reviewer: string | null; supporting_evidence: Support[] }
type Action = { id: string; finding_id: string; finding_title: string; title: string; evidence_ids: string[]; owner: string | null; priority: string; due_date: string | null; acceptance_criteria: string; status: string; reviewer_decision: string; reviewer: string | null; closure_evidence: string }
type Exercise = { id: string; title: string; scenario: string; exercise_date: string; duration_minutes: number; objectives: { id: string; text: string }[]; criteria: string[]; evaluator_roles: string[]; participants: string[]; expected_milestones: { id: string; expected: string; objective_id: string }[] }
type Detail = { exercise: Exercise; sources: Source[]; timeline: Observation[]; timeline_conflicts: { observation_id: string; source_id: string; source_filename: string; source_locator: string; description: string }[]; findings: Finding[]; actions: Action[]; audit_events: { actor: string; action: string; object_id: string; created_at: string }[] }
type Capabilities = { asr: { available: boolean; package_version: string | null; model_path_configured: boolean; note: string }; analysis: { mode: string; cloud_api_required: boolean }; review: { required_key: boolean; demo_key_hint: string | null } }

const api = async <T,>(path: string, options: RequestInit = {}): Promise<T> => {
  const response = await fetch(path.startsWith('/api') ? path : `/api${path}`, options)
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const data = await response.json()
      message = data.detail?.message || data.detail?.code || data.detail || message
    } catch { /* Keep HTTP status message. */ }
    throw new Error(message)
  }
  if (response.headers.get('content-type')?.includes('application/pdf')) return await response.blob() as T
  return await response.json() as T
}

const initials = (name: string) => name.split(' ').map(part => part[0]).join('').slice(0, 2).toUpperCase()
const shortTime = (value: string | null) => value ? value.slice(value.indexOf('T') + 1, value.indexOf('T') + 9) : 'Time unresolved'
const timeLabel = (value: string) => ({ certain: 'Time recorded', medium: 'Time recognized', uncertain: 'Time uncertain', unknown: 'Time missing' }[value] || value)

export default function App() {
  const [exercises, setExercises] = useState<Exercise[]>([])
  const [selectedId, setSelectedId] = useState('HOSP-PO-2026-01')
  const [data, setData] = useState<Detail | null>(null)
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null)
  const [tab, setTab] = useState<Tab>('overview')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [reviewKey, setReviewKey] = useState(() => sessionStorage.getItem('review-key') || 'demo-reviewer')
  const [reviewer, setReviewer] = useState(() => sessionStorage.getItem('reviewer-name') || 'Exercise Reviewer')
  const [sourceFilter, setSourceFilter] = useState('')
  const [evidenceOpen, setEvidenceOpen] = useState<Support | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [newForm, setNewForm] = useState({ id: '', title: '', scenario: '', exercise_date: new Date().toISOString().slice(0, 10), duration_minutes: '120', objectives: '', evaluator_roles: '', participants: '', milestones: '' })

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

  useEffect(() => {
    let live = true
    Promise.all([api<(Exercise & { finding_count: number })[]>('/exercises'), api<Capabilities>('/capabilities')])
      .then(([list, caps]) => {
        if (!live) return
        setExercises(list)
        setCapabilities(caps)
        const initial = list.find(item => item.id === selectedId)?.id || list[0]?.id
        if (initial) {
          setSelectedId(initial)
          return api<Detail>(`/exercises/${encodeURIComponent(initial)}`).then(detail => { if (live) setData(detail) })
        }
      })
      .catch((err: Error) => { if (live) setError(err.message) })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [])

  useEffect(() => { sessionStorage.setItem('review-key', reviewKey) }, [reviewKey])
  useEffect(() => { sessionStorage.setItem('reviewer-name', reviewer) }, [reviewer])

  const withBusy = async (task: () => Promise<void>) => {
    setBusy(true); setError(''); setNotice('')
    try { await task() } catch (err) { setError(err instanceof Error ? err.message : 'Something went wrong.') }
    finally { setBusy(false) }
  }

  const authHeaders = { 'Content-Type': 'application/json', 'X-Reviewer-Key': reviewKey }
  const findingCounts = useMemo(() => ({
    proposed: data?.findings.filter(f => f.status === 'proposed').length || 0,
    approved: data?.findings.filter(f => f.status === 'approved').length || 0,
    improvement: data?.findings.filter(f => f.category === 'improvement').length || 0,
  }), [data])

  const runAnalysis = () => withBusy(async () => {
    const result = await api<{ candidate_count: number; new_findings: number; model_status: string }>(`/exercises/${selectedId}/analyze`, { method: 'POST' })
    await refreshDetail()
    setNotice(`${result.candidate_count} evidence-linked draft(s) prepared. ${result.model_status}`)
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
    await api(`/findings/${finding.id}/review`, { method: 'POST', headers: authHeaders, body: JSON.stringify({ decision, reviewer, note: '' }) })
    await refreshDetail(); setNotice(`Finding ${decision}. The reviewer decision is recorded.`)
  })

  const saveAction = (action: Action, form: HTMLFormElement) => withBusy(async () => {
    const values = new FormData(form)
    await api(`/actions/${action.id}`, { method: 'PUT', headers: authHeaders, body: JSON.stringify({
      owner: String(values.get('owner') || '') || null, priority: values.get('priority'),
      due_date: String(values.get('due_date') || '') || null,
      acceptance_criteria: values.get('acceptance_criteria'), reviewer,
    }) })
    await refreshDetail(); setNotice('Corrective action updated.')
  })

  const reviewAction = (action: Action, decision: 'approved' | 'rejected') => withBusy(async () => {
    await api(`/actions/${action.id}/review`, { method: 'POST', headers: authHeaders, body: JSON.stringify({ decision, reviewer, note: '' }) })
    await refreshDetail(); setNotice(`Corrective action ${decision}.`)
  })

  const closeAction = (action: Action) => {
    const closure_evidence = window.prompt('Add closure evidence (for example, an exercise ID, test record, or approved document reference).')
    if (!closure_evidence) return
    withBusy(async () => {
      await api(`/actions/${action.id}/close`, { method: 'POST', headers: authHeaders, body: JSON.stringify({ closure_evidence, reviewer }) })
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
    const objectives = newForm.objectives.split('\n').map(line => line.trim()).filter(Boolean).map((text, index) => {
      const split = text.indexOf(':')
      return split > 0 ? { id: text.slice(0, split).trim(), text: text.slice(split + 1).trim() } : { id: `OBJ-${String(index + 1).padStart(2, '0')}`, text }
    })
    const expected_milestones = newForm.milestones.split('\n').map(line => line.trim()).filter(Boolean).map((expected, index) => ({ id: `M-${String(index + 1).padStart(2, '0')}`, expected, objective_id: objectives[0]?.id || '' }))
    const created = await api<Exercise>('/exercises', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
      id: newForm.id, title: newForm.title, scenario: newForm.scenario, exercise_date: newForm.exercise_date,
      duration_minutes: Number(newForm.duration_minutes), objectives, expected_milestones,
      criteria: [], evaluator_roles: newForm.evaluator_roles.split(',').map(x => x.trim()).filter(Boolean),
      participants: newForm.participants.split(',').map(x => x.trim()).filter(Boolean),
    }) })
    setSelectedId(created.id); setCreateOpen(false); await refreshExercises(); await refreshDetail(created.id)
    setTab('overview'); setNotice('Exercise created. Upload evidence to start its review.')
  })

  const selectedExercise = data?.exercise
  const filteredSources = data?.sources.filter(source => !sourceFilter || source.filename.toLowerCase().includes(sourceFilter.toLowerCase())) || []

  if (loading) return <div className="loading-screen"><div className="brand-mark"><Activity size={24} /></div><LoaderCircle className="spin" /> Loading exercise workspace</div>

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
        <button className="exercise-switcher" onClick={() => document.getElementById('exercise-picker')?.focus()}>
          <div className="exercise-avatar"><HeartPulse size={17} /></div>
          <div className="switcher-copy"><strong>{selectedExercise?.title || 'Select exercise'}</strong><span>{selectedExercise?.id || 'No exercise selected'}</span></div>
          <ChevronDown size={15} />
        </button>
        <div className="subnav">
          {(['overview', 'evidence', 'timeline', 'findings', 'actions'] as Tab[]).map((item, index) => {
            const Icon = [Activity, FileText, Clock3, ShieldCheck, ListChecks][index]
            const labels = ['Overview', 'Evidence', 'Timeline', 'Findings', 'Actions']
            return <button className={`subnav-link ${tab === item ? 'selected' : ''}`} key={item} onClick={() => setTab(item)}><Icon size={15} />{labels[index]}{item === 'findings' && findingCounts.proposed > 0 && <span className="tiny-count">{findingCounts.proposed}</span>}</button>
          })}
        </div>
        <div className="sidebar-bottom">
          <div className="local-box"><div className="local-icon"><LockKeyhole size={15} /></div><div><strong>Local-first workspace</strong><span>No cloud API required</span></div><span className="online-dot" /></div>
          <button className="profile-row"><div className="user-avatar">{initials(reviewer || 'ER')}</div><div><strong>{reviewer || 'Reviewer'}</strong><span>Evaluator access</span></div><ChevronDown size={14} /></button>
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div className="breadcrumbs"><span>Exercises</span><ChevronRight size={14} /><strong>{selectedExercise?.id || 'New exercise'}</strong></div>
          <div className="topbar-actions">
            <label className="reviewer-field"><span>REVIEWER</span><input value={reviewer} onChange={e => setReviewer(e.target.value)} aria-label="Reviewer name" /></label>
            <label className="key-field"><LockKeyhole size={13} /><input type="password" value={reviewKey} onChange={e => setReviewKey(e.target.value)} aria-label="Reviewer authorization key" placeholder="Reviewer key" /></label>
            <button className="avatar-small" title="Reviewer profile">{initials(reviewer || 'ER')}</button>
          </div>
        </header>

        <div className="content-wrap">
          {error && <div className="alert error-alert"><AlertTriangle size={17} /><span>{error}</span><button onClick={() => setError('')}><X size={15} /></button></div>}
          {notice && <div className="alert success-alert"><CheckCircle2 size={17} /><span>{notice}</span><button onClick={() => setNotice('')}><X size={15} /></button></div>}
          {!data ? <EmptyState onSeed={() => withBusy(async () => { await api('/demo/seed', { method: 'POST' }); await refreshExercises(); await refreshDetail('HOSP-PO-2026-01') })} onCreate={() => setCreateOpen(true)} /> : <>
            <div className="page-heading">
              <div className="heading-copy">
                <div className="eyebrow"><span className="eyebrow-dot" /> HOSPITAL · FUNCTIONAL EXERCISE <span className="heading-separator">/</span> {selectedExercise?.id}</div>
                <h1>{selectedExercise?.title}</h1>
                <p>{selectedExercise?.scenario}</p>
                <div className="heading-meta"><span><Clock3 size={14} /> {selectedExercise?.exercise_date} · {selectedExercise?.duration_minutes} minutes</span><span className="meta-divider" /><span><UsersIcon /> {selectedExercise?.participants.length} participating teams</span><span className="draft-pill"><Circle size={7} fill="currentColor" /> DRAFT REVIEW</span></div>
              </div>
              <div className="heading-buttons">
                <button className="button secondary" onClick={() => setCreateOpen(true)}><Plus size={16} /> New exercise</button>
                <button className="button primary" onClick={() => void runAnalysis()} disabled={busy}><Sparkles size={16} />{busy ? 'Working…' : 'Run evidence analysis'}</button>
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

            {tab === 'overview' && <Overview data={data} counts={findingCounts} busy={busy} onTab={setTab} onEvidence={setEvidenceOpen} />}
            {tab === 'evidence' && <EvidenceView data={data} capabilities={capabilities} filteredSources={filteredSources} sourceFilter={sourceFilter} setSourceFilter={setSourceFilter} onUpload={uploadFiles} onTranscribe={transcribeFile} />}
            {tab === 'timeline' && <TimelineView data={data} onEvidence={setEvidenceOpen} />}
            {tab === 'findings' && <FindingsView data={data} busy={busy} onReview={reviewFinding} onEvidence={setEvidenceOpen} />}
            {tab === 'actions' && <ActionsView data={data} busy={busy} onSave={saveAction} onReview={reviewAction} onClose={closeAction} />}

            <footer className="page-footer"><span><ShieldCheck size={14} /> Original file, exact location, and file-integrity check are retained.</span><span>Fictional data · selected FEMA guidance; DrillLoop is not certified</span></footer>
          </>}
        </div>
      </main>
      {evidenceOpen && <EvidenceModal evidence={evidenceOpen} onClose={() => setEvidenceOpen(null)} />}
      {createOpen && <CreateModal form={newForm} setForm={setNewForm} onClose={() => setCreateOpen(false)} onSubmit={createExercise} busy={busy} />}
      {busy && <div className="busy-indicator"><LoaderCircle size={15} className="spin" /> Saving review workspace…</div>}
    </div>
  )
}

function UsersIcon() { return <span className="users-glyph">◉</span> }

function EmptyState({ onSeed, onCreate }: { onSeed: () => void; onCreate: () => void }) {
  return <div className="empty-workspace"><div className="empty-icon"><Zap size={26} /></div><p className="eyebrow">WELCOME TO DRILLLOOP</p><h1>Turn exercise evidence into verified improvement.</h1><p>Choose the synthetic hospital outage exercise or create an exercise of your own to begin.</p><div className="empty-buttons"><button className="button primary" onClick={onSeed}><Sparkles size={16} /> Load hospital demo</button><button className="button secondary" onClick={onCreate}><Plus size={16} /> Create exercise</button></div><div className="synthetic-tag"><ShieldCheck size={14} /> Fictional training data only</div></div>
}

function Overview({ data, counts, busy, onTab, onEvidence }: { data: Detail; counts: { proposed: number; approved: number; improvement: number }; busy: boolean; onTab: (tab: Tab) => void; onEvidence: (item: Support) => void }) {
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

    {data.timeline_conflicts.length > 0 && <div className="conflict-banner"><div className="conflict-icon"><AlertTriangle size={17} /></div><div><strong>{data.timeline_conflicts.length} timing conflict needs evaluator reconciliation</strong><span>The record shows 09:10; an evaluator note reports 09:11. Both source statements remain visible.</span></div><button onClick={() => onTab('timeline')}>Review conflict <ChevronRight size={14} /></button></div>}

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
        <div className="human-review-note"><ShieldCheck size={15} /><span><strong>Evaluator review required</strong><br />AI drafts are not approved findings until a reviewer confirms them.</span></div>
        <button className="panel-bottom-link" onClick={() => onTab('findings')}>Review all findings <ChevronRight size={15} /></button>
      </section>
    </div>

    <div className="bottom-grid">
      <section className="panel objective-panel"><div className="panel-heading"><div><h2>Exercise objectives</h2><p>Performance criteria agreed before exercise play</p></div><span className="small-count">{data.exercise.objectives.length} objectives</span></div>
        {data.exercise.objectives.map((objective, index) => <div className="objective-row" key={objective.id}><span className="objective-number">0{index + 1}</span><span className="objective-id">{objective.id}</span><p>{objective.text}</p><span className="objective-findings">{data.findings.filter(f => f.objective_id === objective.id).length} findings</span></div>)}
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

function EvidenceView({ data, capabilities, filteredSources, sourceFilter, setSourceFilter, onUpload, onTranscribe }: { data: Detail; capabilities: Capabilities | null; filteredSources: Source[]; sourceFilter: string; setSourceFilter: (value: string) => void; onUpload: (files: FileList | null) => void; onTranscribe: (file?: File) => void }) {
  const [dragging, setDragging] = useState(false)
  const observations = data.timeline
  return <div className="tab-page">
    <div className="section-title-row"><div><h2>Evidence library</h2><p>Every imported record retains its source, location, and integrity hash.</p></div><label className="button primary upload-button"><Upload size={15} /> Add evidence<input type="file" multiple accept=".txt,.md,.csv,.json,.pdf,text/plain,text/csv,application/pdf,application/json" onChange={e => onUpload(e.target.files)} /></label></div>
    <div className={`upload-drop ${dragging ? 'dragging' : ''}`} onDragOver={e => { e.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); onUpload(e.dataTransfer.files) }}>
      <div className="upload-icon"><Upload size={21} /></div><div><strong>Drop exercise notes, logs, or reports here</strong><span>TXT, CSV, JSON transcript, or selectable-text PDF · 15 MB max per file</span></div><label className="button secondary small-button">Browse files<input type="file" multiple accept=".txt,.md,.csv,.json,.pdf" onChange={e => onUpload(e.target.files)} /></label>
    </div>
    <div className="section-header-line"><h3>Imported sources <span className="count-badge">{data.sources.length}</span></h3><div className="search-box"><Search size={14} /><input value={sourceFilter} onChange={e => setSourceFilter(e.target.value)} placeholder="Search sources" /></div></div>
    <div className="source-grid">
      {filteredSources.map(source => <div className="source-card" key={source.id}><div className={`source-type-icon ${source.kind}`}>{source.kind === 'csv' ? <Activity size={18} /> : source.kind === 'transcript' ? <AudioLines size={18} /> : source.kind === 'pdf' ? <FileText size={18} /> : <MessageSquareText size={18} />}</div><div className="source-card-main"><div className="source-name-row"><strong>{source.filename}</strong><span className="source-kind">{source.kind}</span></div><p>{source.observation_count} observations · integrity check {source.sha256.slice(0, 12)}…</p><div className="source-tags"><span><FileCheck2 size={12} /> Imported</span>{source.kind === 'transcript' && <span className="transcript-model">{String(source.provenance.model || 'Transcript')} · {String(source.provenance.language || 'language ?')}</span>}</div></div><button className="icon-button" title="View extracted observations" onClick={() => document.getElementById(`observations-${source.id}`)?.scrollIntoView({ behavior: 'smooth' })}><ChevronRight size={16} /></button></div>)}
      {filteredSources.length === 0 && <div className="empty-card">No evidence source matches that search.</div>}
    </div>
    <div className="section-header-line observations-heading"><div><h3>Extracted observations</h3><p>Text is preserved exactly as imported; timeline normalization is shown separately.</p></div></div>
    <div className="observation-list">{observations.map(obs => <div className="observation-row" key={obs.id} id={`observations-${obs.source_id}`}><div className="observation-time">{shortTime(obs.event_time_normalized)}</div><div className="observation-body"><p>{obs.text}</p><span>{obs.source_filename} · {obs.source_locator}</span></div><span className={`certainty-pill ${obs.time_confidence}`}>{timeLabel(obs.time_confidence)}</span>{obs.recognition_confidence !== null && <span className={`recognition-pill ${obs.recognition_confidence < .75 ? 'low' : ''}`}>Speech-to-text match {Math.round(obs.recognition_confidence * 100)}%</span>}</div>)}</div>
    {data.timeline_conflicts.length > 0 && <div className="conflict-detail"><AlertTriangle size={16} /><div><strong>Conflicting timing note retained</strong>{data.timeline_conflicts.map(item => <p key={item.observation_id}>{item.description} <span>{item.source_filename} · {item.source_locator}</span></p>)}</div></div>}
    <div className="asr-card"><div className="asr-head"><div className="asr-icon"><FileAudio size={19} /></div><div><h3>Offline audio transcription</h3><p>Optional faster-whisper speech-to-text · runs locally · no cloud service</p></div><span className={`asr-state ${capabilities?.asr.available ? 'ready' : 'unavailable'}`}><i />{capabilities?.asr.available ? 'Model ready' : 'Model unavailable'}</span></div><div className="asr-details"><div><span>Software</span><strong>{capabilities?.asr.package_version || 'Not installed'}</strong></div><div><span>Language</span><strong>Detected at runtime</strong></div><div><span>Speaker separation</span><strong>Not provided</strong></div></div><div className="asr-footer"><span>{capabilities?.asr.note || 'Provide a local model directory to enable audio transcription.'}</span><label className={`button secondary small-button ${!capabilities?.asr.available ? 'disabled-look' : ''}`}>Choose audio<input type="file" accept="audio/wav,audio/mpeg,audio/mp4,audio/flac,audio/ogg,.wav,.mp3,.m4a,.flac,.ogg" onChange={e => onTranscribe(e.target.files?.[0])} /></label></div></div>
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

function FindingsView({ data, busy, onReview, onEvidence }: { data: Detail; busy: boolean; onReview: (finding: Finding, decision: 'approved' | 'rejected') => void; onEvidence: (item: Support) => void }) {
  return <div className="tab-page"><div className="section-title-row"><div><h2>Finding review</h2><p>Proposed claims are separated from their interpretation and source evidence.</p></div><div className="review-guard"><LockKeyhole size={14} /> Reviewer authorization required</div></div>
    <div className="finding-review-list">{data.findings.map(finding => <article className="finding-card" key={finding.id}><div className="finding-card-top"><div className={`finding-icon large ${finding.category}`}>{finding.category === 'strength' ? <Check size={17} /> : <AlertTriangle size={16} />}</div><div className="finding-title-block"><div className="finding-kicker">{finding.category === 'strength' ? 'OBSERVED STRENGTH' : 'AREA FOR IMPROVEMENT'} <span>·</span> {finding.code}</div><h3>{finding.title}</h3></div><span className={`status-chip ${finding.status}`}>{finding.status}</span></div>
      <div className="finding-objective"><span>LINKED OBJECTIVE</span><strong>{finding.objective_id || 'Unmapped · reviewer mapping required'}</strong><small>{data.exercise.objectives.find(obj => obj.id === finding.objective_id)?.text || 'No objective mapping available'}</small></div>
      <div className="finding-analysis"><div><span className="analysis-label"><EyeIcon /> Observation</span><p>{finding.observation}</p></div><div><span className="analysis-label"><Sparkles size={13} /> Evaluator interpretation</span><p>{finding.interpretation}</p></div></div>
      <div className="citation-block"><div className="citation-head"><span><FileCheck2 size={14} /> SUPPORTING EVIDENCE</span><span>{finding.supporting_evidence.length} linked record{finding.supporting_evidence.length === 1 ? '' : 's'}</span></div><div className="citation-list">{finding.supporting_evidence.map(item => <button className="citation-row" key={item.observation_id} onClick={() => onEvidence(item)}><span className="citation-file"><FileText size={14} /></span><span><strong>{item.source_filename}</strong><small>{item.source_locator} · “{item.text.slice(0, 180)}”</small></span><ChevronRight size={14} /></button>)}</div></div>
      <div className="finding-card-footer"><div className="finding-confidence"><span className={`confidence-dot ${finding.confidence}`} /> Rule-based match · {finding.confidence} confidence <span className="footer-dot">·</span> {finding.status === 'proposed' ? 'Awaiting evaluator decision' : `${finding.status} by ${finding.reviewer || 'reviewer'}`}</div>{finding.status === 'proposed' && <div className="review-buttons"><button className="button reject" onClick={() => onReview(finding, 'rejected')} disabled={busy}><XCircle size={15} /> Reject</button><button className="button approve" onClick={() => onReview(finding, 'approved')} disabled={busy}><CheckCircle2 size={15} /> Approve finding</button></div>}</div>
      {finding.review_note && <div className="review-note"><strong>Reviewer note:</strong> {finding.review_note}</div>}
    </article>)}
    {data.findings.length === 0 && <div className="empty-card tall"><ShieldCheck size={25} /><h3>No findings prepared yet</h3><p>Import evidence, make sure objectives are present, then run the offline evidence analysis.</p></div>}</div>
    <div className="safety-note"><ShieldCheck size={16} /><span><strong>Human decision stays with the evaluator.</strong> DrillLoop drafts and cites; only an authorized reviewer can approve or reject findings.</span></div>
  </div>
}

function EyeIcon() { return <Search size={13} /> }

function ActionsView({ data, busy, onSave, onReview, onClose }: { data: Detail; busy: boolean; onSave: (action: Action, form: HTMLFormElement) => void; onReview: (action: Action, decision: 'approved' | 'rejected') => void; onClose: (action: Action) => void }) {
  return <div className="tab-page"><div className="section-title-row"><div><h2>Corrective-action register</h2><p>Approval and closure require an authorized reviewer and verifiable completion evidence.</p></div><div className="register-summary"><span>{data.actions.filter(a => a.status !== 'closed').length} open</span><span className="register-sep" /><span>{data.actions.filter(a => a.status === 'closed').length} closed</span></div></div>
    <div className="action-review-list">{data.actions.map(action => <article className={`action-card ${action.owner ? '' : 'owner-gap'}`} key={action.id}><div className="action-card-head"><div className={`action-priority ${action.priority}`}><i />{action.priority}</div><span className="action-linked-finding"><ShieldCheck size={13} /> {action.finding_title}</span><span className={`status-chip ${action.status === 'closed' ? 'approved' : action.status}`}>{action.status.replace('_', ' ')}</span></div>
      <h3>{action.title}</h3><p className="action-support">Linked to {action.evidence_ids.length} source observation{action.evidence_ids.length === 1 ? '' : 's'} and its reviewed finding.</p>
      <form className="action-edit-grid" onSubmit={e => { e.preventDefault(); onSave(action, e.currentTarget) }}>
        <label><span>RESPONSIBLE OWNER / TEAM</span><input name="owner" defaultValue={action.owner || ''} placeholder="Assign a person or team" disabled={action.status === 'closed'} className={!action.owner ? 'missing-input' : ''} /></label>
        <label><span>PRIORITY</span><select name="priority" defaultValue={action.priority} disabled={action.status === 'closed'}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option></select></label>
        <label><span>DUE DATE</span><input name="due_date" type="date" defaultValue={action.due_date || ''} disabled={action.status === 'closed'} /></label>
        <label className="acceptance-label"><span>HOW TO VERIFY COMPLETION</span><textarea name="acceptance_criteria" defaultValue={action.acceptance_criteria} rows={2} disabled={action.status === 'closed'} /></label>
        {action.owner === null && <div className="owner-gap-note"><AlertTriangle size={15} /><span><strong>Owner missing in source register.</strong> This action cannot be approved until an accountable role or team is assigned.</span></div>}
        {action.status !== 'closed' && <div className="action-controls"><button type="submit" className="button secondary" disabled={busy}><Check size={14} /> Save action</button>{action.status === 'proposed' && <><button type="button" className="button reject" onClick={() => onReview(action, 'rejected')} disabled={busy}><XCircle size={14} /> Reject</button><button type="button" className="button approve" onClick={() => onReview(action, 'approved')} disabled={busy || !action.owner || !action.due_date || data.findings.find(f => f.id === action.finding_id)?.status !== 'approved'} title={!action.owner ? 'Assign an owner first' : !action.due_date ? 'Set a due date first' : data.findings.find(f => f.id === action.finding_id)?.status !== 'approved' ? 'Approve linked finding first' : ''}><CheckCircle2 size={14} /> Approve action</button></>}</div>}
      </form>
      {action.status === 'approved' && <div className="closure-row"><span><CheckCircle2 size={16} /> Approved by {action.reviewer || 'reviewer'} · closure evidence required</span><button className="button primary" onClick={() => onClose(action)} disabled={busy}><FileCheck2 size={14} /> Record closure</button></div>}
      {action.status === 'closed' && <div className="closure-record"><CheckCircle2 size={16} /><span><strong>Closed by {action.reviewer || 'reviewer'}</strong><br />{action.closure_evidence}</span></div>}
    </article>)}
      {data.actions.length === 0 && <div className="empty-card tall"><ListChecks size={25} /><h3>No corrective actions</h3><p>Evidence-backed improvement findings will generate proposed actions for review.</p></div>}</div>
    <div className="safety-note"><LockKeyhole size={15} /><span>Reviewer key is required for edits. An action cannot close until an authorized evaluator approves it and records proof that the work is complete.</span></div>
  </div>
}

function EvidenceModal({ evidence, onClose }: { evidence: Support; onClose: () => void }) {
  return <div className="modal-shade" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}><div className="evidence-modal"><div className="modal-head"><div className="modal-file-icon"><FileText size={19} /></div><div><span>ORIGINAL SOURCE EVIDENCE</span><h2>{evidence.source_filename}</h2></div><button className="icon-button" onClick={onClose}><X size={18} /></button></div><div className="source-metadata"><span><strong>Exact location</strong>{evidence.source_locator}</span><span><strong>Event time</strong>{evidence.event_time_normalized ? shortTime(evidence.event_time_normalized) : 'Unresolved'}</span><span><strong>Time quality</strong>{timeLabel(evidence.time_confidence)}</span></div><div className="source-quote"><div className="quote-mark">“</div><p>{evidence.text}</p><span>Exact extracted text · no paraphrase</span></div><div className="modal-footer"><span>Evidence record · {evidence.observation_id.slice(0, 12)}</span><a className="button secondary" href={`/api/sources/${evidence.source_id}/download`}><ArrowDownToLine size={14} /> Download original file</a><button className="button secondary" onClick={onClose}>Close source view</button></div></div></div>
}

type CreateForm = { id: string; title: string; scenario: string; exercise_date: string; duration_minutes: string; objectives: string; evaluator_roles: string; participants: string; milestones: string }
function CreateModal({ form, setForm, onClose, onSubmit, busy }: { form: CreateForm; setForm: React.Dispatch<React.SetStateAction<CreateForm>>; onClose: () => void; onSubmit: () => void; busy: boolean }) {
  const update = (field: keyof typeof form, value: string) => setForm({ ...form, [field]: value })
  return <div className="modal-shade"><div className="create-modal"><div className="modal-head"><div className="modal-file-icon"><Plus size={19} /></div><div><span>EXERCISE SETUP</span><h2>Create an exercise</h2></div><button className="icon-button" onClick={onClose}><X size={18} /></button></div><div className="create-form">
    <div className="form-two"><label><span>EXERCISE ID</span><input value={form.id} onChange={e => update('id', e.target.value)} placeholder="HOSP-PO-2026-02" /></label><label><span>DATE</span><input type="date" value={form.exercise_date} onChange={e => update('exercise_date', e.target.value)} /></label></div>
    <label><span>EXERCISE NAME</span><input value={form.title} onChange={e => update('title', e.target.value)} placeholder="Night shift communications exercise" /></label>
    <label><span>SCENARIO</span><textarea rows={3} value={form.scenario} onChange={e => update('scenario', e.target.value)} placeholder="Describe the simulated situation and scope." /></label>
    <label><span>OBJECTIVES · one per line; prefix with ID: to set an ID</span><textarea rows={4} value={form.objectives} onChange={e => update('objectives', e.target.value)} placeholder={'OBJ-01: Restore essential services within the objective time'} /></label>
    <label><span>EXPECTED MILESTONES · one per line</span><textarea rows={2} value={form.milestones} onChange={e => update('milestones', e.target.value)} placeholder="Generator stable and essential circuits checked" /></label>
    <div className="form-two"><label><span>EVALUATOR ROLES · comma-separated</span><input value={form.evaluator_roles} onChange={e => update('evaluator_roles', e.target.value)} placeholder="Facilities, Clinical" /></label><label><span>PARTICIPANTS / TEAMS · comma-separated</span><input value={form.participants} onChange={e => update('participants', e.target.value)} placeholder="Incident Command, ICU" /></label></div>
    <div className="form-two"><label><span>DURATION · MINUTES</span><input type="number" value={form.duration_minutes} onChange={e => update('duration_minutes', e.target.value)} /></label><div className="form-hint"><HelpCircle size={14} /> Objectives can be added later. Analysis will remain paused until at least one is present.</div></div>
    </div><div className="modal-footer"><span>Exercise data is stored in the configured local database.</span><div><button className="button secondary" onClick={onClose}>Cancel</button><button className="button primary" onClick={onSubmit} disabled={busy || !form.id || !form.title || !form.scenario}><Plus size={14} /> Create exercise</button></div></div></div></div>
}
