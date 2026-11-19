import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const baseURL = process.env.DRILLLOOP_E2E_BASE_URL || 'http://127.0.0.1:5173'
const username = process.env.DRILLLOOP_E2E_USERNAME
const password = process.env.DRILLLOOP_E2E_PASSWORD
assert.ok(username && password, 'Set local disposable DRILLLOOP_E2E_USERNAME and DRILLLOOP_E2E_PASSWORD.')

const exerciseId = 'OCR-PHASE2-DEMO'
const exerciseTitle = 'Fictional water utility scanned-PDF exercise'
const filename = 'utility_emergency_log_scanned.pdf'
const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const pdfPath = resolve(projectRoot, 'evals/phase2/sources', filename)
const screenshotDir = resolve(projectRoot, 'evals/phase2/results')
await mkdir(screenshotDir, { recursive: true })

const browserErrors = []
const httpErrors = []
const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ acceptDownloads: true, viewport: { width: 1440, height: 1100 } })
const page = await context.newPage()
page.setDefaultTimeout(10_000)
page.on('pageerror', error => browserErrors.push(error.message))
page.on('response', response => {
  const expectedUnauthenticatedProbe = response.status() === 401 && response.url().endsWith('/api/auth/session')
  if (response.status() >= 400 && !expectedUnauthenticatedProbe) httpErrors.push({ status: response.status(), url: response.url() })
})

