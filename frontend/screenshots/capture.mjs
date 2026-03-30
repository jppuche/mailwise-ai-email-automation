// Playwright screenshot capture for visual validation
// Uses JS-based navigation to avoid mobile sidebar drawer issues
import { chromium } from "playwright";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const BASE_URL = "http://localhost:5173";
const OUT_DIR = __dirname;

const VIEWPORTS = [
  { name: "mobile", width: 375, height: 812 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "desktop", width: 1280, height: 900 },
];

const THEMES = ["light", "dark"];

const AUTH_PAGES = [
  { name: "overview", path: "/" },
  { name: "emails", path: "/emails" },
  { name: "analytics", path: "/analytics" },
  { name: "review", path: "/review" },
];

// ── Properly encoded mock JWT ──
function makeJwt() {
  const header = Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString("base64url");
  const payload = Buffer.from(JSON.stringify({ sub: "admin", exp: 4102444800 })).toString("base64url");
  return `${header}.${payload}.mock-signature`;
}

const MOCK_TOKEN = { access_token: makeJwt(), refresh_token: "mock-refresh-token", token_type: "bearer" };
const MOCK_USER = { id: "u-001", username: "admin", role: "admin", is_active: true };

const MOCK_EMAILS = {
  items: [
    { id: "e-001", sender_name: "John Smith", sender_email: "john@acme.com", subject: "Q4 Revenue Report - Final Draft", snippet: "Please review the attached Q4 revenue report...", received_at: "2026-03-02T09:30:00Z", state: "classified", classification: { action_name: "review_required", display_name: "Review Required", confidence: 0.94 } },
    { id: "e-002", sender_name: "Sarah Connor", sender_email: "sarah@techcorp.io", subject: "Partnership Proposal - Cloud Migration", snippet: "We would like to discuss a potential partnership...", received_at: "2026-03-02T08:15:00Z", state: "routed", classification: { action_name: "urgent", display_name: "Urgent", confidence: 0.87 } },
    { id: "e-003", sender_name: "Alex Rivera", sender_email: "alex@startup.dev", subject: "Feature Request: API Rate Limiting", snippet: "Our team has been using your API extensively...", received_at: "2026-03-01T16:45:00Z", state: "draft_sent", classification: { action_name: "feature_request", display_name: "Feature Request", confidence: 0.91 } },
    { id: "e-004", sender_name: "Marketing Team", sender_email: "marketing@company.com", subject: "Newsletter Draft - March Edition", snippet: "Here's the draft for our March newsletter...", received_at: "2026-03-01T14:00:00Z", state: "archived", classification: { action_name: "informational", display_name: "Informational", confidence: 0.98 } },
    { id: "e-005", sender_name: "Support Bot", sender_email: "support@helpdesk.io", subject: "Ticket #4521 - Login Issues Resolved", snippet: "The login issue has been resolved...", received_at: "2026-03-01T11:20:00Z", state: "classified", classification: { action_name: "support", display_name: "Support", confidence: 0.76 } },
  ],
  total: 142, page: 1, page_size: 20, pages: 8,
};

const MOCK_VOLUME = {
  data_points: Array.from({ length: 28 }, (_, i) => ({ date: `2026-02-${String(i + 1).padStart(2, "0")}`, count: Math.floor(30 + Math.random() * 40) })),
  total_emails: 1284, start_date: "2026-02-01", end_date: "2026-02-28",
};

const MOCK_DISTRIBUTION = { total_classified: 1156, actions: [
  { action_name: "urgent", display_name: "Urgent", count: 89 },
  { action_name: "review_required", display_name: "Review Required", count: 234 },
  { action_name: "informational", display_name: "Informational", count: 412 },
  { action_name: "support", display_name: "Support", count: 178 },
  { action_name: "feature_request", display_name: "Feature Request", count: 156 },
  { action_name: "spam", display_name: "Spam", count: 87 },
]};

const MOCK_ACCURACY = { total_classified: 1156, total_overridden: 42, accuracy_pct: 96.4, period_start: "2026-02-01", period_end: "2026-03-02" };

const MOCK_ROUTING = { total_dispatched: 823, channels: [
  { channel: "Slack #urgent", dispatched: 89, failed: 2 },
  { channel: "Slack #support", dispatched: 178, failed: 5 },
  { channel: "Email Forward", dispatched: 234, failed: 3 },
  { channel: "HubSpot CRM", dispatched: 156, failed: 1 },
  { channel: "Archive", dispatched: 166, failed: 0 },
]};

