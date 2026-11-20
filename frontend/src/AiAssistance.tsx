import { useEffect, useRef, useState } from 'react'
import { Bookmark, ChevronRight, FileText, LoaderCircle, Sparkles } from 'lucide-react'

export type AiCapability = {
  state: 'disabled' | 'enabled' | 'misconfigured'
  provider: string | null
  model: string | null
}
export type AiCitation = {
  observation_id: string
  source_id: string
  source_filename: string
  source_locator: string
  text: string
  extraction_method: string
  time_confidence: string
  event_time_raw: string | null
}
import { candidateError, createOperationKey, reviewLabels, type ApiError, type CandidateApi, type CandidateDetail } from './candidateApi'

export const interpretationLabels = {
  relevant_observation: 'Relevant observation',
  corroboration: 'Possible corroboration',
  contradiction: 'Possible contradiction',
  different_response_phases: 'Different response phases',
  unknown: 'Uncertain relationship or outcome',
  insufficient_evidence: 'Insufficient evidence',
} as const

export type AiSuggestion = {
  objective_id: string
  kind: keyof typeof interpretationLabels
  assessment: 'advisory' | 'abstained'
  evidence: AiCitation[]
  counterevidence: AiCitation[]
  interpretation: string
  unknowns: string[]
  uncertainty: string
  review_reason: string
  save_token: string | null
}
export type AiResult = {
  suggestions: AiSuggestion[]
  unassessed_objective_ids: string[]
  rejected_suggestion_count: number
  context_limited: boolean
}
export type AiAssistanceProps = {
  capability: AiCapability
  objectives: { id: string; text: string }[]
  assessments: { objective_id: string | null; unknowns: string[]; conflicts: string[] }[]
  generate: (signal: AbortSignal) => Promise<AiResult>
  onEvidence: (item: AiCitation) => void
  exerciseId: string
  api: CandidateApi
  onSaved: () => void
  onOpen: (candidateId: string) => void
  onQueue: () => void
}

function AiCitations({ title, citations, onEvidence }: {
  title: string
  citations: AiCitation[]
  onEvidence: AiAssistanceProps['onEvidence']
}) {
  if (!citations.length) return null
  return <section className="fa-ai-citations">
    <h4>{title}</h4>
    <div className="fa-evidence-list">
      {citations.map(item => <button className="fa-evidence-link" type="button" key={item.observation_id} onClick={() => onEvidence(item)}>
        <span className="fa-evidence-file"><FileText size={17} /></span>
        <span className="fa-evidence-copy">
          <strong>{item.source_filename}</strong>
          <small>{item.source_locator}{item.extraction_method === 'ocr' ? ' · OCR' : ''}{item.event_time_raw && ` · Reported time ${item.event_time_raw}`}{item.time_confidence === 'uncertain' ? ' · Source time uncertain' : ''}</small>
          <q>{item.text}</q>
        </span>
        <ChevronRight size={17} className="fa-evidence-chevron" />
      </button>)}
    </div>
  </section>
}

export default function AiAssistance({ capability, objectives, assessments, generate, onEvidence, exerciseId, api, onSaved, onOpen, onQueue }: AiAssistanceProps) {
  const [result, setResult] = useState<AiResult | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const request = useRef<AbortController | null>(null)
  const ruleConflicts = assessments.filter(item => item.conflicts.length > 0)
  useEffect(() => () => request.current?.abort(), [])

  const run = async () => {
    if (request.current) return
    const controller = new AbortController()
    request.current = controller
    setPending(true)
    setResult(null)
    setError('')
    try {
      const answer = await generate(controller.signal)
      if (!controller.signal.aborted) setResult(answer)
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(err instanceof Error ? err.message : 'AI assistance is unavailable.')
      }
    } finally {
      request.current = null
      if (!controller.signal.aborted) setPending(false)
    }
  }

  return <section className="fa-ai" aria-label="AI assistance" aria-busy={pending}>
    <div className="fa-ai-header">
      <div>
        <h3><Sparkles size={17} /> AI assistance</h3>
        {capability.state === 'enabled' && <p>AI-generated suggestions — not reviewed or approved.</p>}
        {capability.state === 'disabled' && <p>AI assistance is disabled for this workspace.</p>}
        {capability.state === 'misconfigured' && <p>The local AI configuration is unavailable.</p>}
        {capability.model && <small>{capability.provider === 'ollama' ? 'Ollama' : capability.provider} · {capability.model}</small>}
      </div>
      <div className="cr-toolbar"><button className="button secondary" type="button" onClick={onQueue}><Bookmark size={16} /> Saved candidates</button>
      {capability.state === 'enabled' && <button className="button secondary" type="button" disabled={pending} onClick={() => void run()}>
        {pending ? <LoaderCircle size={16} className="spin" /> : <Sparkles size={16} />}
        {pending ? 'Generating suggestions…' : 'Generate AI suggestions'}
      </button>}</div>
    </div>
    {pending && <p role="status">Reviewing extracted observations with the local model…</p>}
    {error && <p className="fa-uncertainty needs-attention" role="alert">{error}</p>}
    {result && <div className="fa-ai-results">
      {result.rejected_suggestion_count > 0 && <p role="status">{result.rejected_suggestion_count} AI {result.rejected_suggestion_count === 1 ? 'result was' : 'results were'} withheld because validation failed.</p>}
      {result.context_limited
        ? <p role="status">AI abstained because the complete evidence exceeds the review limit.</p>
        : result.suggestions.length === 0 && <p>No AI suggestions are available.</p>}
      {!result.context_limited && result.unassessed_objective_ids.length > 0 && <p>AI review incomplete for {result.unassessed_objective_ids.join(', ')}.</p>}
      {ruleConflicts.length > 0 && <section className="fa-uncertainty needs-attention">
        <h4>Conflicts from deterministic analysis</h4>
        <ul>{ruleConflicts.flatMap(item => item.conflicts.map(value => <li key={`${item.objective_id}-${value}`}>{item.objective_id && <strong>{item.objective_id} · </strong>}{value}</li>))}</ul>
      </section>}
      {result.suggestions.map(item => {
        const objective = objectives.find(value => value.id === item.objective_id)
        const assessment = assessments.find(value => value.objective_id === item.objective_id)
        const deterministicNotes = assessment?.unknowns ?? []
        const evidenceTitle = item.kind === 'corroboration' ? 'Potentially corroborating records'
          : item.kind === 'contradiction' ? 'First account'
          : item.kind === 'different_response_phases' ? 'Records from different stages'
          : item.assessment === 'abstained' ? 'Relevant excerpts' : 'Supporting excerpts'
        return <article className="fa-analysis-card fa-ai-result" key={item.objective_id}>
          <h3>{item.objective_id}{objective && ` · ${objective.text}`}</h3>
          <AiCitations title={evidenceTitle} citations={item.evidence} onEvidence={onEvidence} />
          <AiCitations title="Potentially contradictory account" citations={item.counterevidence} onEvidence={onEvidence} />
          <h4>{interpretationLabels[item.kind]}</h4>
          <p>{item.interpretation}</p>
          <section className="fa-uncertainty needs-attention">
            <h4>Uncertainty and missing information</h4>
            <p>{item.uncertainty}</p>
            {item.unknowns.length > 0 && <ul>{item.unknowns.map(value => <li key={value}>{value}</li>)}</ul>}
            <p>{item.review_reason}</p>
          </section>
          {item.save_token && <SaveSuggestion token={item.save_token} exerciseId={exerciseId} api={api} onSaved={onSaved} onOpen={onOpen} />}
          {deterministicNotes.length > 0 && <section className="fa-ai-citations">
            <h4>Deterministic assessment notes</h4>
            <ul>{Array.from(new Set(deterministicNotes)).map(value => <li key={value}>{value}</li>)}</ul>
          </section>}
        </article>
      })}
    </div>}
  </section>
}

