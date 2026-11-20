import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { AlertTriangle, ArrowLeft, ChevronRight, FileText, History } from 'lucide-react'
import { interpretationLabels, type AiAssistanceProps } from './AiAssistance'
import {
  candidateError, candidateTime, createOperationKey, reviewActions, reviewLabels, staleReasons, transitions,
  type ApiError, type CandidateApi, type CandidateDetail, type CandidateEvent, type ReviewDecision, type ReviewState, type ReviewOperation, type SavedCitation,
} from './candidateApi'

type Props = Pick<AiAssistanceProps, 'api' | 'exerciseId' | 'onEvidence'> & {
  candidateId: string
  canReview: boolean
  onChange: () => void
  onBack: () => void
}

function EvidenceQuotes({ title, citations, historical, onEvidence }: {
  title: string
  citations: SavedCitation[]
  historical: boolean
  onEvidence: Props['onEvidence']
}) {
  if (!citations.length) return null
  return <div className="cr-citations">
    <h5>{title}</h5>
    {citations.map(item => <figure className="cr-citation" key={item.observation_id}>
      <figcaption>
        <FileText size={17} aria-hidden="true" />
        <div>
          <strong>{item.source_filename}</strong>
          <span>{item.source_locator} · Source ID {item.source_id}</span>
        </div>
      </figcaption>
      <blockquote>{item.text}</blockquote>
      {(item.event_time_raw || item.time_confidence === 'uncertain' || item.extraction_method === 'ocr') && <p className="cr-meta">
        {item.event_time_raw && <span>Reported time {item.event_time_raw}</span>}
        {item.time_confidence === 'uncertain' && <span>Source time uncertain</span>}
        {item.extraction_method === 'ocr' && <span>OCR wording and timing require verification against the original page.</span>}
      </p>}
      {!historical && <button className="button secondary" type="button"
        aria-label={`Inspect source ${item.source_filename}, ${item.source_locator}`}
        onClick={() => onEvidence(item)}>Inspect source <ChevronRight size={16} aria-hidden="true" /></button>}
    </figure>)}
  </div>
}

function HistoryEvent({ event }: { event: CandidateEvent }) {
  const title = event.operation === 'ai_candidate_saved' ? 'Candidate saved'
    : event.operation === 'ai_candidate_invalidated' ? 'Evidence invalidated' : reviewLabels[event.new_state]
  return <li>
    <strong>{title}</strong>
    <p className="cr-meta"><span>{event.operation === 'ai_candidate_invalidated' ? 'System' : event.actor}</span>
      <time dateTime={event.timestamp}>{candidateTime(event.timestamp)}</time></p>
    {event.operation === 'ai_candidate_saved' && <p>{reviewLabels[event.new_state]}</p>}
    {event.operation === 'ai_candidate_reviewed' && <>
      <p>From {reviewLabels[event.prior_state]} to {reviewLabels[event.new_state]}</p>
      {event.note && <p className="cr-note">{event.note}</p>}
    </>}
    {event.operation === 'ai_candidate_invalidated' && <>
      <p>From current evidence to stale evidence</p>
      <p>{event.reasons.map(reason => staleReasons[reason] ?? reason).join(' ')}</p>
    </>}
  </li>
}

