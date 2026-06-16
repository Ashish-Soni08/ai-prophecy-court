import { chromium } from "@playwright/test";
import { spawn, spawnSync } from "node:child_process";
import { mkdir, rename } from "node:fs/promises";
import { join, resolve } from "node:path";

const root = resolve(import.meta.dirname, "../../..");
const outputDir = resolve(import.meta.dirname, "../demo-output");
const baseURL = "http://127.0.0.1:7860";

await mkdir(outputDir, { recursive: true });

const server = spawn(
  "uv",
  ["run", "--project", root, "--extra", "space", "python", "space/app.py"],
  { cwd: root, shell: true, stdio: ["ignore", "pipe", "pipe"] },
);

const logs = [];
server.stdout.on("data", (chunk) => logs.push(chunk.toString()));
server.stderr.on("data", (chunk) => logs.push(chunk.toString()));

try {
  await waitForServer(`${baseURL}/api/bootstrap`, 180_000);
  const browser = await chromium.launch({ channel: "chrome" });
  const context = await browser.newContext({
    baseURL,
    viewport: { width: 1440, height: 1100 },
    recordVideo: { dir: outputDir, size: { width: 1440, height: 1100 } },
  });
  const page = await context.newPage();

  await page.goto("/");
  await page.waitForTimeout(1400);
  await page.getByRole("button", { name: "Dad joke" }).click();
  await page.waitForTimeout(600);
  await page.getByRole("button", { name: "Convene Court" }).click();
  await page.getByText("Model identity sealed").first().waitFor();
  await page.waitForTimeout(1600);
  await page.getByRole("button", { name: "A wins" }).click();
  await page.getByText("Model identities unsealed").waitFor();
  await page.waitForTimeout(1400);
  await page.getByRole("button", { name: "Generate verdict card" }).click();
  await page.getByRole("heading", { name: "Your verdict card is ready." }).waitFor();
  await page.waitForTimeout(1800);
  await page.getByRole("link", { name: "Open dossier" }).nth(4).click();
  await page.waitForURL("**/people/clement-delangue");
  await page.waitForTimeout(1200);
  await page.getByRole("link", { name: "Archive" }).click();
  await page.waitForURL("**/archive");
  await page.waitForTimeout(1200);

  const video = page.video();
  await context.close();
  await browser.close();

  if (!video) throw new Error("Playwright did not create a video artifact.");
  const finalPath = join(outputDir, "ai-prophecy-court-demo.webm");
  await rename(await video.path(), finalPath);
  console.log(`Demo video written to ${finalPath}`);
} finally {
  stopServer(server);
}

async function waitForServer(url, timeoutMs) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // Server is still booting.
    }
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 1500));
  }
  throw new Error(
    `Server did not become ready. Recent logs:\n${logs.slice(-20).join("")}`,
  );
}

function stopServer(child) {
  child.stdout.destroy();
  child.stderr.destroy();
  if (!child.pid) return;
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], {
      stdio: "ignore",
    });
  } else {
    child.kill("SIGTERM");
  }
}
