import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { resolve } from 'node:path'
import { chromium } from 'playwright'

const baseURL = process.env.DRILLLOOP_E2E_BASE_URL
const password = process.env.DRILLLOOP_CANDIDATE_E2E_PASSWORD
const screenshots = process.env.DRILLLOOP_CANDIDATE_E2E_SCREENSHOTS
const axeScript = process.env.DRILLLOOP_CANDIDATE_E2E_AXE
const mode = process.argv[2]
assert.ok(baseURL && password && screenshots && ['review', 'ai-disabled'].includes(mode), 'Use run_candidate_review.py with its disposable fixture.')
const exerciseId = 'FICTIONAL-CANDIDATE-REVIEW'
const exerciseTitle = 'Fictional dispatch handoff exercise'
const exercisePath = `/api/exercises/${exerciseId}`
const candidatePath = `${exercisePath}/ai-candidates`
const otherExerciseId = 'FICTIONAL-OTHER-EXERCISE'
const otherPath = `/api/exercises/${otherExerciseId}`
const filename = 'fictional_dispatch_notebook.txt'
const wording = 'No matching handoff entry was found in the fictional dispatch notebook.'
const objectives = [
  { id: 'OBJ-ACCEPT', text: 'Verify the signed dispatch handoff log.' },
  { id: 'OBJ-REJECT', text: 'Confirm who received the handoff.' },
  { id: 'OBJ-MORE', text: 'Document the missing handoff entry.' },
  { id: 'OBJ-CONFLICT', text: 'Resolve the dispatch handoff record.' },
  { id: 'OBJ-UNSOURCED', text: 'Identify the unavailable dispatch register.' },
]
const browser = await chromium.launch()
const errors = []
const axeResults = []

async function signIn(user) {
  const page = await browser.newPage({ baseURL, viewport: { width: 1440, height: 1050 }, hasTouch: true })
  page.setDefaultTimeout(12_000)
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/')
  await page.getByLabel('Username').fill(`candidate-${user}`)
  await page.locator('input[autocomplete=current-password]').fill(password)
  const login = page.waitForResponse(response => response.url().endsWith('/api/auth/login'))
  await page.getByRole('button', { name: 'Sign in' }).click()
  const response = await login
  assert.equal(response.status(), 200)
  return { page, headers: { 'X-CSRF-Token': (await response.json()).csrf_token } }
}

async function api(session, path, status, options = {}) {
  const { page, headers } = session
  const response = await page.request.fetch(path, { ...options, headers: { ...headers, ...options.headers } })
  assert.equal(response.status(), status, `${options.method || 'GET'} ${path}`)
  return { body: await response.json(), headers: response.headers() }
}

async function openFindings(page) {
  await page.locator('#exercise-picker').selectOption(exerciseId)
  await page.getByRole('heading', { name: exerciseTitle, exact: true }).waitFor()
  await page.getByRole('navigation', { name: 'Exercise sections' }).getByRole('button', { name: /^Findings/ }).click()
}

const queue = page => page.getByRole('region', { name: 'Saved AI candidates' })
const candidate = page => page.getByRole('region', { name: 'AI candidate review' })
const audit = page => candidate(page).getByRole('region', { name: 'Candidate audit history' })
const decisionPanel = page => candidate(page).getByRole('region', { name: 'Candidate decision' })
const queueButton = (page, id) => queue(page).getByRole('button', { name: `Open candidate for ${id}`, exact: true })
const suggestionCard = (page, id) => page.getByRole('region', { name: 'AI assistance' }).getByRole('article')
  .filter({ has: page.getByRole('heading', { name: new RegExp(`^${id} ·`) }) })

