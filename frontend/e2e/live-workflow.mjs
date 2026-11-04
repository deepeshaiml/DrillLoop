import assert from 'node:assert/strict'
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
const browserErrors = []
const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ acceptDownloads: true, ignoreHTTPSErrors: ignoreHttpsErrors })
const page = await context.newPage()
page.setDefaultTimeout(10_000)
page.on('pageerror', error => browserErrors.push(error.message))
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
  await textareas.nth(1).fill(`OBJ-01: Restore essential circuits | within=${threshold}m | start=power failed | complete=essential circuits restored`)
  await modal.getByRole('button', { name: 'Create exercise' }).click()
  await page.getByRole('heading', { name: title }).waitFor()
}

async function importEvidenceAndAnalyze(id, expectedState) {
  await page.getByRole('button', { name: 'Evidence', exact: true }).last().click()
  const content = `timestamp,event\n14:00,Power failed at the control panel.\n14:04,Essential circuits restored.\n`
  await page.locator('.upload-button input[type=file]').setInputFiles({
    name: `${id}-events.csv`,
    mimeType: 'text/csv',
    buffer: Buffer.from(content),
  })
  await page.getByText(`${id}-events.csv`, { exact: true }).waitFor()
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
  if (await seedDemo.count()) {
    await seedDemo.click()
    await page.getByRole('heading', { name: 'Night Shift: Extended Power Loss' }).waitFor()
    await page.locator('.tabs button').filter({ hasText: 'Findings' }).click()
    assert.equal(await page.locator('.finding-card').count(), 5, 'The fictional seeded path should render its five source-linked proposals.')
    const seedFinding = page.locator('.finding-card').filter({ hasText: 'AREA FOR IMPROVEMENT' }).first()
    const seedFindingTitle = await seedFinding.locator('h3').innerText()
    await seedFinding.getByRole('button', { name: 'Approve finding' }).click()
    await page.getByText(`approved by ${reviewerName}`, { exact: false }).waitFor()
    await page.locator('.tabs button').filter({ hasText: 'Corrective actions' }).click()
    const seedAction = page.locator('.action-card').filter({ hasText: seedFindingTitle }).first()
    await seedAction.waitFor()
    await seedAction.locator('input[name=title]').fill('Fictional demo: rehearse the restoration procedure and log completion time.')
    await seedAction.locator('input[name=owner]').fill('Fictional Demo Team')
    await seedAction.locator('input[name=due_date]').fill('2027-01-15')
    await seedAction.locator('textarea[name=acceptance_criteria]').fill('A fictional timed retest verifies the objective.')
    await seedAction.getByRole('button', { name: 'Save action' }).click()
    await seedAction.getByRole('button', { name: 'Approve action' }).click()
    page.once('dialog', dialog => dialog.accept('Fictional demo closure reference DEMO-01 reviewed.'))
    await seedAction.getByRole('button', { name: 'Record closure' }).click()
    await page.getByText(new RegExp(`Closed by ${reviewerName}`)).waitFor()
    const seededDownloadPromise = page.waitForEvent('download')
    await page.getByRole('button', { name: /Export report/ }).click()
    const seededDownload = await seededDownloadPromise
    assert.equal(seededDownload.suggestedFilename(), 'HOSP-PO-2026-01-AAR-IP.pdf')
    await page.reload()
    await page.getByRole('heading', { name: 'Night Shift: Extended Power Loss' }).waitFor()
    await page.locator('.tabs button').filter({ hasText: 'Corrective actions' }).click()
    assert.equal((await page.locator('.action-card').filter({ hasText: seedFindingTitle }).locator('.status-chip').last().innerText()).toLowerCase(), 'closed')
    await page.locator('.tabs button').filter({ hasText: 'Overview' }).click()
  }

  await createExercise(passId, passTitle, 5)
  await importEvidenceAndAnalyze(passId, 'confirmed success')
  assert.equal(await page.locator('.finding-card').count(), 0, 'Evidence within the five-minute objective must not create a failure finding.')

  await createExercise(failId, failTitle, 2)
  await importEvidenceAndAnalyze(failId, 'confirmed failure')
  await page.getByRole('button', { name: 'Findings', exact: true }).last().click()
  const finding = page.locator('.finding-card').first()
  await finding.waitFor()
  assert.match((await finding.locator('.citation-row').allInnerTexts()).join(' '), /14:04|Essential circuits restored/i)
  const citationButton = finding.locator('.citation-row').first()
  await citationButton.click()
  const sourceDialog = page.getByRole('dialog', { name: /events\.csv/ })
  await sourceDialog.waitFor()
  assert.equal(await sourceDialog.evaluate(element => element.contains(document.activeElement)), true, 'Opening a source dialog should move focus into it.')
  await page.keyboard.press('Escape')
  await sourceDialog.waitFor({ state: 'detached' })
  assert.equal(await citationButton.evaluate(element => document.activeElement === element), true, 'Closing a source dialog should restore focus to its citation.')
  await finding.getByRole('button', { name: 'Approve finding' }).click()
  await page.getByText(`approved by ${reviewerName}`, { exact: false }).waitFor()

  await page.locator('.tabs button').filter({ hasText: 'Corrective actions' }).click()
  const action = page.locator('.action-card').first()
  await action.waitFor()
  await action.locator('input[name=title]').fill('Practice restoration and record a timed verification.')
  await action.locator('input[name=owner]').fill('Facilities Operations')
  await action.locator('input[name=due_date]').fill('2027-01-15')
  await action.locator('textarea[name=acceptance_criteria]').fill('A timed retest confirms the restoration objective is met.')
  await action.getByRole('button', { name: 'Save action' }).click()
  await action.getByRole('button', { name: 'Approve action' }).click()
  page.once('dialog', dialog => dialog.accept('Timed retest record E2E-VERIFY-01 accepted by reviewer.'))
  await action.getByRole('button', { name: 'Record closure' }).click()
  await page.getByText(new RegExp(`Closed by ${reviewerName}`)).waitFor()

  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: /Export report/ }).click()
  const download = await downloadPromise
  assert.match(download.suggestedFilename(), new RegExp(`${failId}-AAR-IP\\.pdf`))

  await page.reload()
  await page.getByRole('heading', { name: failTitle }).waitFor()
  await page.locator('.tabs button').filter({ hasText: 'Corrective actions' }).click()
  assert.equal((await page.locator('.action-card .status-chip').last().innerText()).toLowerCase(), 'closed')
  await page.locator('#exercise-picker').selectOption(passId)
  await page.getByRole('heading', { name: passTitle }).waitFor()
  await page.reload()
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

    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.getByRole('heading', { name: 'Sign in' }).waitFor()
    await page.locator('input[autocomplete=username]').fill(outsiderUsername)
    await page.locator('input[autocomplete=current-password]').fill(outsiderPassword)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await page.locator('#exercise-picker').waitFor()
    const crossUser = await page.evaluate(async id => {
      const detail = await fetch(`/api/exercises/${encodeURIComponent(id)}`)
      const report = await fetch(`/api/exercises/${encodeURIComponent(id)}/report.pdf`)
      return { detail: detail.status, report: report.status, detail_body: await detail.text(), report_body: await report.text() }
    }, failId)
    assert.equal(crossUser.detail, 404, `Ungranted detail request should return 404; received ${crossUser.detail}: ${crossUser.detail_body}`)
    assert.equal(crossUser.report, 404, `Ungranted report request should return 404; received ${crossUser.report}: ${crossUser.report_body}`)
  }

  assert.deepEqual(browserErrors, [], `Browser reported runtime errors: ${browserErrors.join('; ')}`)
  const workflows = ['named login', 'fictional seeded full review and report flow', 'create independent exercises', 'upload unfamiliar CSV', 'objective pass/fail analysis', 'source citation review', 'finding approval', 'action assignment/approval/closure', 'PDF export', 'refresh persistence', 'exercise switching']
  if (outsiderUsername && outsiderPassword) workflows.push('exercise access grant/revoke', 'same-organization cross-user detail and report denial')
  console.log(JSON.stringify({
    result: 'PASS',
    accessibility_checks: ['keyboard sign-in order', 'associated form labels', 'announced sign-in errors', 'accessible modal roles and names', 'dialog focus entry, wrapping, Escape close, and focus restoration'],
    workflows,
    pass_exercise: passId,
    fail_exercise: failId,
    report: download.suggestedFilename(),
    browser_errors: browserErrors,
  }, null, 2))
} finally {
  await browser.close()
}