try {
  await page.goto(baseURL)
  await page.getByRole('heading', { name: 'Sign in' }).waitFor()
  await page.locator('input[autocomplete=username]').fill(username)
  await page.locator('input[autocomplete=current-password]').fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.locator('#exercise-picker').waitFor()

  const setupResponse = await page.evaluate(async ({ id, title }) => {
    const exerciseList = await fetch('/api/exercises').then(response => response.json())
    if (exerciseList.some(item => item.id === id)) {
      const existing = await fetch(`/api/exercises/${encodeURIComponent(id)}`)
      const detail = await existing.json()
      if (detail.sources.length) return { status: 409, reused: false }
      return { status: existing.status, reused: true }
    }
    const session = await fetch('/api/auth/session').then(response => response.json())
    const response = await fetch('/api/exercises', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf_token },
      body: JSON.stringify({
        id,
        title,
        scenario: 'A wholly fictional exercise that demonstrates scanned PDF evidence provenance.',
        exercise_date: '2026-11-13',
        duration_minutes: 30,
        objectives: [
          {
            id: 'OBJ-PRESSURE-15',
            text: 'Restore stable pressure within 15 minutes after the alarm.',
            evaluation_rule: { type: 'elapsed_time', threshold_seconds: 900, start_terms: ['low-pressure alarm activated'], completion_terms: ['stable pressure'] },
          },
          {
            id: 'OBJ-STATION-B',
            text: 'Confirm Station B service restored.',
            evaluation_rule: { type: 'event_presence', terms: ['station b confirmed service restored'], finding_code: 'STATION_B_RESTORED' },
          },
        ],
      }),
    })
    return { status: response.status, reused: false }
  }, { id: exerciseId, title: exerciseTitle })
  assert.ok([200, 201].includes(setupResponse.status), `Disposable fictional exercise setup failed: HTTP ${setupResponse.status}`)
  await page.reload()
  await page.locator('#exercise-picker').selectOption(exerciseId)
  await page.getByRole('heading', { name: exerciseTitle }).waitFor()

  await page.locator('.tabs button').filter({ hasText: 'Evidence' }).click()
  await page.locator('.et-select-files input[type=file]').setInputFiles(pdfPath)
  await page.route(`**/api/exercises/${exerciseId}/evidence`, async route => {
    await new Promise(resolve => setTimeout(resolve, 400))
    await route.continue()
  })
  const uploadClick = page.getByRole('button', { name: 'Upload 1 file', exact: true }).click()
  await page.getByRole('status').filter({ hasText: /scanning PDF pages for OCR/i }).waitFor()
  await uploadClick

  const sourceCard = page.locator('.et-source-card').filter({ hasText: filename })
  await sourceCard.waitFor()
  await sourceCard.getByText('OCR completed · 2 scanned pages').waitFor()
  await page.screenshot({ path: resolve(screenshotDir, 'ocr-demo-evidence.png'), fullPage: true })

  await sourceCard.click()
  const sourceDialog = page.getByRole('dialog', { name: filename })
  await sourceDialog.waitFor()
  await sourceDialog.getByText(/OCR completed for original PDF pages 1, 2/i).waitFor()
  await sourceDialog.getByText(/line positions and word confidence are unavailable/i).waitFor()
  await sourceDialog.getByText('page 2', { exact: true }).first().waitFor()
  await sourceDialog.getByRole('link', { name: /Download original file/ }).waitFor()
  await page.screenshot({ path: resolve(screenshotDir, 'ocr-demo-source-page-citation.png'), fullPage: true })
  await sourceDialog.getByRole('button', { name: 'Close source details' }).click()

  await page.locator('.tabs button').filter({ hasText: 'Timeline' }).click()
  const timelineEvent = page.locator('.et-timeline-event').filter({ hasText: 'Station B confirmed service restored.' })
  await timelineEvent.waitFor()
  await timelineEvent.getByText(`${filename} · page 2`, { exact: true }).waitFor()
  await page.screenshot({ path: resolve(screenshotDir, 'ocr-demo-timeline.png'), fullPage: true })

  await page.locator('.tabs button').filter({ hasText: 'Overview' }).click()
  await page.getByRole('button', { name: 'Run evidence analysis' }).click()
  await page.locator('.tabs button').filter({ hasText: 'Findings' }).click()
  const finding = page.locator('.fa-finding-card').filter({ hasText: 'STATION_B_RESTORED' })
  await finding.waitFor()
  assert.match(await finding.innerText(), /Proposed · needs review/i)
  assert.match(await finding.innerText(), /utility_emergency_log_scanned\.pdf.*page 2/s)
  const findingDialogOpen = await finding.evaluate(element => element.open)
  if (!findingDialogOpen) await finding.locator('summary').click()
  await finding.getByRole('button', { name: /utility_emergency_log_scanned\.pdf/ }).click()
  const citationDialog = page.getByRole('dialog', { name: filename })
  await citationDialog.waitFor()
  await citationDialog.getByText('page 2', { exact: true }).first().waitFor()
  await page.screenshot({ path: resolve(screenshotDir, 'ocr-demo-proposed-finding-citation.png'), fullPage: true })
  await citationDialog.getByRole('button', { name: 'Close source details' }).click()

  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: /Export report/ }).click()
  const report = await downloadPromise
  assert.equal(report.suggestedFilename(), `${exerciseId}-AAR-IP.pdf`)

  assert.deepEqual(browserErrors, [], `Browser runtime errors: ${browserErrors.join('; ')}`)
  assert.deepEqual(httpErrors, [], `Unexpected HTTP errors: ${JSON.stringify(httpErrors)}`)
  console.log(JSON.stringify({
    result: 'PASS',
    prepared_exercise_reused: setupResponse.reused,
    exercise_id: exerciseId,
    source: filename,
    observed_workflow: [
      'upload and OCR processing status',
      'completed OCR page details and limitations',
      'extracted observation in timeline with page 2 locator',
      'objective evaluation with uncertain OCR times preserved for review',
      'proposed finding with original PDF page citation',
      'PDF report download',
    ],
    report: report.suggestedFilename(),
    screenshots: [
      'evals/phase2/results/ocr-demo-evidence.png',
      'evals/phase2/results/ocr-demo-source-page-citation.png',
      'evals/phase2/results/ocr-demo-timeline.png',
      'evals/phase2/results/ocr-demo-proposed-finding-citation.png',
    ],
    browser_errors: browserErrors,
    http_errors: httpErrors,
  }, null, 2))
} finally {
  await browser.close()
}
