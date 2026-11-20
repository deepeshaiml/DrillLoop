import { useEffect, useId, useRef, useState } from 'react'
import { ArrowLeft, Bookmark, ChevronRight } from 'lucide-react'
import AiAssistance, { type AiAssistanceProps } from './AiAssistance'
import CandidateDetailView, { CandidateStatus } from './CandidateDetailView'
import { candidateError, candidateTime, reviewLabels, type AiCandidateQueueEntry, type ApiError, type ReviewState } from './candidateApi'

type WorkspaceProps = Omit<AiAssistanceProps, 'capability' | 'onSaved' | 'onOpen' | 'onQueue'> & {
  capability?: AiAssistanceProps['capability']
  canReview: boolean
  selected: string | null
  setSelected: (id: string | null) => void
  onFindingCreated: () => Promise<void>
  onOpenFinding: (id: string) => Promise<void>
}

export default function AiCandidateWorkspace({
  capability, canReview, selected, setSelected, onFindingCreated, onOpenFinding, ...props
}: WorkspaceProps) {
  const [revision, setRevision] = useState(0)
  const queueHeading = useRef<HTMLHeadingElement>(null)
  const opener = useRef<HTMLElement | null>(null)
  const returnFocus = useRef(false)
  const refreshQueue = () => setRevision(value => value + 1)

  const openCandidate = (candidateId: string) => {
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    setSelected(candidateId)
  }

  useEffect(() => {
    if (selected || !returnFocus.current) return
    returnFocus.current = false
    const previous = opener.current
    if (previous?.isConnected) previous.focus()
    opener.current = null
    if (document.activeElement !== previous) queueHeading.current?.focus()
  }, [selected])

  return <div className="cr-workspace">
    <div hidden={selected !== null}>
      {capability && <AiAssistance {...props} capability={capability} onSaved={refreshQueue} onOpen={openCandidate}
        onQueue={() => queueHeading.current?.focus()} />}
      <CandidateQueue api={props.api} exerciseId={props.exerciseId} revision={revision}
        headingRef={queueHeading} onOpen={openCandidate} />
    </div>
    {selected && <CandidateDetailView key={selected} candidateId={selected} api={props.api}
      exerciseId={props.exerciseId} canReview={canReview}
      onEvidence={props.onEvidence} onChange={refreshQueue} onFindingCreated={onFindingCreated} onOpenFinding={onOpenFinding} onBack={() => {
        returnFocus.current = true
        refreshQueue()
        setSelected(null)
      }} />}
  </div>
}

type QueueProps = Pick<WorkspaceProps, 'api' | 'exerciseId'> & {
  revision: number
  headingRef: React.RefObject<HTMLHeadingElement | null>
  onOpen: (candidateId: string) => void
}

type QueuePage = { after: string | null; rows: AiCandidateQueueEntry[]; next: string | null }
type QueueRequest = { status: 'loading' } | { status: 'loaded'; page: QueuePage } | { status: 'error'; message: string; noAccess: boolean }

