import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { basename, resolve } from 'node:path'
import { chromium } from 'playwright'

const mode = process.argv[2]
const baseURL = process.env.DRILLLOOP_E2E_BASE_URL
const passwords = JSON.parse(process.env.DRILLLOOP_EUREKA_CREDENTIALS)
const workspace = process.env.DRILLLOOP_EUREKA_WORKSPACE
const artifacts = process.env.DRILLLOOP_EUREKA_ARTIFACTS
const axeFile = process.env.DRILLLOOP_EUREKA_AXE
const exerciseId = 'HOSP-PO-2026-01'
const path = `/api/exercises/${exerciseId}`
const title = 'Night Shift: Extended Power Loss'
const observation = 'The fictional pharmacy supervisor signed the backup refrigerator temperature check form.'
const findingTitle = 'Fictional pharmacy temperature check is documented'
const closure = 'Fictional retest DEMO-PO-01 recorded essential circuits restored in 54 seconds.'
const browser = await chromium.launch()
const errors = []
const checks = []
const captures = []
const pages = []
const videoContexts = []

async function signIn(account) {
  const viewport = { width: 1440, height: 1000 }
  const recordVideo = mode === 'fictional' && account !== 'eureka-viewer'
    ? { dir: resolve(artifacts, 'video'), size: viewport } : undefined
  const context = await browser.newContext({ baseURL, viewport, acceptDownloads: true, recordVideo })
  const page = await context.newPage()
  if (recordVideo) videoContexts.push({ context, video: page.video(), account })
  pages.push(page)
  page.setDefaultTimeout(15_000)
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/')
  await page.getByLabel('Username').fill(account)
  await page.locator('input[autocomplete=current-password]').fill(passwords[account])
  const login = page.waitForResponse(response => response.url().endsWith('/api/auth/login'))
  await page.getByRole('button', { name: 'Sign in' }).click()
  const response = await login
  assert.equal(response.status(), 200)
  return { page, csrf: (await response.json()).csrf_token }
}

const nav = (page, label) => page.getByRole('navigation', { name: 'Exercise sections' })
  .getByRole('button', { name: new RegExp(`^${label}`) })
const candidate = page => page.getByRole('region', { name: 'AI candidate review' })

async function snapshot(page, name, target) {
  await page.evaluate(() => window.scrollTo(0, 0))
  if (target) await target.scrollIntoViewIfNeeded()
  await page.screenshot({ path: resolve(artifacts, name + '.png') })
  captures.push(name + '.png')
}

async function view(page, id, name) {
  const heading = page.locator('.page-heading h1').filter({ hasText: name })
  const row = page.locator('.exercise-list-row').filter({ hasText: id }).getByRole('button')
  const option = page.locator(`#exercise-picker option[value="${id}"]`)
  const pickerInWorkspace = page.locator('.page-heading').getByRole('heading')
  await heading.or(row).or(pickerInWorkspace).first().waitFor()
  if (!(await heading.isVisible())) {
    if (await row.isVisible()) await row.click()
    else {
      await option.waitFor({ state: 'attached' })
      await page.locator('#exercise-picker').selectOption(id)
    }
  }
  await heading.waitFor()
}

async function request(session, endpoint, status, options = {}) {
  const response = await session.page.request.fetch(endpoint, { ...options, headers: { 'X-CSRF-Token': session.csrf } })
  assert.equal(response.status(), status, `${options.method || 'GET'} ${endpoint}`)
  return response.json()
}

async function seed(session) {
  const { page } = session
  const load = page.getByRole('button', { name: 'Load fictional demo', exact: true })
  await load.waitFor()
  await load.click()
  await view(page, exerciseId, title)
}

async function grantReviewer(page) {
  await page.getByRole('button', { name: 'Manage access' }).click()
  const dialog = page.getByRole('dialog', { name: 'Manage access' })
  await dialog.getByRole('combobox').selectOption('eureka-reviewer')
  await dialog.getByRole('button', { name: 'Grant exercise access' }).click()
  await dialog.getByText('eureka-reviewer · reviewer', { exact: true }).waitFor()
  await dialog.getByRole('button', { name: 'Close access management' }).click()
}

