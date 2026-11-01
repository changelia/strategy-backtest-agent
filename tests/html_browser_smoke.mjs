// Opt-in verification: node tests/html_browser_smoke.mjs PLAYWRIGHT_MODULE WORK EVIDENCE
// PLAYWRIGHT_MODULE identifies an already installed development-only playwright package.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';

const [modulePath, workArg, evidenceArg] = process.argv.slice(2);
assert(modulePath && workArg && evidenceArg, 'Supply module, fixtures and evidence paths');
const require = createRequire(import.meta.url);
const { chromium } = require(resolve(modulePath));
const work = resolve(workArg), evidence = resolve(evidenceArg);
await mkdir(evidence, { recursive: true });
const browser = await chromium.launch({ headless: true, args: ['--disable-background-networking'] });
const receipt = { browser: browser.version(), playwright: require(join(resolve(modulePath), 'package.json')).version,
  platform: process.platform, javascript_enabled: false, external_requests: [], page_errors: [],
  checks: [], screenshots: {} };
try {
  for (const mode of ['desktop', 'narrow', 'print']) {
    const viewport = mode === 'narrow' ? { width: 390, height: 844 } : { width: 1440, height: 1000 };
    const context = await browser.newContext({ viewport, deviceScaleFactor: 1,
      javaScriptEnabled: false, serviceWorkers: 'block', locale: 'en-US', timezoneId: 'UTC', colorScheme: 'light' });
    await context.route('**/*', async route => {
      const url = route.request().url();
      if (url.startsWith(pathToFileURL(work + '/').href)) await route.continue();
      else { receipt.external_requests.push(url); await route.abort(); }
    });
    for (const kind of ['backtest', 'comparison', 'validation', 'sensitivity', 'costs', 'walk_forward', 'edge', 'panels']) {
      const page = await context.newPage();
      page.on('pageerror', error => receipt.page_errors.push(error.message));
      page.on('console', message => {
        if (message.type() === 'error') receipt.page_errors.push(message.text());
      });
      page.on('request', request => {
        if (!request.url().startsWith(pathToFileURL(work + '/').href)) receipt.external_requests.push(request.url());
      });
      await page.emulateMedia({ media: mode === 'print' ? 'print' : 'screen' });
      const file = join(work, `${kind}.html`);
      await page.goto(pathToFileURL(file).href, { waitUntil: 'load' });
      await page.locator('style').waitFor({ state: 'attached' });
      assert.equal(await page.locator('script,link,iframe,img,object,embed,form,input').count(), 0);
      assert(await page.locator('meta[http-equiv="Content-Security-Policy"]').count());
      const layout = await page.evaluate(() => ({ width: innerWidth,
        scrollWidth: document.documentElement.scrollWidth,
        sectionBackground: getComputedStyle(document.querySelector('section')).backgroundColor,
        chartCount: document.querySelectorAll('svg').length,
        keyOverflow: [...document.querySelectorAll('dt')].some(n => n.scrollWidth > n.clientWidth + 1),
        rows: document.querySelectorAll('.metrics tbody tr').length,
        fonts: getComputedStyle(document.body).fontFamily,
        text: document.body.textContent }));
      assert(layout.scrollWidth <= layout.width + 1, `${kind}/${mode}: horizontal document overflow`);
      assert.equal(layout.sectionBackground, 'rgb(255, 255, 255)', 'Hashed CSS did not load');
      assert.equal(layout.keyOverflow, false, 'Provenance label overflow');
      assert(layout.chartCount > 0 && layout.rows > 0);
      if (kind === 'edge') assert(layout.text.includes('<script>alert(1)</script>'));
      if (kind === 'panels') assert.equal(layout.chartCount, 2);
      receipt.checks.push({ kind, mode, viewport, chart_count: layout.chartCount,
        metric_rows: layout.rows, font_family: layout.fonts, horizontal_overflow: false,
        html_sha256: createHash('sha256').update(await readFile(file)).digest('hex') });
      if (kind === 'comparison' || (kind === 'edge' && mode === 'narrow') || (kind === 'costs' && mode === 'desktop')) {
        const name = `${kind}-${mode}.png`;
        await page.screenshot({ path: join(evidence, name) });
        receipt.screenshots[name] = createHash('sha256').update(await readFile(join(evidence, name))).digest('hex');
        await page.locator('figure').first().evaluate(el => el.scrollIntoView({ block: 'start' }));
        const chartsName = `${kind}-${mode}-charts.png`;
        await page.screenshot({ path: join(evidence, chartsName) });
        receipt.screenshots[chartsName] = createHash('sha256').update(await readFile(join(evidence, chartsName))).digest('hex');
        if (mode === 'narrow') {
          await page.locator('.chart-scroll').first().evaluate(el => { el.scrollLeft = el.scrollWidth - el.clientWidth; });
          const marksName = `${kind}-${mode}-marks.png`;
          await page.screenshot({ path: join(evidence, marksName) });
          receipt.screenshots[marksName] = createHash('sha256').update(await readFile(join(evidence, marksName))).digest('hex');
        }
        if (kind === 'costs') {
          await page.locator('figure').last().evaluate(el => el.scrollIntoView({ block: 'start' }));
          const costName = 'costs-components.png';
          await page.screenshot({ path: join(evidence, costName) });
          receipt.screenshots[costName] = createHash('sha256').update(await readFile(join(evidence, costName))).digest('hex');
        }

      }
      if (kind === 'edge' && mode === 'narrow') {
        await page.getByRole('heading', { name: /^R1/ }).first().evaluate(el => el.scrollIntoView({ block: 'start' }));
        const labelName = 'edge-narrow-label.png';
        await page.screenshot({ path: join(evidence, labelName) });
        receipt.screenshots[labelName] = createHash('sha256').update(await readFile(join(evidence, labelName))).digest('hex');
      }
      if (mode === 'print' && kind === 'comparison') {
        const pdf = await page.pdf({ format: 'A4', printBackground: true,
          displayHeaderFooter: false, margin: { top: '12mm', bottom: '12mm', left: '10mm', right: '10mm' } });
        await writeFile(join(work, 'comparison-print.pdf'), pdf);
        receipt.print_pdf_bytes = pdf.length;
        assert(pdf.length > 10000);
      }
      await page.close();
    }
    await context.close();
  }
  assert.deepEqual(receipt.external_requests, []);
  assert.deepEqual(receipt.page_errors, []);
  receipt.status = 'READY';
  await writeFile(join(evidence, 'browser-receipt.json'), JSON.stringify(receipt, null, 2) + '\n');
  console.log(JSON.stringify({ status: receipt.status, browser: receipt.browser,
    checks: receipt.checks.length, external_requests: 0, screenshots: Object.keys(receipt.screenshots).length }));
} finally { await browser.close(); }
