// HTML 시안 → PNG. data-out="파일명.png" 이 붙은 요소를 하나씩 캡처한다.
// 사용: node tools/render_thumbs.cjs output/키워드/thumbs.html [출력폴더]
const { chromium } = require('playwright');
const path = require('node:path');
const fs = require('node:fs');

(async () => {
  const [, , htmlPath, outArg] = process.argv;
  if (!htmlPath) {
    console.error('usage: node tools/render_thumbs.cjs <page.html> [outDir]');
    process.exit(1);
  }
  const outDir = outArg || path.dirname(htmlPath);
  fs.mkdirSync(outDir, { recursive: true });

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1200, height: 1200 } });
  await page.goto('file://' + path.resolve(htmlPath), { waitUntil: 'networkidle' });
  await page.evaluate(() => document.fonts.ready);
  for (const el of await page.$$('[data-out]')) {
    const file = path.join(outDir, await el.getAttribute('data-out'));
    await el.screenshot({ path: file });
    console.log(file);
  }
  await browser.close();
})();