async function capture(page, width, name, target) {
  await page.setViewportSize({ width, height: width < 800 ? 850 : 1050 })
  if (target) await target.scrollIntoViewIfNeeded()
  const metrics = await page.evaluate(() => ({
    document: document.documentElement.scrollWidth,
    viewport: window.innerWidth,
    keyControls: [...document.querySelectorAll('.cr-workspace button, .cr-workspace select, .cr-workspace summary')]
      .filter(element => element.getClientRects().length > 0)
      .map(element => Math.round(element.getBoundingClientRect().height)),
  }))
  assert.ok(metrics.document <= metrics.viewport, `Horizontal overflow at ${width}px in ${name}`)
  assert.ok(metrics.keyControls.every(height => height >= 44), `Touch targets in ${name}: ${metrics.keyControls}`)
  const activeDialog = page.locator('.cr-dialog[open]')
  if (await activeDialog.count()) {
    const bounds = await activeDialog.boundingBox()
    assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= width)
    assert.ok(bounds.y >= 0 && bounds.y + bounds.height <= (width < 800 ? 850 : 1050))
  }
  const path = resolve(screenshots, `${width}-${name}.png`)
  if (await activeDialog.count()) {
    await page.screenshot({ path })
  } else if (name.includes('queue') || name === 'eligible-suggestion') {
    await target.screenshot({ path })
  } else {
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }))
    await page.screenshot({ path, fullPage: true })
  }
}

async function checkAxe(page, selector, label) {
  if (!axeScript) return
  if (!await page.evaluate(() => Boolean(window.axe))) await page.addScriptTag({ path: axeScript })
  const violations = await page.evaluate(async selector => {
    const result = await window.axe.run(selector, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] },
    })
    return result.violations.map(({ id, nodes }) => ({ id, nodes: nodes.map(node => node.target) }))
  }, selector)
  assert.deepEqual(violations, [], `axe violations in ${label}`)
  axeResults.push(label)
}

async function openCandidate(page, objectiveId) {
  const trigger = queueButton(page, objectiveId)
  await trigger.click()
  await candidate(page).getByRole('heading', { name: 'Original evidence' }).waitFor()
  assert.ok(await candidate(page).getByRole('heading', { name: 'AI candidate review' })
    .evaluate(element => document.activeElement === element), 'Opening the detail focuses its heading')
  return candidate(page)
}

async function backToQueue(page) {
  await candidate(page).getByRole('button', { name: 'Back to saved candidates' }).click()
  await queue(page).waitFor()
}

async function generate(page) {
  const generation = page.waitForResponse(response => response.url().endsWith('/ai-suggestions'))
  await page.getByRole('button', { name: 'Generate AI suggestions' }).click()
  const response = await generation
  assert.equal(response.status(), 200)
  const result = await response.json()
  assert.equal(result.model, 'fictional-provider:test')
  return result
}

async function beginReview(page, label) {
  const trigger = decisionPanel(page).getByRole('button', { name: label, exact: true })
  await trigger.click()
  const dialog = page.getByRole('dialog', { name: label, exact: true })
  await dialog.waitFor()
  assert.ok(await dialog.getByRole('button', { name: 'Cancel' }).evaluate(element => document.activeElement === element))
  return { dialog, trigger }
}

async function confirm(page, dialog, status, etag, buttonLabel = 'Confirm decision') {
  const result = page.waitForResponse(response => response.url().endsWith('/review') && response.request().method() === 'POST')
  await dialog.getByRole('button', { name: buttonLabel, exact: true }).click()
  const response = await result
  assert.equal(response.status(), status)
  const headers = await response.request().allHeaders()
  assert.equal(headers['if-match'], etag)
  assert.match(headers['idempotency-key'], /^[A-Za-z0-9._:-]{1,128}$/)
  await dialog.waitFor({ state: 'detached' })
  return response
}

