import type { AiCitation, AiSuggestion } from './AiAssistance'

export type ReviewDecision = 'accepted_for_consideration' | 'rejected' | 'more_evidence_required'
export type ReviewState = 'pending_review' | ReviewDecision
export type Freshness = 'current' | 'stale'

export const reviewLabels: Record<ReviewState, string> = {
  pending_review: 'Pending human review',
  accepted_for_consideration: 'Accepted for consideration',
  rejected: 'Rejected',
  more_evidence_required: 'More evidence required',
}

export const reviewActions: Record<ReviewDecision, { label: string; meaning: string }> = {
  accepted_for_consideration: {
    label: 'Accept for consideration',
    meaning: 'Record that this candidate merits further consideration. Finding approval is a separate human decision.',
  },
  more_evidence_required: {
    label: 'Request more evidence',
    meaning: 'Record what a reviewer needs to verify before making a decision on this candidate.',
  },
  rejected: {
    label: 'Reject candidate',
    meaning: 'End review of this candidate. Its evidence and decision history remain available.',
  },
}

export const transitions: Record<ReviewState, ReviewDecision[]> = {
  pending_review: ['accepted_for_consideration', 'more_evidence_required', 'rejected'],
  accepted_for_consideration: ['more_evidence_required', 'rejected'],
  more_evidence_required: ['accepted_for_consideration', 'rejected'],
  rejected: [],
}

type CandidateSummary = {
  id: string
  exercise_id: string
  organization_id: string
  objective_id: string
  kind: AiSuggestion['kind']
  assessment: AiSuggestion['assessment']
  status: 'proposed'
  review_state: ReviewState
  freshness: Freshness
  stale_at: string | null
  stale_reasons: string[]
  version: number
  created_at: string
  updated_at: string
}

export type CandidateEvent = {
  id: string
  actor: string
  actor_user_id: string | null
  candidate_id: string
  exercise_id: string
  timestamp: string
  version: number
  organization_id: string
  request_id: string | null
} & (
  | { operation: 'ai_candidate_saved'; prior_state: null; new_state: 'pending_review' }
  | { operation: 'ai_candidate_reviewed'; prior_state: ReviewState; new_state: ReviewDecision; note: string | null }
  | { operation: 'ai_candidate_invalidated'; prior_freshness: 'current'; new_freshness: 'stale'; reasons: string[] }
)

export type SavedCitation = AiCitation & {
  source_sha256: string
  observation_fingerprint: string
  recognition_confidence: number | null
  ocr_page: number | null
  ocr_engine: string | null
  ocr_engine_version: string | null
  ocr_language: string | null
}

export type Candidate = CandidateSummary & Pick<AiSuggestion, 'interpretation' | 'unknowns' | 'uncertainty' | 'review_reason'> & {
  objective_text: string
  objective_fingerprint: string
  context_fingerprint: string
  schema_version: number
  evidence: SavedCitation[]
  counterevidence: SavedCitation[]
  provenance: {
    provider: string
    model: string
    model_digest: string | null
    prompt_version: string
    validator_version: string
    context_version: number
    generated_at: string
    requested_by_user_id: string
  }
  reviewer_decision: ReviewDecision | null
  latest_decision: Extract<CandidateEvent, { operation: 'ai_candidate_reviewed' }> | null
  history: CandidateEvent[]
  next_history_after_version: number | null
}

export type AiCandidateQueueEntry = {
  id: string
  reviewState: ReviewState
  freshness: Freshness
  objectiveId: string
  objectiveText: string
  interpretation: string
  evidenceCount: number
  createdAt: string
  requester: string
}

export type CandidateDetail = { candidate: Candidate; etag: string | null }
export type ReviewOperation = { key: string; etag: string; decision: ReviewDecision; note: string | null }
export type ApiRequest = <T>(path: string, options?: RequestInit) => Promise<{ body: T; headers: Headers }>

export function createCandidateApi(request: ApiRequest) {
  const listPath = (exerciseId: string) => `/exercises/${encodeURIComponent(exerciseId)}/ai-candidates`
  const detailPath = (exerciseId: string, candidateId: string) => `${listPath(exerciseId)}/${encodeURIComponent(candidateId)}`

  return {
    async list(exerciseId: string, after: string | null, signal: AbortSignal) {
      const params = new URLSearchParams({ limit: '6' })
      if (after) params.set('after', after)
      return (await request<{ candidates: CandidateSummary[]; next_after: string | null }>(`${listPath(exerciseId)}?${params}`, { signal })).body
    },
    async detail(exerciseId: string, candidateId: string, signal: AbortSignal, afterVersion = 0, limit = 20): Promise<CandidateDetail> {
      const params = new URLSearchParams({ history_after_version: String(afterVersion), history_limit: String(limit) })
      const { body, headers } = await request<Candidate>(`${detailPath(exerciseId, candidateId)}?${params}`, { signal })
      return { candidate: body, etag: headers.get('ETag') }
    },
    async save(exerciseId: string, token: string, key: string, signal: AbortSignal) {
      return (await request<{ id: string; version: number }>(listPath(exerciseId), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
        body: JSON.stringify({ save_token: token }),
        signal,
      })).body
    },
    async review(exerciseId: string, candidateId: string, operation: ReviewOperation, signal: AbortSignal) {
      return (await request<{ id: string; version: number; decision: ReviewDecision }>(`${detailPath(exerciseId, candidateId)}/review`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': operation.key,
          'If-Match': operation.etag,
        },
        body: JSON.stringify({ decision: operation.decision, note: operation.note }),
        signal,
      })).body
    },
  }
}

export type CandidateApi = ReturnType<typeof createCandidateApi>
export type ApiError = Error & { status?: number; code?: string }

export function candidateError(error: unknown, fallback: string) {
  const err = error instanceof Error ? error as ApiError : null
  if (err?.status === 401) return 'Your session ended. Sign in again to continue.'
  if (err?.status === 403 || err?.status === 404) return 'This candidate or exercise is unavailable to your account.'
  return err?.status ? err.message : fallback
}

export function candidateTime(value: string) {
  // SQLite returns timestamps without an offset even though the server stores them in UTC.
  const date = new Date(/(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}Z`)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(undefined, {
    dateStyle: 'medium', timeStyle: 'medium',
  })
}

export const staleReasons: Record<string, string> = {
  validator_changed: 'The source validation rules changed.',
  objective_changed: 'The exercise objective changed or was removed.',
  source_unavailable: 'A cited original file changed or is unavailable.',
  citation_invalid: 'A cited observation changed or is unavailable.',
  context_changed: 'The exercise evidence or evaluation context changed.',
}

// getRandomValues is available on local HTTP origins where randomUUID may be unavailable.
export function createOperationKey() {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, '0')).join('')
}
