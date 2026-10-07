// Render index.html to MP4 frame by frame (deterministic: each frame seeks the GSAP timeline).
//   node render.cjs            -> out/mindsel-showcase.mp4 (+ cover.jpg)
//   node render.cjs --stills   -> out/stills/*.png at a few key times
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");
let playwright;
try { playwright = require("playwright"); } catch { playwright = require("/opt/node22/lib/node_modules/playwright"); }

const FPS = 30, DUR = 15, W = 1080, H = 1920;
const HERE = __dirname, OUT = path.join(HERE, "out");
const STILLS = [0, 1.4, 2.65, 3.1, 4.4, 7.5, 9.5, 10.55, 12.4, 14.1];

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await playwright.chromium.launch({
    executablePath: fs.existsSync("/opt/pw-browsers/chromium") ? undefined : undefined,
    args: ["--allow-file-access-from-files", "--force-color-profile=srgb"],
  });
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  await page.goto("file://" + path.join(HERE, "index.html"));
  await page.evaluate(() => window.ready);

  const shot = async (t) => {
    await page.evaluate((t) => window.renderAt(t), t);
    return page.screenshot({ type: "png" });
  };

  if (process.argv.includes("--stills")) {
    const dir = path.join(OUT, "stills");
    fs.mkdirSync(dir, { recursive: true });
    // walk the timeline forward so callbacks/relative tweens resolve as in the real render
    let i = 0;
    for (let f = 0; f <= DUR * FPS; f++) {
      const t = f / FPS;
      if (i < STILLS.length && t >= STILLS[i] - 1e-6) {
        fs.writeFileSync(path.join(dir, `t${STILLS[i].toFixed(2)}.png`), await shot(t));
        i++;
      } else {
        await page.evaluate((t) => window.renderAt(t), t);
      }
    }
    await browser.close();
    return;
  }

  const silent = path.join(OUT, "video-only.mp4");
  const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(FPS), "-i", "-",
    "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart", silent],
    { stdio: ["pipe", "inherit", "inherit"] });
  const frames = DUR * FPS;
  for (let f = 0; f < frames; f++) {
    const buf = await shot(f / FPS);
    if (f === Math.round(7.6 * FPS)) fs.writeFileSync(path.join(OUT, "cover.png"), buf);
    if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once("drain", r));
    if (f % 30 === 0) process.stdout.write(`\rframe ${f}/${frames}`);
  }
  ff.stdin.end();
  await new Promise((r) => ff.on("close", r));
  await browser.close();
  console.log("\nvideo done:", silent);
})();
