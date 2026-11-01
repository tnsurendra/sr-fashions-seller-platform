import {chromium} from 'playwright-core';
import {existsSync} from 'node:fs';
import {resolve} from 'node:path';

const candidates = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
].filter(Boolean);
const executablePath = candidates.find(existsSync);
if (!executablePath) throw new Error('Set CHROME_PATH to a local Chromium/Chrome executable');

const browser = await chromium.launch({headless: true, executablePath});
const page = await browser.newPage({viewport: {width: 1440, height: 1000}, deviceScaleFactor: 1});
const output = name => resolve('../docs/screenshots', `${name}.png`);
const capture = async (name, url, prepare) => {
  await page.goto(url, {waitUntil: 'networkidle'});
  if (prepare) await prepare(page);
  await page.screenshot({path: output(name), fullPage: true});
  console.log(`captured ${name}`);
};

await capture('dashboard', 'http://127.0.0.1:5173/');
await capture('products', 'http://127.0.0.1:5173/products');
await capture('add-product', 'http://127.0.0.1:5173/products/new');
await capture('inventory', 'http://127.0.0.1:5173/inventory');
await capture('orders', 'http://127.0.0.1:5173/orders', async current => {
  const detail = current.locator('details.order-detail').first();
  if (await detail.count()) await detail.locator('summary').click();
});
await capture('returns', 'http://127.0.0.1:5173/returns');
await capture('ondc-settings', 'http://127.0.0.1:5173/ondc-settings');
await capture('api-docs', 'http://127.0.0.1:8000/docs', async current => {
  await current.locator('.swagger-ui').waitFor();
});
await browser.close();
