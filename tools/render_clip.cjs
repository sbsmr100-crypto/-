// 클립 HTML → 무음 MP4. 페이지의 window.renderAt(t)로 프레임을 그려 #stage를 캡처하고 ffmpeg로 인코딩한다.
// 사용: node tools/render_clip.cjs output/키워드/clip.html <길이초> [출력.mp4] [fps]
const { chromium } = require('playwright');
const { spawn } = require('node:child_process');
const path = require('node:path');

(async () => {
  const [, , htmlPath, durArg, outArg, fpsArg] = process.argv;
  if (!htmlPath || !durArg) {
    console.error('usage: node tools/render_clip.cjs <clip.html> <seconds> [out.mp4] [fps]');
    process.exit(1);
  }
  const dur = +durArg, fps = +(fpsArg || 30);
  const out = outArg || path.join(path.dirname(htmlPath), 'clip.mp4');

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1200, height: 2000 } });
  await page.goto('file://' + path.resolve(htmlPath), { waitUntil: 'networkidle' });
  await page.evaluate(() => document.fonts.ready);
  const stage = await page.$('#stage');

  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-i', '-',
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out],
    { stdio: ['pipe', 'inherit', 'inherit'] });

  const n = Math.round(dur * fps);
  for (let i = 0; i < n; i++) {
    await page.evaluate(async t => {
      window.renderAt(t);
      await Promise.all([...document.images].map(im => im.decode().catch(() => {})));
    }, i / fps);
    const buf = await stage.screenshot({ type: 'jpeg', quality: 95 });
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if (i % (fps * 5) === 0) console.log(`${(i / fps).toFixed(0)}s / ${dur}s`);
  }
  ff.stdin.end();
  await new Promise(r => ff.on('close', r));
  await browser.close();
  console.log(out);
})();