const MOCK_HEALTH = { status: "ok", adapters: [
  { name: "Gmail", status: "ok", latency_ms: 120, error: null },
  { name: "Slack", status: "ok", latency_ms: 85, error: null },
  { name: "HubSpot", status: "degraded", latency_ms: 450, error: "High latency" },
  { name: "LLM (GPT-4)", status: "ok", latency_ms: 200, error: null },
]};

const MOCK_REVIEW_QUEUE = { items: [
  { id: "r-001", email_id: "e-001", subject: "Q4 Revenue Report", sender_email: "john@acme.com", classification: { action_name: "review_required", display_name: "Review Required", confidence: 0.94 }, draft_body: "Thank you for the Q4 Report.", created_at: "2026-03-02T09:31:00Z" },
  { id: "r-002", email_id: "e-002", subject: "Partnership Proposal", sender_email: "sarah@techcorp.io", classification: { action_name: "urgent", display_name: "Urgent", confidence: 0.87 }, draft_body: "Thank you for reaching out.", created_at: "2026-03-02T08:16:00Z" },
], total: 8, page: 1, page_size: 20, pages: 1 };

// ── Route matching ──
function getApiMockResponse(url) {
  const path = new URL(url).pathname;
  if (path.includes("/auth/login")) return MOCK_TOKEN;
  if (path.includes("/auth/me")) return MOCK_USER;
  if (path.includes("/auth/refresh")) return MOCK_TOKEN;
  if (path.includes("/analytics/volume")) return MOCK_VOLUME;
  if (path.includes("/analytics/classification-distribution")) return MOCK_DISTRIBUTION;
  if (path.includes("/analytics/accuracy")) return MOCK_ACCURACY;
  if (path.includes("/analytics/routing")) return MOCK_ROUTING;
  if (path.includes("/health")) return MOCK_HEALTH;
  if (path.includes("/emails")) return MOCK_EMAILS;
  if (path.includes("/review") || path.includes("/drafts")) return MOCK_REVIEW_QUEUE;
  return {};
}

async function setupMockRoutes(page) {
  await page.route(
    (url) => (typeof url === "string" ? url : url.toString()).includes("/api/v1/"),
    (route) => {
      const body = getApiMockResponse(route.request().url());
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    }
  );
}

async function setTheme(page, theme) {
  await page.evaluate((t) => {
    document.documentElement.classList.remove("light", "dark");
    document.documentElement.classList.add(t);
    localStorage.setItem("theme", t);
  }, theme);
  await page.waitForTimeout(300);
}

// Navigate by programmatically clicking the sidebar link via JS (avoids pointer event issues)
async function navigateViaLink(page, path) {
  await page.evaluate((p) => {
    const link = document.querySelector(`a[href="${p}"]`);
    if (link) link.click();
  }, path);
  await page.waitForTimeout(1500);
}

async function captureScreenshot(page, pageName, viewport, theme) {
  const filename = `${pageName}-${viewport.name}-${theme}.png`;
  // Scroll to bottom first to ensure all content is in the viewport
  // (fullPage stitching can miss SVG path elements below the fold)
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.waitForTimeout(200);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(200);
  await page.screenshot({ path: join(OUT_DIR, filename), fullPage: true });
  console.log(`  captured: ${filename}`);
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  let count = 0;

  for (const viewport of VIEWPORTS) {
    for (const theme of THEMES) {
      const context = await browser.newContext({
        viewport: { width: viewport.width, height: viewport.height },
      });
      const page = await context.newPage();
      await setupMockRoutes(page);

      // 1. Capture login
      console.log(`[${viewport.name}/${theme}] login`);
      await page.goto(`${BASE_URL}/login`, { waitUntil: "networkidle", timeout: 15000 });
      await setTheme(page, theme);
      await captureScreenshot(page, "login", viewport, theme);
      count++;

      // 2. Login
      await page.fill("#username", "admin");
      await page.fill("#password", "admin123");
      await page.click('button[type="submit"]');
      await page.waitForTimeout(2000);

      if (page.url().includes("/login")) {
        console.log(`  auth FAILED — skipping`);
        await context.close();
        continue;
      }

      await setTheme(page, theme);

      // 3. Capture auth pages
      for (const pg of AUTH_PAGES) {
        console.log(`[${viewport.name}/${theme}] ${pg.name}`);
        const cur = new URL(page.url()).pathname;
        if (cur !== pg.path) {
          await navigateViaLink(page, pg.path);
        }
        await setTheme(page, theme);
        // Wait for recharts SVG to render (ResponsiveContainer needs layout time)
        await page.waitForTimeout(pg.name === "overview" ? 1500 : 500);
        await captureScreenshot(page, pg.name, viewport, theme);
        count++;
      }

      await context.close();
    }
  }

  await browser.close();
  console.log(`\nDone! ${count} screenshots`);
}

main().catch(console.error);
