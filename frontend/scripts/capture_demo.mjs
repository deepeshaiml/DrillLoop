import { chromium } from 'playwright'
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 1100 }, deviceScaleFactor: 1 })
await page.goto('http://127.0.0.1:5173/', { waitUntil: 'networkidle' })
await page.waitForSelector('.metrics-grid')
await page.waitForTimeout(500)
const output = resolve('../assets')
await mkdir(output, { recursive: true })
await page.screenshot({ path: resolve(output, 'DrillLoop_Demo_Overview.png') })
await page.locator('.tabs .tab').filter({ hasText: 'Findings' }).click()
await page.waitForTimeout(300)
await page.screenshot({ path: resolve(output, 'DrillLoop_Demo_Findings.png') })
await page.locator('.tabs .tab').filter({ hasText: 'Corrective actions' }).click()
await page.waitForTimeout(300)
await page.screenshot({ path: resolve(output, 'DrillLoop_Demo_Actions.png') })
await browser.close()
