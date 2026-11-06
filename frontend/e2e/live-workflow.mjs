import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import { chromium } from 'playwright'

const baseURL = process.env.DRILLLOOP_E2E_BASE_URL || 'http://127.0.0.1:5173'
const username = process.env.DRILLLOOP_E2E_USERNAME
const password = process.env.DRILLLOOP_E2E_PASSWORD
const outsiderUsername = process.env.DRILLLOOP_E2E_OUTSIDER_USERNAME
const outsiderPassword = process.env.DRILLLOOP_E2E_OUTSIDER_PASSWORD
const outsiderName = process.env.DRILLLOOP_E2E_OUTSIDER_NAME || 'CI Viewer'
const reviewerName = process.env.DRILLLOOP_E2E_REVIEWER_NAME || 'Demo Administrator'
const expectedScanStatus = process.env.DRILLLOOP_E2E_EXPECT_SCAN_STATUS || 'not_scanned'
const ignoreHttpsErrors = process.env.DRILLLOOP_E2E_IGNORE_HTTPS_ERRORS === '1'
assert.ok(username && password, 'Set DRILLLOOP_E2E_USERNAME and DRILLLOOP_E2E_PASSWORD for an isolated local test identity.')

const suffix = `${Date.now()}`
const passId = `E2E-PASS-${suffix}`
const failId = `E2E-FAIL-${suffix}`
const passTitle = `Unfamiliar evidence pass ${suffix}`
const failTitle = `Unfamiliar evidence failure ${suffix}`
const seedId = 'HOSP-PO-2026-01'
const screenshotDir = resolve(process.env.DRILLLOOP_E2E_SCREENSHOT_DIR || '../artifacts/ui-phase4')
await mkdir(screenshotDir, { recursive: true })
const browserErrors = []
const browserConsoleErrors = []
const httpErrorResponses = []
const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ acceptDownloads: true, ignoreHTTPSErrors: ignoreHttpsErrors, viewport: { width: 1440, height: 1100 } })
const page = await context.newPage()
page.setDefaultTimeout(10_000)
page.on('pageerror', error => browserErrors.push(error.message))
page.on('console', message => { if (message.type() === 'error') browserConsoleErrors.push(message.text()) })
page.on('response', response => { if (response.status() >= 400) httpErrorResponses.push({ status: response.status(), url: response.url() }) })
let nextApiRequestAt = Date.now()
await page.route('**/api/**', async route => {
  const now = Date.now()
  const delay = Math.max(0, nextApiRequestAt - now)
  nextApiRequestAt = Math.max(now, nextApiRequestAt) + 125
  if (delay) await new Promise(resolve => setTimeout(resolve, delay))
  await route.continue()
})

async function createExercise(id, title, threshold) {
  const newExercise = page.getByRole('button', { name: 'New exercise', exact: true })
  const emptyStateCreate = page.getByRole('button', { name: 'Create exercise', exact: true })
  const trigger = await newExercise.count() ? newExercise : emptyStateCreate
  await trigger.click()
  let modal = page.getByRole('dialog', { name: 'Create an exercise' })
  await modal.waitFor()
  await page.waitForFunction(() => {
    const dialog = document.querySelector('[role="dialog"]')
    const first = Array.from(dialog?.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])') || [])
      .find(element => element.getAttribute('aria-hidden') !== 'true')
    return first && document.activeElement === first
  })
  assert.equal(await modal.evaluate(element => element.contains(document.activeElement)), true, 'Opening a dialog should move keyboard focus into it.')
  const labels = await modal.locator('label').evaluateAll(items => items.map(label => Boolean(label.control)))
  assert.ok(labels.length > 0 && labels.every(Boolean), 'Every visible exercise form label should be associated with a control.')
  const firstFocusable = modal.locator('button:not([disabled]), input:not([disabled]), textarea:not([disabled])').first()
  const lastFocusable = modal.locator('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled])').last()
  await page.keyboard.press('Shift+Tab')
  assert.equal(await lastFocusable.evaluate(element => document.activeElement === element), true, 'Shift+Tab from the first control should wrap to the last enabled control.')
  await page.keyboard.press('Tab')
  assert.equal(await firstFocusable.evaluate(element => document.activeElement === element), true, 'Tab from the last control should wrap to the first control.')
  await page.keyboard.press('Escape')
  await modal.waitFor({ state: 'detached' })
  assert.equal(await trigger.evaluate(element => document.activeElement === element), true, 'Closing a dialog should restore focus to its trigger.')
  await trigger.click()
  modal = page.getByRole('dialog', { name: 'Create an exercise' })
  const inputs = modal.locator('input')
  await inputs.nth(0).fill(id)
  await inputs.nth(1).fill(new Date().toISOString().slice(0, 10))
  await inputs.nth(2).fill(title)
  const textareas = modal.locator('textarea')
  await textareas.nth(0).fill(`Unfamiliar evidence workflow for ${title}.`)
  await modal.getByRole('button', { name: 'Create exercise' }).click()
  await page.getByRole('heading', { name: 'Define what success looks like' }).waitFor()
  await page.getByRole('button', { name: 'Add objectives', exact: true }).click()
  const objectiveDialog = page.getByRole('dialog', { name: 'Define what success looks like' })
  await objectiveDialog.getByRole('button', { name: 'Add objective' }).click()
  const objective = objectiveDialog.locator('.objective-draft-card').first()
  await objective.locator('input').fill('OBJ-01')
  await objective.locator('textarea').nth(0).fill('Restore essential circuits within the configured target time.')
  await objective.locator('select').first().selectOption('elapsed_time')
  await objective.getByLabel('Objective 1 target time', { exact: true }).fill(String(threshold))
  await objective.getByLabel('Objective 1 target time unit').selectOption('minutes')
  await objective.locator('textarea').nth(1).fill('power failed')
  await objective.locator('textarea').nth(2).fill('essential circuits restored')
  await objectiveDialog.getByRole('button', { name: 'Save objectives' }).click()
  await page.getByRole('heading', { name: title }).waitFor()
}