export default function CandidateDetailView({ api, exerciseId, candidateId, canReview, onEvidence, onChange, onBack }: Props) {
  const headingId = useId()
  const headingRef = useRef<HTMLHeadingElement>(null)
  const request = useRef<AbortController | null>(null)
  const historyRequest = useRef<AbortController | null>(null)
  const [detail, setDetail] = useState<CandidateDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [decision, setDecision] = useState<ReviewDecision | null>(null)
  const [reviewDenied, setReviewDenied] = useState(false)
  const [historyBusy, setHistoryBusy] = useState(false)
  const [historyError, setHistoryError] = useState('')

  const reload = useCallback(async () => {
    request.current?.abort()
    historyRequest.current?.abort()
    const controller = new AbortController()
    const { signal } = controller
    request.current = controller
    setLoading(true)
    setHistoryBusy(false)
    setHistoryError('')
    setError('')
    try {
      const current = await api.detail(exerciseId, candidateId, signal)
      if (!signal.aborted) setDetail(current)
    } catch (reason) {
      if (signal.aborted) return
      const status = (reason as ApiError).status
      if (status === 401 || status === 403 || status === 404) setDetail(null)
      setError(candidateError(reason, 'The candidate could not be loaded. Try again.'))
    } finally {
      if (!signal.aborted) setLoading(false)
    }
  }, [api, exerciseId, candidateId])

  useEffect(() => {
    headingRef.current?.focus()
    void reload()
    return () => {
      request.current?.abort()
      historyRequest.current?.abort()
    }
  }, [reload])

  const loadMoreHistory = async () => {
    const cursor = detail?.candidate.next_history_after_version
    if (!detail || cursor == null || historyRequest.current) return
    const controller = new AbortController()
    const { signal } = controller
    historyRequest.current = controller
    setHistoryBusy(true)
    setHistoryError('')
    try {
      const next = await api.detail(exerciseId, candidateId, signal, cursor)
      if (signal.aborted) return
      if (next.candidate.version !== detail.candidate.version) {
        setNotice('The candidate changed while you were viewing it. Its latest state and history have been reloaded.')
        void reload()
        onChange()
        return
      }
      setDetail({
        ...next,
        candidate: { ...next.candidate, history: [...detail.candidate.history, ...next.candidate.history] },
      })
    } catch (reason) {
      if (signal.aborted) return
      const status = (reason as ApiError).status
      if (status === 401 || status === 403 || status === 404) {
        setDetail(null)
        setError(candidateError(reason, 'Candidate access is unavailable.'))
      } else {
        setHistoryError(candidateError(reason, 'More audit events could not be loaded. Try again.'))
      }
    } finally {
      if (historyRequest.current === controller) historyRequest.current = null
      if (!signal.aborted) setHistoryBusy(false)
    }
  }

  const afterReview = (message: string, reviewForbidden = false) => {
    if (reviewForbidden) setReviewDenied(true)
    setDecision(null)
    setNotice(message)
    void reload()
    onChange()
  }

  const candidate = detail?.candidate
  const historical = candidate?.freshness === 'stale'
  const actions = candidate && detail.etag && canReview && !reviewDenied && !historical && !loading && !error
    ? transitions[candidate.review_state] : []

  return <section className="cr-panel cr-detail" aria-labelledby={headingId}>
    <header className="cr-detail-heading">
      <button type="button" className="button secondary" onClick={onBack}><ArrowLeft size={16} aria-hidden="true" /> Back to saved candidates</button>
      <h3 ref={headingRef} tabIndex={-1} id={headingId}>AI candidate review</h3>
      {candidate && <p className="cr-objective">{candidate.objective_id} · {candidate.objective_text}</p>}
    </header>
    <div role="status">{notice && <p className="cr-message">{notice}</p>}</div>
    {loading && <p role="status" className="cr-empty">Loading candidate and audit history…</p>}
    {error && <div className="cr-message cr-warning">
      <p role="alert">{error}</p>
      <button type="button" className="button secondary" onClick={() => void reload()}>Retry candidate</button>
    </div>}
    {candidate && <>
      {historical && <div className="cr-warning cr-stale">
        <h4><AlertTriangle size={18} aria-hidden="true" /> Evidence is stale</h4>
        <p>The quotations below reflect the saved snapshot. This candidate is read-only.</p>
        {candidate.stale_at && <p>Detected <time dateTime={candidate.stale_at}>{candidateTime(candidate.stale_at)}</time></p>}
        <ul>{candidate.stale_reasons.map(reason => <li key={reason}>{staleReasons[reason] ?? reason}</li>)}</ul>
      </div>}
      <section className="cr-section" aria-label="Original evidence">
        <h4>Original evidence</h4>
        <EvidenceQuotes title={historical ? 'Historical supporting quotations' : 'Supporting quotations'} citations={candidate.evidence} historical={historical} onEvidence={onEvidence} />
        <EvidenceQuotes title={historical ? 'Historical counterevidence' : 'Counterevidence'} citations={candidate.counterevidence} historical={historical} onEvidence={onEvidence} />
      </section>
      <section className="cr-section" aria-label="AI interpretation">
        <h4>AI interpretation</h4>
        <p className="cr-meta">AI-generated · Independent verification required</p>
        <p><strong>{interpretationLabels[candidate.kind]}</strong></p>
        <p>{candidate.interpretation}</p>
      </section>
      <section className="cr-section" aria-label="Uncertainty and missing information">
        <h4>Uncertainty and missing information</h4>
        <div className="cr-warning cr-uncertainty">
          <p>{candidate.uncertainty}</p>
          {candidate.unknowns.length > 0 && <ul>{candidate.unknowns.map((item, index) => <li key={index}>{item}</li>)}</ul>}
          <p>{candidate.review_reason}</p>
        </div>
      </section>
      <section className="cr-section" aria-label="Candidate decision">
        <h4>Candidate decision</h4>
        <CandidateStatus state={candidate.review_state} freshness={candidate.freshness} />
        {candidate.latest_decision
          ? <p>Latest human decision by <strong>{candidate.latest_decision.actor}</strong> · <time dateTime={candidate.latest_decision.timestamp}>{candidateTime(candidate.latest_decision.timestamp)}</time></p>
          : <p>{historical ? 'No human decision was recorded.' : 'Awaiting a decision from an authorized reviewer.'}</p>}
        <p>Acceptance records a decision about this AI candidate. Finding approval remains a separate human decision.</p>
        {(!canReview || reviewDenied) && <p className="cr-meta">Review actions require an administrator or reviewer role.</p>}
        {candidate.review_state === 'rejected' && <p className="cr-meta">Rejection ends review of this candidate.</p>}
        {!detail.etag && canReview && !historical && candidate.review_state !== 'rejected' && <p role="alert" className="cr-warning">The response did not include a review version. Reload before recording a decision.</p>}
        {actions.length > 0 && <div className="cr-toolbar">{actions.map(action => <button type="button" key={action}
          className={`button ${action === 'accepted_for_consideration' ? 'primary' : action === 'rejected' ? 'reject' : 'secondary'}`}
          onClick={() => setDecision(action)}>{reviewActions[action].label}</button>)}</div>}
        {!loading && !error && !detail.etag && canReview && !historical && candidate.review_state !== 'rejected' && <button type="button" className="button secondary" onClick={() => void reload()}>Reload review version</button>}
      </section>
      <section className="cr-section" aria-label="Candidate audit history">
        <h4><History size={18} aria-hidden="true" /> Audit history</h4>
        <ol className="cr-history">{candidate.history.map(event => <HistoryEvent key={event.id} event={event} />)}</ol>
        {historyError && <p className="cr-warning" role="alert">{historyError}</p>}
        {candidate.next_history_after_version != null && <button type="button" className="button secondary"
          aria-disabled={historyBusy || loading} onClick={() => { if (!historyBusy && !loading) void loadMoreHistory() }}>
          {historyBusy ? 'Loading audit events…' : 'Load more audit events'}
        </button>}
      </section>
      <details className="cr-provenance">
        <summary>Generation provenance</summary>
        <dl>
          <dt>Provider</dt><dd>{candidate.provenance.provider}</dd>
          <dt>Model tag</dt><dd>{candidate.provenance.model}</dd>
          {candidate.provenance.model_digest && <><dt>Model digest</dt><dd>{candidate.provenance.model_digest}</dd></>}
          <dt>Generated at</dt><dd><time dateTime={candidate.provenance.generated_at}>{candidateTime(candidate.provenance.generated_at)}</time></dd>
          <dt>Requesting user ID</dt><dd>{candidate.provenance.requested_by_user_id}</dd>
          <dt>Prompt version</dt><dd>{candidate.provenance.prompt_version}</dd>
          <dt>Snapshot schema</dt><dd>{candidate.schema_version}</dd>
          <dt>Validator version</dt><dd>{candidate.provenance.validator_version}</dd>
          <dt>Context version</dt><dd>{candidate.provenance.context_version}</dd>
        </dl>
      </details>
    </>}
    {decision && detail?.etag && <ReviewDialog api={api} exerciseId={exerciseId} candidateId={candidateId}
      decision={decision} etag={detail.etag} headingRef={headingRef} onClose={() => setDecision(null)} onReload={afterReview} />}
  </section>
}

