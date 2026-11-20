import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const baseURL = process.env.DRILLLOOP_E2E_BASE_URL || 'http://127.0.0.1:5173'
const username = process.env.DRILLLOOP_E2E_USERNAME
const password = process.env.DRILLLOOP_E2E_PASSWORD
assert.ok(username && password, 'Set disposable DRILLLOOP_E2E_USERNAME and DRILLLOOP_E2E_PASSWORD.')

const exerciseId = 'OCR-PHASE3-DEMO'
const exerciseTitle = 'Fictional mixed-page water utility exercise'
const filename = 'phase3_same_page_mixed_water_log.pdf'
const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const pdfPath = resolve(projectRoot, 'evals/phase3/sources', filename)
const screenshotDir = resolve(projectRoot, 'evals/phase3/results/browser')
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
  await page.locator('#exercise-picker').selectOption(exerciseId)
  await page.getByRole('heading', { name: exerciseTitle }).waitFor()

  await page.locator('.tabs button').filter({ hasText: 'Evidence' }).click()
  await page.locator('.et-select-files input[type=file]').setInputFiles(pdfPath)
  await page.route(`**/api/exercises/${exerciseId}/evidence`, async route => {
    await new Promise(resolve => setTimeout(resolve, 350))
    await route.continue()
  })
  const uploadClick = page.getByRole('button', { name: 'Upload 1 file', exact: true }).click()
  await page.getByRole('status').filter({ hasText: /scanning PDF pages for OCR/i }).waitFor()
  await uploadClick

  const sourceCard = page.locator('.et-source-card').filter({ hasText: filename })
  await sourceCard.waitFor()
  await sourceCard.getByText('OCR completed · 1 page').waitFor()
  await page.screenshot({ path: resolve(screenshotDir, 'phase3-evidence.png'), fullPage: true })

  await sourceCard.click()
  const sourceDialog = page.getByRole('dialog', { name: filename })
  await sourceDialog.waitFor()
  await sourceDialog.getByText(/OCR processed original PDF page 1, including embedded image areas/i).waitFor()
  await sourceDialog.getByText(/OCR-derived timestamps remain uncertain/i).waitFor()
  await sourceDialog.getByText('page 1', { exact: true }).first().waitFor()
  const overlappedObservation = sourceDialog.locator('.et-source-observation').filter({ hasText: 'Dispatcher acknowledged the alarm.' })
  assert.equal(await overlappedObservation.count(), 1, 'The image/native overlap should yield one cited observation.')
  const repeatedEvent = sourceDialog.locator('.et-source-observation').filter({ hasText: 'Station B pump restored; pressure stable.' })
  assert.equal(await repeatedEvent.count(), 2, 'The repeated source event on pages 1 and 2 should remain separately cited.')
  await sourceDialog.getByRole('link', { name: /Download original file/ }).waitFor()
  await page.screenshot({ path: resolve(screenshotDir, 'phase3-page-citation.png'), fullPage: true })
  await sourceDialog.getByRole('button', { name: 'Close source details' }).click()

  await page.locator('.tabs button').filter({ hasText: 'Timeline' }).click()
  const pageOneEvent = page.locator('.et-timeline-event').filter({ hasText: 'phase3_same_page_mixed_water_log.pdf · page 1' }).filter({ hasText: 'Station B pump restored; pressure stable.' })
  await pageOneEvent.waitFor()
  await page.screenshot({ path: resolve(screenshotDir, 'phase3-timeline.png'), fullPage: true })

  await page.locator('.tabs button').filter({ hasText: 'Overview' }).click()
  await page.getByRole('button', { name: 'Run evidence analysis' }).click()
  await page.locator('.tabs button').filter({ hasText: 'Findings' }).click()
  const finding = page.locator('.fa-finding-card').filter({ hasText: 'STATION_B_PUMP_RESTORED' })
  await finding.waitFor()
  assert.match(await finding.innerText(), /Proposed · needs review/i)
  const findingDetailOpen = await finding.evaluate(element => element.open)
  if (!findingDetailOpen) await finding.locator('summary').click()
  assert.match(await finding.innerText(), /phase3_same_page_mixed_water_log\.pdf.*page 1/s)
  await finding.getByRole('button', { name: 'Approve finding' }).waitFor()
  await finding.getByRole('button', { name: 'Reject finding' }).waitFor()
  await finding.getByRole('button', { name: /phase3_same_page_mixed_water_log\.pdf/ }).first().click()
  const citationDialog = page.getByRole('dialog', { name: filename })
  await citationDialog.waitFor()
  await citationDialog.getByText('page 1', { exact: true }).first().waitFor()
  await page.screenshot({ path: resolve(screenshotDir, 'phase3-proposed-finding.png'), fullPage: true })
  await citationDialog.getByRole('button', { name: 'Close source details' }).click()

  const detail = await page.evaluate(async id => fetch(`/api/exercises/${encodeURIComponent(id)}`).then(response => response.json()), exerciseId)
  const source = detail.sources.find(item => item.filename === filename)
  const assessment = detail.objective_assessments.find(item => item.objective_id === 'OBJ-PRESSURE-15')
  const storedFinding = detail.findings.find(item => item.code === 'STATION_B_PUMP_RESTORED')
  assert.equal(source.provenance.ocr_status, 'completed')
  assert.equal(source.observation_count, 8)
  assert.equal(assessment.state, 'confirmed_success', 'The matching native-text repeat on page 2 supplies the usable time; page 1 OCR time remains uncertain.')
  assert.deepEqual(assessment.elapsed_seconds, [660])
  const ocrRestoration = detail.timeline.find(item => item.source_id === source.id && item.source_locator === 'page 1' && item.event_time_raw === '14:11')
  assert.equal(ocrRestoration.time_confidence, 'uncertain')
  assert.equal(storedFinding.status, 'proposed')
  assert.equal(storedFinding.reviewer, null)
  assert.ok(storedFinding.supporting_evidence.some(item => item.source_filename === filename && item.source_locator === 'page 1'))

  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: /Export report/ }).click()
  const report = await downloadPromise
  assert.equal(report.suggestedFilename(), `${exerciseId}-AAR-IP.pdf`)

  assert.deepEqual(browserErrors, [], `Browser runtime errors: ${browserErrors.join('; ')}`)
  assert.deepEqual(httpErrors, [], `Unexpected HTTP errors: ${JSON.stringify(httpErrors)}`)
  console.log(JSON.stringify({
    result: 'PASS',
    exercise_id: exerciseId,
    source: filename,
    workflow: [
      'uploaded the synthetic same-page mixed PDF and observed OCR status',
      'confirmed native text and embedded image text coexist on page 1',
      'suppressed the exact overlap once and retained the repeated event on page 2',
      'followed page-level citation to source details and original file download',
      'opened the timeline and ran unchanged objective evaluation',
      'kept the OCR time uncertain; elapsed-time result used the repeated selectable-text page 2 record',
      'inspected a source-linked proposed finding with pending human review',
      'exported the PDF report',
    ],
    report: report.suggestedFilename(),
    screenshots: [
      'evals/phase3/results/browser/phase3-evidence.png',
      'evals/phase3/results/browser/phase3-page-citation.png',
      'evals/phase3/results/browser/phase3-timeline.png',
      'evals/phase3/results/browser/phase3-proposed-finding.png',
    ],
    browser_errors: browserErrors,
    http_errors: httpErrors,
  }, null, 2))
} finally {
  await browser.close()
}