async function importEvidenceAndAnalyze(id, expectedState) {
  await page.getByRole('button', { name: 'Evidence', exact: true }).last().click()
  const content = `timestamp,event\n14:00,Power failed at the control panel.\n14:04,Essential circuits restored.\n`
  const filename = `${id}-events.csv`
  await page.locator('.et-select-files input[type=file]').setInputFiles({
    name: filename,
    mimeType: 'text/csv',
    buffer: Buffer.from(content),
  })
  await page.getByRole('button', { name: 'Upload 1 file', exact: true }).click()
  await page.locator('.et-source-card').filter({ hasText: filename }).waitFor()
  const uploaded = await page.evaluate(async exerciseId => {
    const response = await fetch(`/api/exercises/${encodeURIComponent(exerciseId)}`)
    const detail = await response.json()
    return detail.sources.filter(source => source.filename === `${exerciseId}-events.csv`)
  }, id)
  assert.equal(uploaded.length, 1, 'The upload should create exactly one source record.')
  assert.equal(uploaded[0].scan_status, expectedScanStatus, 'The uploaded file should have the expected scanner verdict.')
  await page.getByRole('button', { name: 'Overview', exact: true }).last().click()
  await page.getByRole('button', { name: 'Run evidence analysis' }).click()
  await page.getByText(expectedState, { exact: true }).waitFor()
}