async function reviewJourney() {
  const admin = await signIn('admin')
  const { page } = admin
  await api(admin, '/api/exercises', 201, {
    method: 'POST', data: {
      id: exerciseId, title: exerciseTitle, scenario: 'Fictional evidence for this candidate review test.',
      exercise_date: '2026-11-20', duration_minutes: 20, objectives,
    },
  })
  await api(admin, '/api/exercises', 201, {
    method: 'POST', data: {
      id: otherExerciseId, title: 'Fictional separate exercise', scenario: 'Fictional unrelated access fixture.',
      exercise_date: '2026-11-20', duration_minutes: 20, objectives: [objectives[0]],
    },
  })
  await api(admin, `${exercisePath}/evidence`, 201, {
    method: 'POST', multipart: { files: { name: filename, mimeType: 'text/plain', buffer: Buffer.from(wording) } },
  })
  for (const user of ['reviewer', 'viewer', 'evaluator']) {
    await api(admin, `${exercisePath}/access`, 201, { method: 'POST', data: { user_id: `candidate-${user}` } })
  }
  await page.reload()
  await openFindings(page)
  await queue(page).getByText(/No saved AI candidates/).waitFor()
  const generated = await generate(page)
  assert.equal(generated.suggestions.filter(item => item.save_token).length, 4)
  assert.equal(generated.suggestions.find(item => item.objective_id === 'OBJ-UNSOURCED').save_token, null)
  assert.deepEqual((await api(admin, candidatePath, 200)).body.candidates, [])
  assert.equal(await suggestionCard(page, 'OBJ-UNSOURCED').getByRole('button', { name: 'Save for review' }).count(), 0)
  await capture(page, 1440, 'eligible-suggestion', suggestionCard(page, 'OBJ-ACCEPT'))
  await checkAxe(page, '.fa-ai', 'eligible suggestion')

  const saved = {}
  for (const id of ['OBJ-ACCEPT', 'OBJ-REJECT', 'OBJ-MORE', 'OBJ-CONFLICT']) {
    const card = suggestionCard(page, id)
    let failedSave
    if (id === 'OBJ-ACCEPT') {
      await page.context().setOffline(true)
      const failed = page.waitForEvent('requestfailed', request => request.url().endsWith(candidatePath) && request.method() === 'POST')
      await card.getByRole('button', { name: 'Save for review' }).click()
      failedSave = await failed
      await card.getByRole('alert').waitFor()
      await page.context().setOffline(false)
    }
    const responsePromise = page.waitForResponse(response => response.url().endsWith(candidatePath) && response.request().method() === 'POST')
    await card.getByRole('button', { name: failedSave ? 'Retry save' : 'Save for review' }).click()
    const response = await responsePromise
    assert.equal(response.status(), 201)
    const { id: candidateId, version } = await response.json()
    saved[id] = candidateId
    assert.equal(version, 1)
    const requestHeaders = await response.request().allHeaders()
    assert.match(requestHeaders['idempotency-key'], /^[A-Za-z0-9._:-]{1,128}$/)
    assert.deepEqual(Object.keys(response.request().postDataJSON()), ['save_token'])
    if (failedSave) {
      assert.equal(requestHeaders['idempotency-key'], (await failedSave.allHeaders())['idempotency-key'])
      assert.deepEqual(response.request().postDataJSON(), failedSave.postDataJSON())
      const replay = await api(admin, candidatePath, 201, {
        method: 'POST', data: response.request().postDataJSON(),
        headers: { 'Idempotency-Key': requestHeaders['idempotency-key'] },
      })
      assert.deepEqual(replay.body, { id: candidateId, version })
    }
    await card.getByText('Saved for review · Pending human review', { exact: true }).waitFor()
  }
  const savedQueue = await api(admin, candidatePath, 200)
  assert.equal(savedQueue.body.candidates.length, 4)
  await page.getByRole('button', { name: 'Saved candidates', exact: true }).click()
  await queueButton(page, 'OBJ-ACCEPT').waitFor()
  assert.equal(await queue(page).getByText('Requested by Fictional Evaluation Lead', { exact: true }).count(), 4)
  await capture(page, 1440, 'saved-queue', queue(page))
  await checkAxe(page, '.cr-panel', 'saved candidate queue')
  await suggestionCard(page, 'OBJ-ACCEPT').getByRole('button', { name: 'Open saved candidate' }).click()
  const evidence = candidate(page).getByRole('region', { name: 'Original evidence' })
  await evidence.locator('blockquote').waitFor()
  assert.equal(await evidence.locator('blockquote').textContent(), wording)
  const detailPath = `${candidatePath}/${saved['OBJ-ACCEPT']}`
  const initial = await api(admin, detailPath, 200)
  assert.deepEqual(initial.body.history.map(event => event.operation), ['ai_candidate_saved'])
  assert.equal(initial.headers.etag, '"1"')
  assert.equal(initial.body.reviewer_decision, null)
  const { source_id: sourceId } = initial.body.evidence[0]
  await evidence.getByText(`line 1 · Source ID ${sourceId}`, { exact: true }).waitFor()
  assert.equal((await api(admin, `${otherPath}/ai-candidates/${saved['OBJ-ACCEPT']}`, 404)).body.detail, 'Candidate not found.')
  await evidence.getByRole('button', { name: /Inspect source/ }).click()
  const source = page.getByRole('dialog', { name: filename })
  await source.getByText(wording, { exact: true }).waitFor()
  await source.getByRole('link', { name: 'Download original file' }).waitFor()
  await page.keyboard.press('Escape')
  await source.waitFor({ state: 'detached' })
  assert.ok(await evidence.getByRole('button', { name: /Inspect source/ }).evaluate(element => document.activeElement === element))
  await candidate(page).getByText('Generation provenance', { exact: true }).click()
  await candidate(page).getByText('fictional-provider:test', { exact: true }).waitFor()
  assert.equal(await candidate(page).getByText('Model digest', { exact: true }).count(), 0)
  for (const width of [1440, 1024, 768, 390, 320]) {
    await capture(page, width, 'source-evidence', candidate(page).getByRole('heading', { name: 'AI candidate review' }))
  }
  await checkAxe(page, '.cr-detail', '320px detail with provenance')

  let review = await beginReview(page, 'Accept for consideration')
  await page.keyboard.press('Tab')
  assert.ok(await review.dialog.getByRole('button', { name: 'Confirm decision' }).evaluate(element => document.activeElement === element))
  await page.keyboard.press('Tab')
  assert.ok(await review.dialog.getByLabel('Reviewer note (optional)').evaluate(element => document.activeElement === element))
  await page.keyboard.press('Shift+Tab')
  assert.ok(await review.dialog.getByRole('button', { name: 'Confirm decision' }).evaluate(element => document.activeElement === element))
  await capture(page, 1440, 'confirmation', review.dialog)
  await capture(page, 320, 'confirmation', review.dialog)
  await checkAxe(page, '.cr-dialog', '320px confirmation dialog')
  await page.keyboard.press('Escape')
  await review.dialog.waitFor({ state: 'detached' })
  assert.ok(await review.trigger.evaluate(element => document.activeElement === element))
  review = await beginReview(page, 'Accept for consideration')
  await review.dialog.getByLabel('Reviewer note (optional)').fill('Consider this documentation gap at debrief.')
  await page.context().setOffline(true)
  const failedReview = page.waitForEvent('requestfailed', request => request.url().endsWith('/review') && request.method() === 'POST')
  await review.dialog.getByRole('button', { name: 'Confirm decision' }).click()
  const firstAttempt = await failedReview
  await review.dialog.getByRole('alert').getByText(/decision could not be confirmed/i).waitFor()
  await page.context().setOffline(false)
  const acceptedResponse = await confirm(page, review.dialog, 200, '"1"', 'Retry decision')
  assert.deepEqual(acceptedResponse.request().postDataJSON(), firstAttempt.postDataJSON())
  assert.equal((await acceptedResponse.request().allHeaders())['idempotency-key'], (await firstAttempt.allHeaders())['idempotency-key'])
  assert.equal((await firstAttempt.allHeaders())['if-match'], '"1"')
  await decisionPanel(page).getByText('Latest human decision by').getByText('Fictional Evaluation Lead').waitFor()
  await audit(page).getByText('Consider this documentation gap at debrief.', { exact: true }).waitFor()
  await capture(page, 1440, 'accepted-and-audit', decisionPanel(page))
  const accepted = await api(admin, detailPath, 200)
  assert.equal(accepted.body.reviewer_decision, 'accepted_for_consideration')
  assert.equal(accepted.body.latest_decision.actor_user_id, 'candidate-admin')
  assert.equal(accepted.body.latest_decision.prior_state, 'pending_review')
  const reviewedRequest = acceptedResponse.request()
  const attemptHeaders = await reviewedRequest.allHeaders()
  const replay = await api(admin, detailPath + '/review', 200, {
    method: 'POST', data: reviewedRequest.postDataJSON(),
    headers: { 'Idempotency-Key': attemptHeaders['idempotency-key'], 'If-Match': attemptHeaders['if-match'] },
  })
  assert.deepEqual(replay.body, await acceptedResponse.json())
  assert.equal((await api(admin, detailPath, 200)).body.history.length, 2)

  await backToQueue(page)
  await openCandidate(page, 'OBJ-REJECT')
  review = await beginReview(page, 'Reject candidate')
  await review.dialog.getByLabel('Reviewer note (optional)').fill('The source leaves the recipient unresolved.')
  await confirm(page, review.dialog, 200, '"1"')
  await audit(page).getByText('The source leaves the recipient unresolved.', { exact: true }).waitFor()
  assert.equal(await decisionPanel(page).getByRole('button', { name: 'Reject candidate' }).count(), 0)
  await capture(page, 1024, 'rejected', decisionPanel(page))

  await backToQueue(page)
  await openCandidate(page, 'OBJ-MORE')
  review = await beginReview(page, 'Request more evidence')
  await review.dialog.getByRole('button', { name: 'Confirm decision' }).click()
  await review.dialog.getByRole('alert').getByText('Explain what evidence is needed.').waitFor()
  assert.equal(await review.dialog.getByLabel('What evidence is needed? (required)').getAttribute('aria-invalid'), 'true')
  await review.dialog.getByLabel('What evidence is needed? (required)').fill('Locate the signed dispatch handoff form.')
  await confirm(page, review.dialog, 200, '"1"')
  await audit(page).getByText('Locate the signed dispatch handoff form.', { exact: true }).waitFor()
  await capture(page, 768, 'more-evidence-required', decisionPanel(page))

  const reviewer = await signIn('reviewer')
  await openFindings(reviewer.page)
  await openCandidate(reviewer.page, 'OBJ-CONFLICT')
  const loser = await beginReview(reviewer.page, 'Reject candidate')
  await loser.dialog.getByLabel('Reviewer note (optional)').fill('Superseded draft decision.')
  await backToQueue(page)
  await openCandidate(page, 'OBJ-CONFLICT')
  const winner = await beginReview(page, 'Request more evidence')
  await winner.dialog.getByLabel('What evidence is needed? (required)').fill('Verify the date of the notebook entry.')
  await confirm(page, winner.dialog, 200, '"1"')
  await confirm(reviewer.page, loser.dialog, 412, '"1"')
  await candidate(reviewer.page).getByText(/Another reviewer or an evidence update changed this candidate/).waitFor()
  await audit(reviewer.page).getByText('Verify the date of the notebook entry.', { exact: true }).waitFor()
  assert.equal(await audit(reviewer.page).getByText('Superseded draft decision.').count(), 0)
  assert.equal(await decisionPanel(reviewer.page).getByRole('button', { name: 'Request more evidence' }).count(), 0)
  await capture(reviewer.page, 390, 'concurrent-review', candidate(reviewer.page).getByRole('heading', { name: 'AI candidate review' }))
  const newReview = await beginReview(reviewer.page, 'Accept for consideration')
  await confirm(reviewer.page, newReview.dialog, 200, '"2"')
  await audit(reviewer.page).getByText('Fictional Independent Reviewer', { exact: true }).waitFor()

  await backToQueue(page)
  await generate(page)
  const unsaved = suggestionCard(page, 'OBJ-ACCEPT')
  const update = await api(admin, `${exercisePath}/objectives`, 200, {
    method: 'PUT', data: { objectives: objectives.map(item => item.id === 'OBJ-ACCEPT'
      ? { ...item, text: 'Verify the updated dispatch handoff target.' } : item) },
  })
  assert.ok(update.body)
  const staleSaveResponse = page.waitForResponse(response => response.url().endsWith(candidatePath) && response.request().method() === 'POST')
  await unsaved.getByRole('button', { name: 'Save for review' }).click()
  const staleSave = await staleSaveResponse
  assert.equal(staleSave.status(), 409)
  assert.equal((await staleSave.json()).detail.code, 'AI_CONTEXT_CHANGED')
  await unsaved.getByRole('alert').getByText(/Generate AI suggestions again/).waitFor()
  await openCandidate(page, 'OBJ-ACCEPT')
  await candidate(page).getByRole('heading', { name: 'Evidence is stale' }).waitFor()
  await candidate(page).getByText('The exercise objective changed or was removed.', { exact: true }).first().waitFor()
  assert.equal(await candidate(page).locator('blockquote').first().textContent(), wording)
  await audit(page).getByText('Evidence invalidated', { exact: true }).waitFor()
  await audit(page).getByText('Consider this documentation gap at debrief.', { exact: true }).waitFor()
  assert.equal(await decisionPanel(page).getByRole('button').count(), 0)
  await capture(page, 390, 'stale-candidate', candidate(page).getByRole('heading', { name: 'AI candidate review' }))
  await checkAxe(page, '.cr-detail', '390px stale detail and audit')
  await backToQueue(page)
  await queue(page).getByLabel('Status on this page').selectOption('stale')
  await queueButton(page, 'OBJ-ACCEPT').waitFor()
  await capture(page, 320, 'stale-queue', queue(page))

  const afterUpdate = await generate(page)
  const eligible = afterUpdate.suggestions.filter(item => item.save_token)
  for (const item of eligible) {
    await api(admin, candidatePath, 201, {
      method: 'POST', data: { save_token: item.save_token }, headers: { 'Idempotency-Key': randomUUID() },
    })
  }
  await page.reload()
  await openFindings(page)
  await queue(page).getByRole('button', { name: 'Next' }).click()
  await queue(page).getByText('Page 2', { exact: true }).waitFor()
  assert.equal(await queue(page).getByRole('listitem').count(), 2)
  await queue(page).getByRole('button', { name: 'Previous' }).click()
  await queue(page).getByText('Page 1', { exact: true }).waitFor()
  assert.equal(await queue(page).getByRole('listitem').count(), 6)
  await queue(page).getByLabel('Status on this page').selectOption('rejected')
  await queueButton(page, 'OBJ-ACCEPT').waitFor({ state: 'hidden' })
  assert.ok((await queue(page).getByRole('listitem').count()) <= 1)
  await page.context().setOffline(true)
  await queue(page).getByRole('button', { name: 'Next' }).click()
  await queue(page).getByRole('alert').getByText('Candidate queue unavailable.').waitFor()
  await page.context().setOffline(false)
  await queue(page).getByRole('button', { name: 'Retry queue' }).click()
  await queue(page).getByText('Page 2', { exact: true }).waitFor()

  for (const role of ['viewer', 'evaluator']) {
    const user = await signIn(role)
    await openFindings(user.page)
    await queue(user.page).getByRole('button', { name: /^Open candidate for/ }).first().click()
    await decisionPanel(user.page).getByText('Review actions require an administrator or reviewer role.').waitFor()
    assert.equal(await decisionPanel(user.page).getByRole('button').count(), 0)
    await api(user, detailPath + '/review', 403, {
      method: 'POST', data: { decision: 'rejected' }, headers: { 'If-Match': '"3"', 'Idempotency-Key': randomUUID() },
    })
    if (role === 'viewer') {
      await api(user, candidatePath, 403, { method: 'POST', data: { save_token: eligible[0].save_token }, headers: { 'Idempotency-Key': randomUUID() } })
    }
    await user.page.context().close()
  }
  await api(reviewer, `${otherPath}/ai-candidates`, 404)
  const unauthenticated = await browser.newContext({ baseURL })
  assert.equal((await unauthenticated.request.get(detailPath)).status(), 401)
  await unauthenticated.close()
  await api(admin, `${exercisePath}/access/candidate-reviewer`, 200, { method: 'DELETE' })
  await backToQueue(reviewer.page)
  await queue(reviewer.page).getByRole('alert').getByText('Candidate access unavailable.').waitFor()
  await api(admin, `${exercisePath}/access`, 201, { method: 'POST', data: { user_id: 'candidate-reviewer' } })
  await queue(reviewer.page).getByRole('button', { name: 'Retry queue' }).click()
  await queue(reviewer.page).getByRole('button', { name: /^Open candidate for/ }).first().waitFor()
  const exercise = (await api(admin, exercisePath, 200)).body
  assert.deepEqual(exercise.findings, [])
  assert.deepEqual(exercise.actions, [])
  console.log('Candidate review passed with the injected fictional provider. Candidate routes used the migrated disposable database.')
}

