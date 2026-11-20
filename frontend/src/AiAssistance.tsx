import { useEffect, useRef, useState } from 'react'
import { ChevronRight, FileText, LoaderCircle, Sparkles } from 'lucide-react'

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
const interpretationLabels = {
  relevant_observation: 'Relevant observation',
  corroboration: 'Possible corroboration',
  contradiction: 'Possible contradiction',
  different_response_phases: 'Different response phases',
  unknown: 'Uncertain relationship or outcome',
  insufficient_evidence: 'Insufficient evidence',
} as const

type Suggestion = {
  objective_id: string
  kind: keyof typeof interpretationLabels
  assessment: 'advisory' | 'abstained'
  evidence: AiCitation[]
  counterevidence: AiCitation[]
  interpretation: string
  unknowns: string[]
  uncertainty: string
  review_reason: string
}
export type AiResult = {
  suggestions: Suggestion[]
  unassessed_objective_ids: string[]
  rejected_suggestion_count: number
  context_limited: boolean
}
type Props = {
  capability: AiCapability
  objectives: { id: string; text: string }[]
  assessments: { objective_id: string | null; unknowns: string[]; conflicts: string[] }[]
  generate: (signal: AbortSignal) => Promise<AiResult>
  onEvidence: (item: AiCitation) => void
}

function AiCitations({ title, citations, onEvidence }: {
  title: string
  citations: AiCitation[]
  onEvidence: Props['onEvidence']
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

export default function AiAssistance({ capability, objectives, assessments, generate, onEvidence }: Props) {
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
      {capability.state === 'enabled' && <button className="button secondary" type="button" disabled={pending} onClick={() => void run()}>
        {pending ? <LoaderCircle size={16} className="spin" /> : <Sparkles size={16} />}
        {pending ? 'Generating suggestions…' : 'Generate AI suggestions'}
      </button>}
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
          {deterministicNotes.length > 0 && <section className="fa-ai-citations">
            <h4>Deterministic assessment notes</h4>
            <ul>{Array.from(new Set(deterministicNotes)).map(value => <li key={value}>{value}</li>)}</ul>
          </section>}
        </article>
      })}
    </div>}
  </section>
}
