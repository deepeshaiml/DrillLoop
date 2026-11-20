import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import {
  candidateError, createOperationKey, type ApiError, type Candidate, type CandidateApi,
  type PromotionFields, type PromotionOperation,
} from './candidateApi'

type Props = {
  api: CandidateApi
  candidate: Candidate
  etag: string
  children: ReactNode
  headingRef: React.RefObject<HTMLHeadingElement | null>
  onClose: () => void
  onReload: (message: string, reviewForbidden?: boolean) => void
  onCreated: () => void
}

export default function CandidatePromotionDialog({ api, candidate, etag, children, headingRef, onClose, onReload, onCreated }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  const descriptionId = useId()
  const titleRef = useRef<HTMLHeadingElement>(null)
  const request = useRef<AbortController | null>(null)
  const operation = useRef<PromotionOperation | null>(null)
  const [busy, setBusy] = useState(false)
  const [retry, setRetry] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    const previousFocus = document.activeElement
    dialog.showModal()
    titleRef.current?.focus()
    return () => {
      request.current?.abort()
      dialog.close()
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus()
      if (document.activeElement === document.body) headingRef.current?.focus()
    }
  }, [headingRef])

  const dismiss = () => {
    if (request.current) return
    if (retry) onReload('Check the reloaded candidate to see whether a finding was created.')
    else onClose()
  }

  const submit = async (form: HTMLFormElement) => {
    if (request.current) return
    if (!operation.current) {
      const values = new FormData(form)
      const fields: PromotionFields = {
        title: String(values.get('title')).trim(),
        observation: String(values.get('observation')).trim(),
        interpretation: String(values.get('interpretation')).trim(),
        category: values.get('category') as PromotionFields['category'],
        objective_id: candidate.objective_id,
        confirmed: true,
      }
      for (const name of ['title', 'observation', 'interpretation'] as const) {
        if (fields[name].length < 4) {
          setError('Enter at least four characters for each finding wording field.')
          ;(form.elements.namedItem(name) as HTMLElement | null)?.focus()
          return
        }
      }
      operation.current = { key: createOperationKey(), etag, fields }
    }
    const controller = new AbortController()
    request.current = controller
    setBusy(true)
    setError('')
    try {
      await api.promote(candidate.exercise_id, candidate.id, operation.current,
        AbortSignal.any([controller.signal, AbortSignal.timeout(15_000)]))
      if (!controller.signal.aborted) onCreated()
    } catch (reason) {
      if (controller.signal.aborted) return
      const { code, status } = reason as ApiError
      if (status === 412) {
        onReload('The candidate changed. Review its latest state and linked finding before taking another action.')
      } else if (status === 428 || (status === 409 && code !== 'FINDING_DUPLICATE')) {
        onReload(candidateError(reason, 'Reload the candidate to check its latest state and version.'))
      } else if (status === 401 || status === 403 || status === 404) {
        onReload(candidateError(reason, 'Promotion access is unavailable.'), status === 403)
      } else {
        const uncertain = !status || status === 408 || status === 429 || status >= 500
        setRetry(uncertain)
        if (!uncertain) operation.current = null
        const message = candidateError(reason, 'The server response could not be confirmed.')
        setError(uncertain ? `${message} Retry the same submission to check its outcome.` : message)
      }
    } finally {
      request.current = null
      if (!controller.signal.aborted) setBusy(false)
    }
  }

  return <dialog ref={dialogRef} className="cr-dialog cr-promotion-dialog" aria-labelledby={titleId} aria-describedby={descriptionId}
    onCancel={event => { event.preventDefault(); dismiss() }}>
    <form onSubmit={event => { event.preventDefault(); void submit(event.currentTarget) }}>
      <header>
        <h4 id={titleId} ref={titleRef} tabIndex={-1}>Create proposed finding</h4>
        <p id={descriptionId}>This creates a proposed finding for separate human review. Approval and corrective actions require separate steps.</p>
        <p>Candidate {candidate.id}</p>
        <p><strong>{candidate.objective_id}</strong> · {candidate.objective_text}</p>
      </header>
      <div className="cr-promotion-context">{children}</div>
      <fieldset disabled={busy || retry}>
        <legend>Proposed finding wording</legend>
        <label>Finding title<input name="title" required minLength={4} maxLength={240} /></label>
        <label>Evidence-based observation<textarea name="observation" required minLength={4} maxLength={4000} rows={3} /></label>
        <label>Interpretation<textarea name="interpretation" required minLength={4} maxLength={4000} rows={3} /></label>
        <label>Category<select name="category" required defaultValue="">
          <option value="" disabled>Choose a category</option>
          <option value="strength">Strength</option>
          <option value="improvement">Improvement</option>
        </select></label>
        <label className="cr-confirm-wording">
          <input name="confirmed" type="checkbox" required />
          <span>I confirm this wording and category for objective <strong>{candidate.objective_id}</strong>. The cited evidence supports the statement, and any unverified times or causes remain uncertain.</span>
        </label>
      </fieldset>
      {error && <p className="cr-warning cr-message" role="alert">{error}</p>}
      <div className="cr-toolbar cr-dialog-actions">
        <button type="button" className="button secondary" aria-disabled={busy} onClick={dismiss}>Cancel</button>
        <button type="submit" className="button primary" aria-disabled={busy}>
          {busy ? 'Creating proposed finding…' : retry ? 'Retry promotion' : 'Confirm proposed finding'}
        </button>
      </div>
      <span className="sr-only" role="status">{busy ? 'Submitting the proposed finding.' : ''}</span>
    </form>
  </dialog>
}