type ReviewProps = {
  api: CandidateApi
  exerciseId: string
  candidateId: string
  decision: ReviewDecision
  etag: string
  headingRef: React.RefObject<HTMLHeadingElement | null>
  onClose: () => void
  onReload: (message: string, reviewForbidden?: boolean) => void
}

function ReviewDialog({ api, exerciseId, candidateId, decision, etag, headingRef, onClose, onReload }: ReviewProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  const meaningId = useId()
  const noteId = useId()
  const validationId = useId()
  const noteRef = useRef<HTMLTextAreaElement>(null)
  const request = useRef<AbortController | null>(null)
  const op = useRef<ReviewOperation | null>(null)
  const [note, setNote] = useState('')
  const [validation, setValidation] = useState('')
  const [error, setError] = useState('')
  const [locked, setLocked] = useState(false)
  const [busy, setBusy] = useState(false)
  const requiresNote = decision === 'more_evidence_required'
  const { label, meaning } = reviewActions[decision]

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    const previousFocus = document.activeElement
    dialog.showModal()
    dialog.querySelector<HTMLElement>('[data-initial-focus]')?.focus()
    return () => {
      request.current?.abort()
      dialog.close()
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus()
      // The old action may be removed by the new state when the dialog closes.
      if (document.activeElement === document.body) headingRef.current?.focus()
    }
  }, [headingRef])

  const dismiss = () => {
    if (request.current) return
    if (locked) onReload('The submission could not be confirmed. The candidate has been reloaded so you can check its recorded decisions.')
    else onClose()
  }

  const submit = async () => {
    if (request.current) return
    if (!op.current && requiresNote && !note.trim()) {
      setValidation('Explain what evidence is needed.')
      noteRef.current?.focus()
      return
    }
    if (!op.current) op.current = { key: createOperationKey(), etag, decision, note: note.trim() || null }
    const controller = new AbortController()
    const { signal } = controller
    request.current = controller
    setBusy(true)
    setError('')
    try {
      await api.review(exerciseId, candidateId, op.current, signal)
      if (!signal.aborted) onReload('Human decision recorded. The latest candidate state and audit history are shown below.')
    } catch (reason) {
      if (signal.aborted) return
      const { code, status } = reason as ApiError
      if (status === 412) {
        onReload('Another reviewer or an evidence update changed this candidate. Review the latest state and history before making a new decision.')
      } else if (code === 'AI_CANDIDATE_STALE' || code === 'INVALID_CANDIDATE_TRANSITION' || code === 'IDEMPOTENCY_CONFLICT') {
        onReload(candidateError(reason, 'The candidate changed. Check its current state before reviewing.'))
      } else if (status === 401 || status === 403 || status === 404) {
        onReload(candidateError(reason, 'Candidate review access is unavailable.'), status === 403)
      } else {
        const uncertain = !status || status === 408 || status === 429 || status >= 500
        setLocked(uncertain)
        if (!uncertain) op.current = null
        setError(candidateError(reason, 'The decision could not be confirmed. Retry to check the same submission.'))
      }
    } finally {
      request.current = null
      if (!signal.aborted) setBusy(false)
    }
  }

  return <dialog ref={dialogRef} className="cr-dialog" aria-labelledby={titleId} aria-describedby={meaningId}
    onCancel={event => { event.preventDefault(); dismiss() }}
    onKeyDown={event => {
      if (event.key !== 'Tab') return
      const first = noteRef.current
      const last = event.currentTarget.querySelector<HTMLButtonElement>('button[type="submit"]')
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last?.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first?.focus()
      }
    }}>
    <form noValidate onSubmit={event => { event.preventDefault(); void submit() }}>
      <header>
        <h4 id={titleId}>{label}</h4>
        <p id={meaningId}>{meaning}</p>
      </header>
      <label htmlFor={noteId}>{requiresNote ? 'What evidence is needed? (required)' : 'Reviewer note (optional)'}</label>
      <textarea ref={noteRef} id={noteId} rows={4} maxLength={3000} value={note} readOnly={busy || locked} required={requiresNote}
        aria-invalid={Boolean(validation)} aria-describedby={validation ? validationId : undefined}
        onChange={event => { setNote(event.target.value); setValidation('') }} />
      {validation && <p id={validationId} className="cr-warning" role="alert">{validation}</p>}
      {error && <p className="cr-warning" role="alert">{error}</p>}
      <div className="cr-toolbar cr-dialog-actions">
        <button type="button" data-initial-focus className="button secondary" aria-disabled={busy} onClick={dismiss}>Cancel</button>
        <button type="submit" className={`button ${decision === 'rejected' ? 'reject' : 'primary'}`} aria-disabled={busy}>
          {busy ? 'Recording decision…' : locked ? 'Retry decision' : 'Confirm decision'}
        </button>
      </div>
      <span className="sr-only" role="status">{busy ? 'Recording your review decision.' : ''}</span>
    </form>
  </dialog>
}

export function CandidateStatus({ state, freshness }: { state: ReviewState; freshness: 'current' | 'stale' }) {
  return <div className="cr-statuses">
    <span className={`cr-status cr-status--${state}`}>{reviewLabels[state]}</span>
    {freshness === 'stale' && <span className="cr-status cr-status--stale">Evidence stale</span>}
  </div>
}