function SaveSuggestion({ token, exerciseId, api, onSaved, onOpen }: Pick<AiAssistanceProps, 'exerciseId' | 'api' | 'onSaved' | 'onOpen'> & { token: string }) {
  const idempotencyKey = useRef<string | null>(null)
  const request = useRef<AbortController | null>(null)
  const savedId = useRef<string | null>(null)
  const [candidateId, setCandidateId] = useState<string | null>(null)
  const [detail, setDetail] = useState<CandidateDetail | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [blocked, setBlocked] = useState(false)

  useEffect(() => () => request.current?.abort(), [])

  const save = async () => {
    if (request.current || blocked) return
    const controller = new AbortController()
    const { signal } = controller
    request.current = controller
    setBusy(true)
    setError('')
    try {
      if (!savedId.current) {
        idempotencyKey.current ??= createOperationKey()
        const result = await api.save(exerciseId, token, idempotencyKey.current, signal)
        if (signal.aborted) return
        savedId.current = result.id
        setCandidateId(result.id)
        onSaved()
      }
      const current = await api.detail(exerciseId, savedId.current, signal, 0, 1)
      if (!signal.aborted) setDetail(current)
    } catch (reason) {
      if (signal.aborted) return
      const failure = reason as ApiError
      const regenerate = ['AI_SAVE_TOKEN_EXPIRED', 'AI_SAVE_TOKEN_INVALID', 'AI_CITATIONS_INVALID', 'AI_CONTEXT_CHANGED', 'AI_SOURCE_UNAVAILABLE'].includes(failure.code ?? '')
      const noAccess = failure.status === 401 || failure.status === 403 || failure.status === 404
      setBlocked(regenerate || noAccess || failure.code === 'IDEMPOTENCY_CONFLICT')
      setError(regenerate
        ? failure.code === 'AI_SAVE_TOKEN_EXPIRED'
          ? 'This save token expired. Generate AI suggestions again.'
          : failure.code === 'AI_CONTEXT_CHANGED' || failure.code === 'AI_SOURCE_UNAVAILABLE'
            ? 'Evidence or objectives changed. Generate AI suggestions again using the current exercise.'
            : 'This suggestion is no longer eligible. Generate AI suggestions again.'
        : candidateError(reason, savedId.current ? 'Candidate saved. Its current state could not be loaded.' : 'The save could not be confirmed. Retry this save.'))
    } finally {
      request.current = null
      if (!signal.aborted) setBusy(false)
    }
  }

  return <div className="cr-save">
    <div className="cr-toolbar">
      {candidateId
        ? <button type="button" className="button secondary" onClick={() => onOpen(candidateId)}>Open saved candidate <ChevronRight size={16} /></button>
        : <button type="button" className="button primary" disabled={busy || blocked} onClick={() => void save()}>
          <Bookmark size={16} /> {busy ? 'Saving candidate…' : error && !blocked ? 'Retry save' : 'Save for review'}
        </button>}
      {candidateId && error && !blocked && <button type="button" className="button secondary" disabled={busy} onClick={() => void save()}>Reload saved status</button>}
      {candidateId && <span role="status">{detail
        ? `Saved for review · ${reviewLabels[detail.candidate.review_state]}${detail.candidate.freshness === 'stale' ? ' · Evidence stale' : ''}`
        : 'Candidate saved for review.'}</span>}
    </div>
    {error && <p role="alert" className="cr-warning">{error}</p>}
  </div>
}