async function upload(page, filenames, purpose) {
  await nav(page, 'Evidence').click()
  await page.locator('.et-select-files input[type=file]').setInputFiles(filenames)
  if (purpose) await page.getByLabel('Source purpose').selectOption(purpose)
  await page.getByRole('button', { name: `Upload ${filenames.length} file${filenames.length > 1 ? 's' : ''}`, exact: true }).click()
  for (const name of filenames) {
    await page.locator('.et-source-card').filter({ hasText: basename(name) }).waitFor()
  }
}

async function exportReport(page, filename) {
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: /^(Download|Export) report/ }).click(),
  ])
  await download.saveAs(resolve(artifacts, filename))
  const bytes = await readFile(resolve(artifacts, filename))
  assert.equal(bytes.subarray(0, 5).toString(), '%PDF-')
}

async function generate(page, status) {
  const response = page.waitForResponse(item => item.url().endsWith('/ai-suggestions'), { timeout: 125_000 })
  await page.getByRole('button', { name: 'Generate AI suggestions' }).click()
  const reply = await response
  assert.equal(reply.status(), status)
  return reply.json()
}

async function checkAxe(page, selector) {
  if (!axeFile) return
  if (!await page.evaluate(() => Boolean(window.axe))) await page.addScriptTag({ path: axeFile })
  const violations = await page.evaluate(async selector => {
    const scan = await window.axe.run(selector, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] },
    })
    return scan.violations.map(({ id, nodes }) => ({ id, nodes: nodes.map(node => node.target) }))
  }, selector)
  assert.deepEqual(violations, [])
  checks.push(`axe ${selector}`)
}

async function approveFinding(page, card) {
  if (!(await card.evaluate(node => node.open))) await card.locator('summary').click()
  await card.getByRole('button', { name: 'Approve finding' }).click()
  const dialog = page.getByRole('dialog', { name: 'Approve this finding?' })
  await dialog.getByLabel(/Reviewer note/).fill('Fictional exercise review. Checked the linked source wording.')
  await dialog.getByRole('button', { name: 'Approve finding' }).click()
  await card.getByText(/Reviewer decision: Approved by/).waitFor()
}