try {
  await page.goto(baseURL)
  await page.getByRole('heading', { name: 'Sign in' }).waitFor()
  const usernameInput = page.locator('input[autocomplete=username]')
  const passwordInput = page.locator('input[autocomplete=current-password]')
  await page.keyboard.press('Tab')
  assert.equal(await usernameInput.evaluate(element => document.activeElement === element), true, 'Keyboard tab order should begin with the username field.')
  await page.keyboard.press('Tab')
  assert.equal(await passwordInput.evaluate(element => document.activeElement === element), true, 'Keyboard tab order should reach the password field.')
  await usernameInput.fill(username)
  await passwordInput.fill('intentionally-incorrect-test-password')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByRole('alert').waitFor()
  assert.match(await page.getByRole('alert').innerText(), /sign|credential|password/i, 'Sign-in errors should be announced through an alert.')
  await passwordInput.fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.locator('#exercise-picker').waitFor()

  const seedDemo = page.getByRole('button', { name: 'Load fictional demo', exact: true })
  const seedOption = page.locator(`#exercise-picker option[value="${seedId}"]`)
  if (!(await seedOption.count())) {
    if (await seedDemo.count()) {
    await seedDemo.click()
    } else {
      const seedResponse = await page.evaluate(async () => {
        const session = await fetch('/api/auth/session').then(response => response.json())
        const response = await fetch('/api/demo/seed', { method: 'POST', headers: { 'X-CSRF-Token': session.csrf_token } })
        return { status: response.status, body: await response.json() }
      })
      assert.equal(seedResponse.status, 200, `The isolated fictional fixture should seed successfully: ${JSON.stringify(seedResponse.body)}`)
      await page.reload()
      await page.locator('#exercise-picker').waitFor()
    }
  }
  const seedWorkspaceHeading = page.locator('.page-heading h1').filter({ hasText: 'Night Shift: Extended Power Loss' })
  if (!(await seedWorkspaceHeading.count())) {
    await page.locator('.exercise-list-row').filter({ hasText: seedId }).getByRole('button').click()
  }
  {
    await seedWorkspaceHeading.waitFor()
    await page.locator('.tabs button').filter({ hasText: 'Findings' }).click()
    assert.equal(await page.locator('.fa-finding-card').count(), 5, 'The fictional seeded path should render its five source-linked proposals.')
    await page.screenshot({ path: resolve(screenshotDir, 'after-findings-desktop.png'), fullPage: true })
    const conflictingFinding = page.locator('.fa-finding-card').filter({ hasText: 'COMMUNICATION_ACK_DELAY' }).first()
    if (!(await conflictingFinding.evaluate(card => card.open))) await conflictingFinding.locator('summary').click()
    assert.match(await conflictingFinding.locator('.fa-uncertainty').innerText(), /Conflicting source timing/i, 'The finding details should surface the recorded source timing disagreement.')
    assert.match(await conflictingFinding.locator('.fa-uncertainty').innerText(), /evaluator_notes\.txt, line 9/i, 'The uncertainty message should identify the conflicting source locator.')
    await conflictingFinding.locator('summary').click()
    const seedFinding = page.locator('.fa-finding-card').filter({ hasText: 'AREA FOR IMPROVEMENT' }).first()
    const seedFindingTitle = await seedFinding.locator('h3').innerText()
    const seedCitation = seedFinding.locator('.fa-evidence-link').first()
    await seedCitation.click()
    const sourceDialog = page.getByRole('dialog', { name: /control_room_log\.csv/ })
    await sourceDialog.waitFor()
    await page.screenshot({ path: resolve(screenshotDir, 'after-finding-details.png'), fullPage: true })
    assert.equal(await sourceDialog.evaluate(element => element.contains(document.activeElement)), true, 'Opening a citation should move focus into the Phase 3 source viewer.')
    await page.keyboard.press('Escape')
    await sourceDialog.waitFor({ state: 'detached' })
    assert.equal(await seedCitation.evaluate(element => document.activeElement === element), true, 'Closing a citation should return focus to its source link.')
    await seedFinding.getByRole('button', { name: 'Approve finding' }).click()
    let decisionDialog = page.getByRole('dialog', { name: 'Approve this finding?' })
    await decisionDialog.waitFor()
    assert.equal(await decisionDialog.evaluate(element => element.contains(document.activeElement)), true, 'Review confirmation should move focus into its dialog.')
    await page.keyboard.press('Escape')
    await decisionDialog.waitFor({ state: 'detached' })
    assert.equal(await seedFinding.getByRole('button', { name: 'Approve finding' }).evaluate(element => document.activeElement === element), true, 'Canceling review should restore focus to the finding action.')
    await seedFinding.getByRole('button', { name: 'Approve finding' }).click()
    decisionDialog = page.getByRole('dialog', { name: 'Approve this finding?' })
    await decisionDialog.getByLabel(/Reviewer note/).fill('Fictional demo review: source wording and objective compared.')
    await page.route('**/api/findings/*/review', route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Synthetic temporary review service failure.' }) }))
    await decisionDialog.getByRole('button', { name: 'Approve finding' }).click()
    await decisionDialog.getByRole('alert').waitFor()
    assert.match(await decisionDialog.getByRole('alert').innerText(), /Synthetic temporary review service failure/i, 'A failed review request should be explained in the open dialog.')
    assert.equal(await seedFinding.locator('.fa-review-outcome').count(), 0, 'An API failure must not display a false reviewer decision.')
    await page.unroute('**/api/findings/*/review')
    await decisionDialog.getByRole('button', { name: 'Approve finding' }).click()
    await seedFinding.locator('.fa-review-outcome').waitFor()
    const rejectFinding = page.locator('.fa-finding-card').filter({ hasText: 'AREA FOR IMPROVEMENT' }).last()
    if (!(await rejectFinding.evaluate(card => card.open))) await rejectFinding.locator('summary').click()
    await rejectFinding.getByRole('button', { name: 'Reject finding' }).click()
    decisionDialog = page.getByRole('dialog', { name: 'Reject this finding?' })
    await decisionDialog.getByLabel(/Reviewer note/).fill('Fictional demo review: rejected in the synthetic regression path.')
    await decisionDialog.getByRole('button', { name: 'Reject finding' }).click()
    await rejectFinding.locator('.fa-review-outcome').waitFor()
    await page.getByRole('button', { name: 'Dismiss message' }).click()
    await page.screenshot({ path: resolve(screenshotDir, 'after-finding-review.png'), fullPage: true })
    await page.locator('.tabs button').filter({ hasText: 'Corrective actions' }).click()
    const seedAction = page.locator('.fa-action-card').filter({ hasText: seedFindingTitle }).first()
    await seedAction.waitFor()
    await page.screenshot({ path: resolve(screenshotDir, 'after-corrective-actions-desktop.png'), fullPage: true })
    assert.equal(await seedAction.getByRole('button', { name: 'Approve action' }).isDisabled(), true, 'Action approval should stay unavailable while its owner and due date are unset.')
    await seedAction.locator('.fa-action-edit summary').click()
    await seedAction.locator('input[name=title]').fill('x')
    assert.equal(await seedAction.locator('form.fa-edit-form').evaluate(form => form.checkValidity()), false, 'Action title validation should reject a value shorter than the API minimum.')
    await seedAction.locator('input[name=title]').fill('Fictional demo: rehearse the restoration procedure and log completion time.')
    await seedAction.locator('input[name=owner]').fill('Fictional Demo Team')
    await seedAction.locator('input[name=due_date]').fill('2027-01-15')
    await seedAction.locator('textarea[name=acceptance_criteria]').fill('A fictional timed retest verifies the objective.')
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.screenshot({ path: resolve(screenshotDir, 'after-action-details-editing.png'), fullPage: true })
    await seedAction.getByRole('button', { name: 'Save action' }).click()
    await seedAction.getByRole('button', { name: 'Approve action' }).click()
    decisionDialog = page.getByRole('dialog', { name: 'Approve this action?' })
    await decisionDialog.getByRole('button', { name: 'Approve action' }).click()
    await seedAction.getByRole('button', { name: 'Record closure evidence' }).click()
    const closureDialog = page.getByRole('dialog', { name: 'Record closure evidence' })
    await closureDialog.waitFor()
    await closureDialog.getByRole('button', { name: 'Record closure evidence' }).click()
    await closureDialog.getByRole('alert').waitFor()
    assert.match(await closureDialog.getByRole('alert').innerText(), /at least 12 characters/i, 'Closure evidence must show validation feedback before submission.')
    await closureDialog.getByLabel(/Closure evidence/).fill('Fictional demo closure reference DEMO-01 reviewed by the synthetic evaluator.')
    await closureDialog.getByRole('button', { name: 'Record closure evidence' }).click()
    await seedAction.locator('.fa-closure-record').waitFor()
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.screenshot({ path: resolve(screenshotDir, 'after-action-closure.png'), fullPage: true })
    const seededDownloadPromise = page.waitForEvent('download')
    await page.getByRole('button', { name: /Export report/ }).click()
    const seededDownload = await seededDownloadPromise
    assert.equal(seededDownload.suggestedFilename(), 'HOSP-PO-2026-01-AAR-IP.pdf')
    await page.reload()
    await page.getByRole('heading', { name: 'Night Shift: Extended Power Loss' }).waitFor()
    await page.locator('.exercise-list-row.is-selected').filter({ hasText: seedId }).getByRole('button', { name: 'Continue' }).click()
    await page.locator('.page-heading h1').filter({ hasText: 'Night Shift: Extended Power Loss' }).waitFor()
    await page.locator('.tabs button').filter({ hasText: 'Corrective actions' }).click()
    assert.equal((await page.locator('.fa-action-card').filter({ hasText: seedFindingTitle }).locator('.fa-status').innerText()).toLowerCase(), 'closed')
    await page.locator('.tabs button').filter({ hasText: 'Overview' }).click()
  }

  let missingSupportInjected = false
  await page.route('**/api/exercises/HOSP-PO-2026-01', async route => {
    const response = await route.fetch()
    const detail = await response.json()
    const unsupportedFinding = detail.findings.find(item => item.code === 'RESPONSE_TIME_DISCREPANCY' && item.status === 'proposed' && item.supporting_evidence.length > 0)
    assert.ok(unsupportedFinding, 'The isolated synthetic fixture should include a proposed finding for the missing-support state.')
    unsupportedFinding.supporting_evidence = []
    missingSupportInjected = true
    await route.fulfill({ response, body: JSON.stringify(detail) })
  })
  await page.reload()
  await page.locator('.exercise-list-row.is-selected').filter({ hasText: seedId }).getByRole('button', { name: 'Continue' }).click()
  await page.getByRole('heading', { name: 'Night Shift: Extended Power Loss' }).waitFor()
  assert.equal(missingSupportInjected, true, 'The isolated browser fixture should inject the missing-support state into the detail response.')
  await page.locator('.tabs button').filter({ hasText: 'Findings' }).click()
  const unsupportedFinding = page.locator('.fa-finding-card').filter({ hasText: 'RESPONSE_TIME_DISCREPANCY' }).first()
  if (!(await unsupportedFinding.evaluate(card => card.open))) await unsupportedFinding.locator('summary').click()
  await unsupportedFinding.locator('.fa-evidence-missing').waitFor()
  assert.equal(await unsupportedFinding.getByRole('button', { name: 'Approve finding' }).isDisabled(), true, 'A finding without source support must not be approvable.')
  await page.unroute('**/api/exercises/HOSP-PO-2026-01')
  await page.reload()

  await createExercise(passId, passTitle, 5)
  await importEvidenceAndAnalyze(passId, 'confirmed success')
  assert.equal(await page.locator('.fa-finding-card').count(), 0, 'Evidence within the five-minute objective must not create a failure finding.')
  await page.locator('.tabs button').filter({ hasText: 'Findings' }).click()
  await page.locator('.fa-empty h3').waitFor()
  assert.match(await page.locator('.fa-empty h3').innerText(), /No finding proposals were produced|Start with objectives and source evidence/)
  await page.locator('.tabs button').filter({ hasText: 'Corrective actions' }).click()
  await page.locator('.fa-empty h3').waitFor()
  assert.equal(await page.locator('.fa-empty h3').innerText(), 'No actions are linked to this exercise yet')
  await page.locator('.tabs button').filter({ hasText: 'Overview' }).click()

  await createExercise(failId, failTitle, 2)
  await importEvidenceAndAnalyze(failId, 'confirmed failure')
  await page.getByRole('button', { name: 'Findings', exact: true }).last().click()
  const finding = page.locator('.fa-finding-card').first()
  await finding.waitFor()
  assert.match((await finding.locator('.fa-evidence-link').allInnerTexts()).join(' '), /14:04|Essential circuits restored/i)
  const citationButton = finding.locator('.fa-evidence-link').first()
  await citationButton.click()
  const sourceDialog = page.getByRole('dialog', { name: /events\.csv/ })
  await sourceDialog.waitFor()
  assert.equal(await sourceDialog.evaluate(element => element.contains(document.activeElement)), true, 'Opening a source dialog should move focus into it.')
  await page.keyboard.press('Escape')
  await sourceDialog.waitFor({ state: 'detached' })
  assert.equal(await citationButton.evaluate(element => document.activeElement === element), true, 'Closing a source dialog should restore focus to its citation.')
  await finding.getByRole('button', { name: 'Approve finding' }).click()
  let decisionDialog = page.getByRole('dialog', { name: 'Approve this finding?' })
  await decisionDialog.getByRole('button', { name: 'Approve finding' }).click()
  await finding.locator('.fa-review-outcome').waitFor()

  await page.locator('.tabs button').filter({ hasText: 'Corrective actions' }).click()
  const action = page.locator('.fa-action-card').first()
  await action.waitFor()
  await action.locator('.fa-action-edit summary').click()
  await action.locator('input[name=title]').fill('Practice restoration and record a timed verification.')
  await action.locator('input[name=owner]').fill('Facilities Operations')
  await action.locator('input[name=due_date]').fill('2027-01-15')
  await action.locator('textarea[name=acceptance_criteria]').fill('A timed retest confirms the restoration objective is met.')
  await action.getByRole('button', { name: 'Save action' }).click()
  await action.getByRole('button', { name: 'Approve action' }).click()
  decisionDialog = page.getByRole('dialog', { name: 'Approve this action?' })
  await decisionDialog.getByRole('button', { name: 'Approve action' }).click()
  await action.getByRole('button', { name: 'Record closure evidence' }).click()
  const closureDialog = page.getByRole('dialog', { name: 'Record closure evidence' })
  await closureDialog.getByLabel(/Closure evidence/).fill('Fictional E2E timed retest record E2E-VERIFY-01 accepted by the reviewer.')
  await closureDialog.getByRole('button', { name: 'Record closure evidence' }).click()
  await action.locator('.fa-closure-record').waitFor()

  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: /Export report/ }).click()
  const download = await downloadPromise
  assert.match(download.suggestedFilename(), new RegExp(`${failId}-AAR-IP\\.pdf`))

  await page.reload()
  await page.getByRole('heading', { name: failTitle }).waitFor()
  await page.locator('.exercise-list-row.is-selected').filter({ hasText: failId }).getByRole('button', { name: 'Continue' }).click()
  await page.getByRole('heading', { name: failTitle }).waitFor()
  await page.locator('.tabs button').filter({ hasText: 'Corrective actions' }).click()
  assert.equal((await page.locator('.fa-action-card .fa-status').last().innerText()).toLowerCase(), 'closed')
  await page.locator('#exercise-picker').selectOption(passId)
  await page.getByRole('heading', { name: passTitle }).waitFor()
  await page.reload()
  await page.getByRole('heading', { name: passTitle }).waitFor()
  await page.setViewportSize({ width: 390, height: 844 })
  const resumedExercise = page.locator('.exercise-list-row.is-selected').filter({ hasText: passId })
  await resumedExercise.scrollIntoViewIfNeeded()
  await resumedExercise.getByRole('button', { name: 'Continue' }).click()
  await page.getByRole('heading', { name: passTitle }).waitFor()
  await page.waitForTimeout(100)
  assert.equal(await page.evaluate(() => window.scrollY), 0, 'Resuming an exercise from a scrolled library should return its workspace to the top.')

  await page.setViewportSize({ width: 390, height: 844 })
  await page.locator('#exercise-picker').selectOption(seedId)
  await page.getByRole('heading', { name: 'Night Shift: Extended Power Loss' }).waitFor()
  await page.locator('.subnav-link').filter({ hasText: 'Findings' }).click()
  const mobileNavVisibility = await page.locator('.subnav-link[aria-current="page"]').evaluate(element => {
    const nav = element.closest('.subnav')
    if (!nav) return false
    const itemRect = element.getBoundingClientRect()
    const navRect = nav.getBoundingClientRect()
    return itemRect.left >= navRect.left && itemRect.right <= navRect.right
  })
  assert.equal(mobileNavVisibility, true, 'The active section label should remain fully visible in the horizontally scrolling mobile navigation.')
  const mobileWidth = await page.evaluate(() => ({ viewport: window.innerWidth, document: document.documentElement.scrollWidth, body: document.body.scrollWidth }))
  assert.ok(mobileWidth.document <= mobileWidth.viewport && mobileWidth.body <= mobileWidth.viewport, `Findings overflow at 390px: ${JSON.stringify(mobileWidth)}`)
  await page.screenshot({ path: resolve(screenshotDir, 'mobile-findings.png'), fullPage: true })
  await page.locator('.subnav-link').filter({ hasText: 'Corrective actions' }).click()
  const mobileActionWidth = await page.evaluate(() => ({ viewport: window.innerWidth, document: document.documentElement.scrollWidth, body: document.body.scrollWidth }))
  assert.ok(mobileActionWidth.document <= mobileActionWidth.viewport && mobileActionWidth.body <= mobileActionWidth.viewport, `Corrective actions overflow at 390px: ${JSON.stringify(mobileActionWidth)}`)
  await page.screenshot({ path: resolve(screenshotDir, 'mobile-corrective-actions.png'), fullPage: true })
  await page.setViewportSize({ width: 1440, height: 1100 })
  await page.locator('#exercise-picker').selectOption(passId)
  await page.getByRole('heading', { name: passTitle }).waitFor()

  if (outsiderUsername && outsiderPassword) {
    await page.getByRole('button', { name: 'Manage access' }).click()
    let accessDialog = page.getByRole('dialog', { name: 'Manage access' })
    await page.waitForFunction(() => {
      const dialog = document.querySelector('[role="dialog"]')
      const first = Array.from(dialog?.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])') || [])
        .find(element => element.getAttribute('aria-hidden') !== 'true')
      return first && document.activeElement === first
    })
    assert.equal(await accessDialog.evaluate(element => element.contains(document.activeElement)), true, 'Opening access management should move focus into the dialog.')
    await page.keyboard.press('Escape')
    await accessDialog.waitFor({ state: 'detached' })
    assert.equal(await page.getByRole('button', { name: 'Manage access' }).evaluate(element => document.activeElement === element), true, 'Closing access management should restore focus.')
    await page.getByRole('button', { name: 'Manage access' }).click()
    accessDialog = page.getByRole('dialog', { name: 'Manage access' })
    await accessDialog.locator('select').selectOption({ label: `${outsiderName} · viewer` })
    await page.waitForLoadState('networkidle')
    const accessURL = new URL(`/api/exercises/${encodeURIComponent(passId)}/access`, baseURL).href
    const grantResponse = page.waitForResponse(response =>
      response.request().method() === 'POST' && response.url() === accessURL
    )
    const grantsRefreshResponse = page.waitForResponse(response =>
      response.request().method() === 'GET' && response.url() === accessURL
    )
    await accessDialog.getByRole('button', { name: 'Grant exercise access' }).click()
    const createdGrant = await grantResponse
    assert.equal(createdGrant.status(), 201, `Expected grant to succeed, received HTTP ${createdGrant.status()}: ${await createdGrant.text()}`)
    const accessState = await grantsRefreshResponse
    assert.equal(accessState.status(), 200, `Expected grant list refresh to succeed, received HTTP ${accessState.status()}: ${await accessState.text()}`)
    assert.ok((await accessState.json()).some(grant => grant.name === outsiderName), `Grant endpoint did not return ${outsiderName}.`)
    const viewerRow = accessDialog.locator('.access-row').filter({ hasText: outsiderName })
    await viewerRow.waitFor().catch(async error => {
      throw new Error(`Granted account is missing from the open dialog. Dialog text: ${await accessDialog.innerText()}. ${error.message}`)
    })
    const revokeResponse = page.waitForResponse(response =>
      response.request().method() === 'DELETE' && response.url().includes('/access/')
    )
    await viewerRow.getByRole('button', { name: 'Revoke' }).click()
    const revoked = await revokeResponse
    assert.equal(revoked.status(), 200, `Expected exercise access revocation to succeed, got HTTP ${revoked.status()}.`)
    await viewerRow.waitFor({ state: 'detached' })
    await accessDialog.getByRole('button', { name: 'Done' }).click()

    await page.locator('#exercise-picker').selectOption(seedId)
    await page.getByRole('heading', { name: 'Night Shift: Extended Power Loss' }).waitFor()
    await page.getByRole('button', { name: 'Manage access' }).click()
    const seedAccessDialog = page.getByRole('dialog', { name: 'Manage access' })
    await seedAccessDialog.locator('select').selectOption({ label: `${outsiderName} · viewer` })
    const seedAccessURL = new URL(`/api/exercises/${encodeURIComponent(seedId)}/access`, baseURL).href
    const seedGrantResponse = page.waitForResponse(response => response.request().method() === 'POST' && response.url() === seedAccessURL)
    await seedAccessDialog.getByRole('button', { name: 'Grant exercise access' }).click()
    assert.equal((await seedGrantResponse).status(), 201, 'The viewer should receive read access to the fictional seeded exercise.')
    await seedAccessDialog.getByRole('button', { name: 'Done' }).click()

    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.getByRole('heading', { name: 'Sign in' }).waitFor()
    await page.locator('input[autocomplete=username]').fill(outsiderUsername)
    await page.locator('input[autocomplete=current-password]').fill(outsiderPassword)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await page.locator('#exercise-picker').waitFor()
    await page.locator('.subnav-link').filter({ hasText: 'Findings' }).click()
    const viewerFindings = page.locator('.fa-finding-card')
    await viewerFindings.first().waitFor()
    assert.equal(await page.getByRole('button', { name: 'Approve finding' }).count(), 0, 'Viewer accounts must not see finding approval controls.')
    assert.equal(await page.getByRole('button', { name: 'Reject finding' }).count(), 0, 'Viewer accounts must not see finding rejection controls.')
    await page.locator('.subnav-link').filter({ hasText: 'Corrective actions' }).click()
    assert.equal(await page.locator('.fa-action-edit').count(), 0, 'Viewer accounts must not see action edit forms.')
    assert.equal(await page.getByRole('button', { name: 'Approve action' }).count(), 0, 'Viewer accounts must not see action approval controls.')
    assert.equal(await page.getByRole('button', { name: 'Record closure evidence' }).count(), 0, 'Viewer accounts must not see closure controls.')
    const deniedReviews = await page.evaluate(async exerciseId => {
      const session = await fetch('/api/auth/session').then(response => response.json())
      const detail = await fetch(`/api/exercises/${encodeURIComponent(exerciseId)}`).then(response => response.json())
      const finding = detail.findings.find(item => item.status === 'proposed')
      const action = detail.actions.find(item => item.status === 'proposed')
      const headers = { 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf_token }
      const findingResponse = await fetch(`/api/findings/${finding.id}/review`, { method: 'POST', headers, body: JSON.stringify({ decision: 'approved' }) })
      const actionResponse = await fetch(`/api/actions/${action.id}/review`, { method: 'POST', headers, body: JSON.stringify({ decision: 'approved' }) })
      const updateResponse = await fetch(`/api/actions/${action.id}`, { method: 'PUT', headers, body: JSON.stringify({ title: action.title, owner: action.owner, priority: action.priority, due_date: action.due_date, acceptance_criteria: action.acceptance_criteria }) })
      return { finding: findingResponse.status, action: actionResponse.status, update: updateResponse.status }
    }, seedId)
    assert.deepEqual(deniedReviews, { finding: 403, action: 403, update: 403 }, 'Server-side role checks must deny viewer review and edit requests.')
    const crossUser = await page.evaluate(async id => {
      const detail = await fetch(`/api/exercises/${encodeURIComponent(id)}`)
      const report = await fetch(`/api/exercises/${encodeURIComponent(id)}/report.pdf`)
      return { detail: detail.status, report: report.status, detail_body: await detail.text(), report_body: await report.text() }
    }, failId)
    assert.equal(crossUser.detail, 404, `Ungranted detail request should return 404; received ${crossUser.detail}: ${crossUser.detail_body}`)
    assert.equal(crossUser.report, 404, `Ungranted report request should return 404; received ${crossUser.report}: ${crossUser.report_body}`)
  }

  assert.deepEqual(browserErrors, [], `Browser reported runtime errors: ${browserErrors.join('; ')}`)
  const expectedHttpError = ({ status, url }) => {
    const path = new URL(url).pathname
    if (status === 401 && (path === '/api/auth/session' || path === '/api/auth/login')) return true
    if (status === 503 && /^\/api\/findings\/[^/]+\/review$/.test(path)) return true
    if (status === 403 && (/^\/api\/findings\/[^/]+\/review$/.test(path) || /^\/api\/actions\/[^/]+(?:\/review|\/close)?$/.test(path))) return true
    return status === 404 && (path === `/api/exercises/${encodeURIComponent(failId)}` || path === `/api/exercises/${encodeURIComponent(failId)}/report.pdf`)
  }
  const unexpectedHttpErrors = httpErrorResponses.filter(response => !expectedHttpError(response))
  assert.deepEqual(unexpectedHttpErrors, [], `Browser workflow received unexpected HTTP errors: ${JSON.stringify(unexpectedHttpErrors)}`)
  const expectedConsoleError = message => /status of 401 \(Unauthorized\)|status of 403 \(Forbidden\)|status of 404 \(Not Found\)|status of 503 \(Service Unavailable\)/.test(message)
  const unexpectedConsoleErrors = browserConsoleErrors.filter(message => !expectedConsoleError(message))
  assert.deepEqual(unexpectedConsoleErrors, [], `Browser console reported unexpected errors: ${unexpectedConsoleErrors.join('; ')}`)
  assert.equal(browserConsoleErrors.length, httpErrorResponses.length, 'Each browser console network error should match a captured expected API error response.')
  const workflows = ['named login', 'fictional seeded full review and report flow', 'finding approval and rejection confirmations', 'source citation review and focus return', 'action validation, assignment, approval and evidence-based closure', 'create independent exercises', 'upload unfamiliar CSV', 'objective pass/fail analysis', 'PDF export', 'refresh persistence', 'exercise switching', '390px responsive layout, active mobile navigation, and overflow checks']
  if (outsiderUsername && outsiderPassword) workflows.push('exercise access grant/revoke', 'viewer read-only controls', 'server-side viewer review and edit denial', 'same-organization cross-user detail and report denial')
  console.log(JSON.stringify({
    result: 'PASS',
    accessibility_checks: ['keyboard sign-in order', 'associated form labels', 'announced sign-in errors', 'accessible modal roles and names', 'dialog focus entry, wrapping, Escape close, and focus restoration'],
    workflows,
    pass_exercise: passId,
    fail_exercise: failId,
    report: download.suggestedFilename(),
    browser_errors: browserErrors,
    browser_console_errors: browserConsoleErrors,
    expected_http_errors: httpErrorResponses.map(({ status, url }) => ({ status, path: new URL(url).pathname })),
  }, null, 2))
} finally {
  await browser.close()
}