function CandidateQueue({ api, exerciseId, revision, headingRef, onOpen }: QueueProps) {
  const headingId = useId()
  const [cursors, setCursors] = useState<(string | null)[]>([null])
  const [filter, setFilter] = useState<'all' | 'stale' | ReviewState>('all')
  const [request, setRequest] = useState<QueueRequest>({ status: 'loading' })
  const [retry, setRetry] = useState(0)
  const after = cursors[cursors.length - 1]

  useEffect(() => {
    const controller = new AbortController()
    const { signal } = controller
    const load = async () => {
      setRequest(previous => previous.status === 'loaded' && previous.page.after === after ? previous : { status: 'loading' })
      try {
        const page = await api.list(exerciseId, after, signal)
        // The list supplies state and cursors. Read the saved snapshot and creation event
        // for each item on this bounded page to display interpretation and requester.
        const rows = await Promise.all(page.candidates.map(async ({ id }) => {
          const { candidate } = await api.detail(exerciseId, id, signal, 0, 1)
          return {
            id: candidate.id,
            reviewState: candidate.review_state,
            freshness: candidate.freshness,
            promoted: candidate.promoted,
            objectiveId: candidate.objective_id,
            objectiveText: candidate.objective_text,
            interpretation: candidate.interpretation,
            evidenceCount: candidate.evidence.length,
            createdAt: candidate.created_at,
            requester: candidate.history.find(event => event.operation === 'ai_candidate_saved')?.actor ?? candidate.provenance.requested_by_user_id,
          }
        }))
        if (!signal.aborted) setRequest({ status: 'loaded', page: { after, rows, next: page.next_after } })
      } catch (error) {
        if (signal.aborted) return
        const { status } = error as ApiError
        setRequest({
          status: 'error',
          message: candidateError(error, 'Saved candidates could not be loaded. Try again.'),
          noAccess: status === 401 || status === 403 || status === 404,
        })
      }
    }
    void load()
    return () => controller.abort()
  }, [api, exerciseId, after, revision, retry])

  const page = request.status === 'loaded' && request.page.after === after ? request.page : null
  const rows = page?.rows.filter(row => filter === 'all' || (filter === 'stale' ? row.freshness === 'stale' : row.reviewState === filter)) ?? []

  const navigate = (nextCursors: (string | null)[]) => {
    headingRef.current?.focus()
    setCursors(nextCursors)
  }

  return <section className="cr-panel" aria-labelledby={headingId}>
    <header className="cr-heading">
      <div className="cr-heading-copy">
        <span className="cr-heading-icon"><Bookmark size={19} aria-hidden="true" /></span>
        <div>
          <h3 ref={headingRef} tabIndex={-1} id={headingId}>Saved AI candidates</h3>
          <p>Review the source evidence and record a decision about the candidate.</p>
        </div>
      </div>
      {page && (page.rows.length > 0 || after) && <label className="cr-filter">Status on this page
        <select value={filter} onChange={event => setFilter(event.target.value as typeof filter)}>
          <option value="all">All statuses</option>
          {Object.entries(reviewLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
          <option value="stale">Evidence stale</option>
        </select>
      </label>}
    </header>
    {(request.status === 'loading' || (request.status === 'loaded' && !page)) && <p className="cr-empty" role="status">Loading saved candidates…</p>}
    {request.status === 'error' && <div className="cr-message cr-warning">
      <p role="alert"><strong>{request.noAccess ? 'Candidate access unavailable. ' : 'Candidate queue unavailable. '}</strong>{request.message}</p>
      <button type="button" className="button secondary" onClick={() => { headingRef.current?.focus(); setRetry(value => value + 1) }}>Retry queue</button>
    </div>}
    {page && <>
      {rows.length ? <>
        <p className="sr-only" role="status">{rows.length} {rows.length === 1 ? 'candidate' : 'candidates'} shown.</p>
        <ul className="cr-queue-list">{rows.map(row => <li key={row.id} className="cr-queue-row">
          <div className="cr-row-content">
            <p className="cr-objective">{row.objectiveId} · {row.objectiveText}</p>
            <p className="cr-summary">{row.interpretation}</p>
            <p className="cr-meta" id={`candidate-meta-${row.id}`}>
              <span>{row.evidenceCount} supporting {row.evidenceCount === 1 ? 'reference' : 'references'}</span>
              <time dateTime={row.createdAt}>{candidateTime(row.createdAt)}</time>
              <span>Requested by {row.requester}</span>
            </p>
          </div>
          <div className="cr-row-controls">
            <CandidateStatus state={row.reviewState} freshness={row.freshness} promoted={row.promoted} />
            <button type="button" className="button secondary" aria-label={`Open candidate for ${row.objectiveId}`} aria-describedby={`candidate-meta-${row.id}`}
              onClick={() => onOpen(row.id)}>Open candidate <ChevronRight size={16} aria-hidden="true" /></button>
          </div>
        </li>)}</ul>
      </> : <p className="cr-empty" role="status">{page.rows.length > 0
        ? 'No candidates on this page match the selected status.'
        : 'No saved AI candidates. Eligible suggestions can be saved explicitly from AI assistance.'}</p>}
      {(cursors.length > 1 || page.next) && <nav className="cr-pagination" aria-label="Candidate queue pages">
        <button type="button" className="button secondary" disabled={cursors.length === 1}
          onClick={() => navigate(cursors.slice(0, -1))}><ArrowLeft size={16} aria-hidden="true" /> Previous</button>
        <span>Page {cursors.length}</span>
        <button type="button" className="button secondary" disabled={!page.next}
          onClick={() => navigate([...cursors, page.next])}>Next <ChevronRight size={16} aria-hidden="true" /></button>
      </nav>}
    </>}
  </section>
}