async function fictional() {
  const operator = await signIn('eureka-operator')
  const { page } = operator
  await seed(operator)
  await snapshot(page, '01-fictional-overview')
  await nav(page, 'Objectives').click()
  await page.getByText(/Restore and confirm essential power circuits within 60 seconds/).first().waitFor()
  await snapshot(page, '02-objectives')
  await grantReviewer(page)
  const outsider = await signIn('eureka-viewer')
  await request(outsider, path, 404)
  await outsider.page.close()
  await upload(page, [resolve(workspace, 'fictional_pharmacy_scan.pdf'), resolve(workspace, 'fictional_pharmacy_handoff.txt')])
  const scan = page.locator('.et-source-card').filter({ hasText: 'fictional_pharmacy_scan.pdf' })
  await scan.getByText('OCR completed · 1 page').waitFor()
  await scan.click()
  const source = page.getByRole('dialog', { name: 'fictional_pharmacy_scan.pdf' })
  await source.getByText('page 1', { exact: true }).first().waitFor()
  await snapshot(page, '03-ocr-and-source', source)
  await page.keyboard.press('Escape')
  await nav(page, 'Timeline').click()
  await page.getByText('Conflicting or unresolved times').waitFor()
  await snapshot(page, '04-timeline-and-conflicts', page.locator('.et-conflict-group').first())
  const before = await request(operator, path, 200)
  assert.equal(before.findings.length, 5)
  assert.equal(before.findings.filter(item => item.status === 'approved').length, 0)
  assert.equal(before.actions.filter(item => item.status === 'closed').length, 0)
  assert.ok(before.timeline.some(row => row.extraction_method === 'ocr' && row.time_confidence === 'uncertain'))
  await nav(page, 'Findings').click()
  await snapshot(page, '05-deterministic-findings')
  const result = await generate(page, 200)
  assert.equal(result.model, 'eureka-controlled:test')
  assert.deepEqual(await request(operator, path, 200), before)
  const advisory = page.getByRole('article').filter({ has: page.getByRole('heading', { name: /^OBJ-03 ·/ }) })
  assert.equal(await advisory.locator('q').textContent(), observation)
  await snapshot(page, '06-controlled-suggestion', advisory)
  await advisory.getByRole('button', { name: 'Save for review' }).click()
  await advisory.getByRole('button', { name: 'Open saved candidate' }).waitFor()

  const reviewer = await signIn('eureka-reviewer')
  const rp = reviewer.page
  await view(rp, exerciseId, title)
  await nav(rp, 'Findings').click()
  await rp.getByRole('button', { name: 'Open candidate for OBJ-03', exact: true }).click()
  await candidate(rp).getByRole('button', { name: 'Accept for consideration', exact: true }).click()
  await rp.getByRole('dialog', { name: 'Accept for consideration', exact: true })
    .getByRole('button', { name: 'Confirm decision' }).click()
  const promote = candidate(rp).getByRole('button', { name: 'Create proposed finding' })
  await promote.waitFor()
  assert.deepEqual((await request(reviewer, path, 200)).findings, before.findings)
  await snapshot(rp, '07-human-acceptance', candidate(rp))
  await promote.click()
  const dialog = rp.getByRole('dialog', { name: 'Create proposed finding' })
  await dialog.getByLabel('Finding title').fill(findingTitle)
  await dialog.getByLabel('Evidence-based observation').fill(observation)
  await dialog.getByLabel('Interpretation', { exact: true }).fill('The signed form supports documentation of the temperature check. Event time remains unknown.')
  await dialog.getByRole('combobox', { name: /^Category/ }).selectOption('strength')
  await dialog.getByRole('checkbox', { name: /I confirm this wording/ }).check()
  await rp.setViewportSize({ width: 390, height: 844 })
  await checkAxe(rp, '.cr-promotion-dialog')
  assert.equal(await rp.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
  await snapshot(rp, '08-promotion-390px', dialog)
  await rp.setViewportSize({ width: 1440, height: 1000 })
  await dialog.getByRole('button', { name: 'Confirm proposed finding' }).click()
  await candidate(rp).getByText(/Awaiting separate human finding review/).waitFor()
  const afterPromotion = await request(reviewer, path, 200)
  const promoted = afterPromotion.findings.find(item => item.title === findingTitle)
  assert.ok(promoted.source_candidate_id)
  assert.equal(promoted.status, 'proposed')
  assert.equal(promoted.reviewer, null)
  assert.deepEqual(afterPromotion.actions, before.actions)
  await candidate(rp).getByRole('button', { name: 'Open finding', exact: true }).click()
  await candidate(rp).waitFor({ state: 'hidden' })
  const promotedCard = rp.locator('.fa-finding-card').filter({ hasText: findingTitle })
  await promotedCard.getByText('Awaiting reviewer decision', { exact: true }).waitFor()
  await approveFinding(rp, promotedCard)
  await snapshot(rp, '09-separate-finding-approval', promotedCard)

  const power = rp.locator('.fa-finding-card').filter({ hasText: 'POWER_RESTORATION_DELAY' })
  await approveFinding(rp, power)
  await nav(page, 'Corrective actions').click()
  const action = page.locator('.fa-action-card').filter({ hasText: 'Essential power restoration exceeded the exercise target' })
  if (!(await action.evaluate(node => node.open))) await action.locator('summary').first().click()
  await action.locator('.fa-action-edit summary').click()
  await action.locator('input[name=owner]').fill('Fictional Facilities Operations')
  await action.locator('input[name=due_date]').fill('2027-01-15')
  await action.locator('textarea[name=acceptance_criteria]').fill('Record a fictional retest restoring essential circuits within 60 seconds.')
  await action.getByRole('button', { name: 'Save action' }).click()
  await action.getByRole('button', { name: 'Approve action' }).click()
  await page.getByRole('dialog', { name: 'Approve this action?' }).getByRole('button', { name: 'Approve action' }).click()
  await action.getByRole('button', { name: 'Record closure evidence' }).click()
  const close = page.getByRole('dialog', { name: 'Record closure evidence' })
  await close.getByLabel(/Closure evidence/).fill(closure)
  await snapshot(page, '10-human-closure-confirmation', close)
  await close.getByRole('button', { name: 'Record closure evidence' }).click()
  await action.locator('.fa-closure-record').getByText(closure, { exact: true }).waitFor()
  await snapshot(page, '11-action-closed', action)
  const closed = await request(operator, path, 200)
  assert.equal(closed.actions.filter(item => item.status === 'closed').length, 1)
  assert.equal(closed.findings.filter(item => item.status === 'approved').length, 2)
  await nav(page, 'Reports').click()
  await snapshot(page, '12-report-and-audit')
  await exportReport(page, 'fictional-eureka-AAR-IP.pdf')
  await page.reload()
  await view(page, exerciseId, title)
  assert.deepEqual(await request(operator, path, 200), closed)
  checks.push('seeded objectives, evidence upload, scan OCR and source page, timeline conflicts, five rule proposals, viewer denial',
    'controlled inference, save, independent acceptance, promotion, separate finding approval, action review and closure, PDF download, refresh')
}

async function restart() {
  const session = await signIn('eureka-reviewer')
  const { page } = session
  await view(page, exerciseId, title)
  const detail = await request(session, path, 200)
  const promoted = detail.findings.find(item => item.title === findingTitle)
  assert.equal(promoted.status, 'approved')
  assert.equal(promoted.reviewer, 'Fictional Independent Reviewer')
  assert.ok(promoted.source_candidate_id && promoted.supporting_evidence.length)
  assert.ok(detail.actions.some(item => item.status === 'closed' && item.closure_evidence === closure))
  const capabilities = await request(session, '/api/capabilities', 200)
  assert.equal(capabilities.analysis.ai_assistance.state, 'disabled')
  await nav(page, 'Findings').click()
  assert.equal(await page.getByRole('button', { name: 'Generate AI suggestions' }).count(), 0)
  await page.getByRole('button', { name: 'Open candidate for OBJ-03', exact: true }).click()
  await candidate(page).getByText('Proposed finding created', { exact: true }).waitFor()
  await snapshot(page, '13-ai-disabled-candidate-history', candidate(page))
  checks.push('AI-disabled API restart preserves approved finding, closure, candidate source and audit history')
}

async function publicDocuments() {
  const session = await signIn('eureka-operator')
  const { page } = session
  const cases = JSON.parse(await readFile('evals/real-evidence/cases.json', 'utf8'))
  for (const [key, inputs, purpose] of [
    ['A', ['.eureka-private/derived/LA25-PLAN.pdf', '.eureka-private/derived/LA25-EEG.pdf'], 'planning'],
    ['B', ['.eureka-private/sources/NDMS_Regional-Surge_-Surge-Squared-Exercise-AAR_FINAL.pdf'], 'published_evaluation'],
  ]) {
    const data = cases[key].exercise
    const endpoint = `/api/exercises/${data.id}`
    await request(session, '/api/exercises', 201, { method: 'POST', data })
    await page.reload()
    await view(page, data.id, data.title)
    await upload(page, inputs.map(item => resolve(item)), purpose)
    const first = page.locator('.et-source-card').filter({ hasText: basename(inputs[0]) })
    await first.click()
    const source = page.getByRole('dialog', { name: basename(inputs[0]) })
    await source.getByText(/page 1, line/).first().waitFor()
    await snapshot(page, `public-${key}-source`, source)
    await page.keyboard.press('Escape')
    await nav(page, 'Timeline').click()
    await page.getByRole('heading', { name: /^Reference documents/ }).waitFor()
    if (key === 'A') {
      await page.getByRole('textbox', { name: 'Search timeline events and source references' }).fill('08:00')
      await page.getByText('Source clock 08:00', { exact: true }).first().waitFor()
      assert.equal(await page.getByRole('heading', { name: /^Events with a recorded time/ }).count(), 0)
      await snapshot(page, 'public-A-planned-time')
    }
    await nav(page, 'Overview').click()
    await page.getByRole('button', { name: 'Run evidence analysis' }).click()
    await page.getByRole('button', { name: 'Analysis already run' }).waitFor()
    await nav(page, 'Findings').click()
    const reply = await generate(page, 422)
    assert.equal(reply.detail.code, 'AI_EVIDENCE_REQUIRED')
    await page.getByRole('alert').filter({ hasText: 'Upload observed performance evidence' }).waitFor()
    const detail = await request(session, endpoint, 200)
    assert.equal(detail.findings.length, 0)
    assert.equal(detail.actions.length, 0)
    await snapshot(page, `public-${key}-no-performance-evidence`)
    await exportReport(page, `public-${key}-browser-report.pdf`)
    await page.reload()
    await view(page, data.id, data.title)
    assert.deepEqual(await request(session, endpoint, 200), detail)
    checks.push(`public case ${key}: login, objectives, classified PDF upload, page locator, timeline, analysis, AI evidence guard, export and refresh`)
  }
}

async function ollama() {
  const session = await signIn('eureka-operator')
  const { page } = session
  await seed(session)
  await upload(page, [resolve(workspace, 'fictional_pharmacy_handoff.txt'), resolve(workspace, 'fictional_pharmacy_scan.pdf')])
  const before = await request(session, path, 200)
  await nav(page, 'Findings').click()
  const result = await generate(page, 200)
  assert.equal(result.model, process.env.DRILLLOOP_EUREKA_MODEL)
  assert.ok(result.input_tokens > 0 && result.output_tokens > 0)
  assert.deepEqual(await request(session, path, 200), before)
  const allowed = new Set(before.timeline.map(row => row.id))
  const citations = result.suggestions.flatMap(item => [...item.evidence, ...item.counterevidence])
  assert.ok(citations.every(item => allowed.has(item.observation_id)))
  await writeFile(resolve(artifacts, 'ollama-private-response.json'), JSON.stringify(result, null, 2))
  await snapshot(page, 'ollama-fictional-advisories', page.getByRole('region', { name: 'AI assistance' }))
  checks.push({
    model: result.model, latency_ms: result.latency_ms,
    input_tokens: result.input_tokens, output_tokens: result.output_tokens,
    kinds: result.suggestions.map(({ objective_id, kind }) => ({ objective_id, kind })),
    attempted_citations: result.citations_attempted, matched_citations: result.citations_matched,
    returned_citations: citations.length, exercise_state_unchanged: true,
  })
}

try {
  await ({ fictional, restart, public: publicDocuments, ollama }[mode])()
  assert.deepEqual(errors, [])
  const videos = []
  for (const { context, video, account } of videoContexts) {
    const filename = `video/${account}.webm`
    await context.close()
    await video.saveAs(resolve(artifacts, filename))
    videos.push(filename)
  }
  const summary = { mode, status: 'PASS', checks, browser_errors: errors, screenshots: captures, videos }
  await writeFile(resolve(artifacts, mode + '.json'), JSON.stringify(summary, null, 2) + '\n')
  console.log(JSON.stringify(summary))
} catch (error) {
  await Promise.allSettled(pages.filter(page => !page.isClosed()).map((page, index) =>
    page.screenshot({ path: resolve(artifacts, `failure-${mode}-${index}.png`), timeout: 2000 })))
  throw error
} finally {
  await browser.close()
}
