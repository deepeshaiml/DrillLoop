import assert from 'node:assert/strict'
import { mkdir, mkdtemp } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const baseURL = process.env.DRILLLOOP_E2E_BASE_URL || 'http://127.0.0.1:8000'
const username = process.env.DRILLLOOP_E2E_USERNAME
const password = process.env.DRILLLOOP_E2E_PASSWORD
assert.ok(username && password, 'Set disposable DRILLLOOP_E2E_USERNAME and DRILLLOOP_E2E_PASSWORD.')
const project = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const screenshots = process.env.DRILLLOOP_E2E_SCREENSHOT_DIR || await mkdtemp(resolve(tmpdir(), 'drillloop-hybrid-browser-'))
await mkdir(screenshots, { recursive: true })

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 1120 } })
const pageErrors = []
page.on('pageerror', error => pageErrors.push(error.message))
const tab = name => page.locator('.tabs button').filter({ hasText: name })
const aiPanel = page.getByRole('region', { name: 'AI assistance' })
const generate = aiPanel.getByRole('button', { name: 'Generate AI suggestions' })
const detail = id => page.evaluate(async exerciseId => {
  const response = await fetch(`/api/exercises/${exerciseId}`)
  if (!response.ok) throw new Error(`Detail request failed: ${response.status}`)
  return response.json()
}, id)

async function uploadAndAnalyze(id, filename, fixture, findingCode) {
  await page.locator('#exercise-picker').selectOption(id)
  await tab('Evidence').click()
  await page.locator('.et-select-files input[type=file]').setInputFiles(resolve(project, fixture))
  await page.getByRole('button', { name: 'Upload 1 file', exact: true }).click()
  await page.locator('.et-source-card').filter({ hasText: filename }).waitFor()
  await tab('Overview').click()
  await page.getByRole('button', { name: 'Run evidence analysis' }).click()
  await page.getByRole('button', { name: 'Analysis already run' }).waitFor()
  await tab('Findings').click()
  if (findingCode) {
    const finding = page.locator('details.fa-finding-card').filter({ hasText: findingCode })
    await finding.getByRole('button', { name: 'Approve finding' }).waitFor()
    assert.match(await finding.innerText(), /Proposed · needs review/i)
  }
}

async function infer(id) {
  const before = await detail(id)
  const responsePromise = page.waitForResponse(
    response => response.url().endsWith(`/${id}/ai-suggestions`) && response.request().method() === 'POST',
    { timeout: 180_000 },
  )
  await generate.click()
  await aiPanel.getByText('Reviewing extracted observations with the local model…').waitFor()
  const response = await responsePromise
  assert.equal(response.status(), 200, await response.text())
  const result = await response.json()
  assert.equal(result.provider, 'ollama')
  assert.ok(result.input_tokens > 0 && result.output_tokens > 0)
  await generate.waitFor()
  await aiPanel.getByText('AI-generated suggestions — not reviewed or approved.').waitFor()
  assert.equal(await aiPanel.getByRole('button', { name: /approve|reject/i }).count(), 0)
  assert.deepEqual(await detail(id), before, 'AI leaves exercise detail, findings and actions unchanged')
  return result
}

try {
  await page.goto(baseURL)
  await page.locator('input[autocomplete=username]').fill(username)
  await page.locator('input[autocomplete=current-password]').fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.locator('#exercise-picker').waitFor()

  const narrativeId = 'PH4A-FICTIONAL-NARRATIVE'
  const notes = 'fictional_reception_notes.txt'
  await uploadAndAnalyze(narrativeId, notes, `evals/phase4a/${notes}`, 'RECEPTION_POINT_OPEN')
  const narrative = await infer(narrativeId)
  await aiPanel.getByRole('heading', { name: 'Insufficient evidence' }).waitFor()
  const noteCitation = aiPanel.getByRole('button', { name: new RegExp(notes) }).first()
  await noteCitation.waitFor()
  await page.screenshot({ path: resolve(screenshots, 'narrative-suggestions.png'), fullPage: true })
  await noteCitation.click()
  const noteDialog = page.getByRole('dialog', { name: notes })
  await noteDialog.getByText('line 1', { exact: true }).waitFor()
  await noteDialog.getByRole('button', { name: 'Close source details' }).click()

  const ocrId = 'PH4A-FICTIONAL-OCR'
  const pdf = 'utility_emergency_log_scanned.pdf'
  await uploadAndAnalyze(ocrId, pdf, `evals/phase2/sources/${pdf}`)
  assert.equal(await aiPanel.getByRole('button', { name: new RegExp(notes) }).count(), 0)
  const ocr = await infer(ocrId)
  const ocrCitation = aiPanel.getByRole('button', { name: /page 1.*Source time uncertain/ }).first()
  await ocrCitation.waitFor()
  await ocrCitation.click()
  const pdfDialog = page.getByRole('dialog', { name: pdf })
  await pdfDialog.getByText('page 1', { exact: true }).first().waitFor()
  await pdfDialog.getByRole('link', { name: /Download original file/ }).waitFor()
  await page.screenshot({ path: resolve(screenshots, 'ocr-source-citation.png'), fullPage: true })
  await pdfDialog.getByRole('button', { name: 'Close source details' }).click()

  await page.setViewportSize({ width: 390, height: 844 })
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true)
  await page.screenshot({ path: resolve(screenshots, 'ocr-suggestions-mobile.png'), fullPage: true })

  // Inject only the HTTP failure response here to verify UI feedback and retry controls.
  for (const [status, code, message] of [
    [504, 'AI_TIMEOUT', 'The local AI request timed out. Try again.'],
    [503, 'AI_UNAVAILABLE', 'The configured local AI model is unavailable. Rule-based analysis is still available.'],
  ]) {
    const endpoint = `**/${ocrId}/ai-suggestions`
    await page.route(endpoint, route => route.fulfill({ status, json: { detail: { code, message } } }), { times: 1 })
    await generate.click()
    await aiPanel.getByRole('alert').filter({ hasText: message }).waitFor()
    assert.equal(await generate.isEnabled(), true)
  }

  assert.deepEqual(pageErrors, [])
  console.log(JSON.stringify({
    result: 'PASS',
    real_local_model: narrative.model,
    narrative_suggestions: narrative.suggestions.length,
    ocr_suggestions: ocr.suggestions.length,
    screenshots,
    browser_errors: pageErrors,
  }, null, 2))
} finally {
  await browser.close()
}