async function disabledJourney() {
  const reviewer = await signIn('reviewer')
  const { page } = reviewer
  assert.equal((await api(reviewer, '/api/capabilities', 200)).body.analysis.ai_assistance.state, 'disabled')
  await openFindings(page)
  assert.equal(await page.getByRole('button', { name: 'Generate AI suggestions' }).count(), 0)
  const row = queue(page).getByRole('listitem').filter({ hasText: 'Evidence stale' }).first()
  await row.getByRole('button').click()
  await candidate(page).getByRole('heading', { name: 'Evidence is stale' }).waitFor()
  await audit(page).getByText('Evidence invalidated', { exact: true }).waitFor()
  assert.equal(await candidate(page).locator('blockquote').first().textContent(), wording)
  await page.reload()
  await openFindings(page)
  const current = queue(page).getByRole('listitem')
    .filter({ hasText: 'Pending human review', hasNotText: 'Evidence stale' }).first()
  await current.getByRole('button').click()
  const review = await beginReview(page, 'Accept for consideration')
  const reviewed = await confirm(page, review.dialog, 200, '"1"')
  await audit(page).getByText('Fictional Independent Reviewer', { exact: true }).waitFor()
  const { id } = await reviewed.json()
  const admin = await signIn('admin')
  await api(admin, `${exercisePath}/evidence`, 201, {
    method: 'POST', multipart: { files: { name: 'fictional_dispatch_supplement.txt', mimeType: 'text/plain',
      buffer: Buffer.from('The fictional exercise planner added a separate dispatch notebook entry.') } },
  })
  const { body } = await api(reviewer, `${candidatePath}/${id}`, 200)
  assert.equal(body.freshness, 'stale')
  assert.equal(body.review_state, 'accepted_for_consideration')
  assert.equal(body.evidence[0].text, wording)
  assert.deepEqual(body.stale_reasons, ['context_changed'])
  assert.equal(body.history.at(-1).operation, 'ai_candidate_invalidated')
  console.log('AI-disabled restart and browser refresh preserved the reviewer’s saved candidates, citations, and audit history.')
}

try {
  if (mode === 'review') await reviewJourney()
  else await disabledJourney()
  assert.deepEqual(errors, [])
  console.log(JSON.stringify({ mode, screenshots, axeChecks: axeResults, browserErrors: errors }))
} finally {
  await browser.close()
}
