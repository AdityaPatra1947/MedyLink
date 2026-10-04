import assert from "node:assert/strict";
import { createServer } from "node:http";
import { once } from "node:events";
import { test } from "node:test";
import { proxyMLInsights } from "../lib/server/ml-insights-proxy.mjs";

const request = (options = {}) => new Request("http://localhost:3001/api/v1/admin/analytics/ml/insights/?dataset_id=fixture&disease_codes=DENGUE%2CASTHMA&date_from=2025-01-01", options);

async function stub(t, handle) {
  const server = createServer(handle);
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  t.after(() => { server.closeAllConnections(); server.close(); });
  return `http://127.0.0.1:${server.address().port}`;
}

test("fixed upstream preserves query, session cookies and authorization without client-host routing", async t => {
  let received;
  const origin = await stub(t, (req, res) => {
    received = { url: req.url, headers: req.headers };
    res.writeHead(200, { "Content-Type": "application/json", "Set-Cookie": ["first=one; HttpOnly", "second=two; HttpOnly"], "X-Request-ID": "test-request", "Cache-Control": "public, max-age=500" });
    res.end(JSON.stringify({ ok: true }));
  });
  const response = await proxyMLInsights(request({ headers: { Cookie: "access_token=private-session", Authorization: "Bearer private-token", "X-Forwarded-Proto": "https", Host: "attacker.invalid", Connection: "close, x-transport-only", "X-Transport-Only": "remove-me" } }), { backendOrigin: origin });
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { ok: true });
  assert.equal(received.url, "/api/v1/admin/analytics/ml/insights/?dataset_id=fixture&disease_codes=DENGUE%2CASTHMA&date_from=2025-01-01");
  assert.equal(received.headers.cookie, "access_token=private-session");
  assert.equal(received.headers.authorization, "Bearer private-token");
  assert.equal(received.headers["x-forwarded-proto"], "https");
  assert.equal(received.headers["x-forwarded-host"], "localhost:3001");
  assert.equal(received.headers["x-transport-only"], undefined);
  assert.notEqual(received.headers.host, "attacker.invalid");
  assert.match(response.headers.get("cache-control"), /no-store/);
  assert.equal(response.headers.get("x-request-id"), "test-request");
  assert.deepEqual(response.headers.getSetCookie(), ["first=one; HttpOnly", "second=two; HttpOnly"]);
});

for (const status of [400, 401, 403, 429, 500]) {
  test(`preserves upstream ${status} and its structured error`, async t => {
    const origin = await stub(t, (_req, res) => { res.writeHead(status, { "Content-Type": "application/json", "Retry-After": "5" }); res.end(JSON.stringify({ detail: "Backend decision." })); });
    const response = await proxyMLInsights(request(), { backendOrigin: origin });
    assert.equal(response.status, status);
    assert.deepEqual(await response.json(), { detail: "Backend decision." });
    assert.match(response.headers.get("cache-control"), /no-store/);
    assert.equal(response.headers.get("retry-after"), "5");
  });
}

test("deadline includes a stalled response body and returns safe JSON 504", async t => {
  const origin = await stub(t, (_req, res) => { res.writeHead(200, { "Content-Type": "application/json" }); res.write('{"pending":'); });
  const response = await proxyMLInsights(request(), { backendOrigin: origin, timeoutMs: 100 });
  assert.equal(response.status, 504);
  const body = await response.json();
  assert.equal(body.code, "insights_timeout");
  assert.doesNotMatch(JSON.stringify(body), /127\.0\.0\.1|ECONN|stack/i);
});

test("browser disconnect aborts the active upstream request", async t => {
  let began, closed;
  const started = new Promise(resolve => { began = resolve; });
  const disconnected = new Promise(resolve => { closed = resolve; });
  const origin = await stub(t, (_req, res) => { res.on("close", closed); began(); });
  const controller = new AbortController();
  const pending = proxyMLInsights(request({ signal: controller.signal }), { backendOrigin: origin });
  await started;
  controller.abort();
  const response = await pending;
  assert.equal(response.status, 499);
  assert.equal((await response.json()).code, "request_cancelled");
  await disconnected;
});

test("connection failure returns safe JSON 502", async () => {
  const response = await proxyMLInsights(request(), { backendOrigin: "http://127.0.0.1:1" });
  assert.equal(response.status, 502);
  assert.equal((await response.json()).code, "insights_unavailable");
});

test("redirects do not forward private credentials to a second destination", async t => {
  let secondRequests = 0;
  const second = await stub(t, (_req, res) => { secondRequests++; res.end("unexpected"); });
  const first = await stub(t, (_req, res) => { res.writeHead(307, { Location: second + "/other" }); res.end(); });
  const response = await proxyMLInsights(request({ headers: { Cookie: "access_token=private-session" } }), { backendOrigin: first });
  assert.equal(response.status, 307);
  assert.equal(secondRequests, 0);
});

test("already cancelled reads and non-read methods never contact the backend", async () => {
  let calls = 0;
  const options = { fetchImpl: async () => { calls++; throw new Error("should not run"); } };
  const cancelled = new AbortController(); cancelled.abort();
  assert.equal((await proxyMLInsights(request({ signal: cancelled.signal }), options)).status, 499);
  assert.equal((await proxyMLInsights(request({ method: "POST", body: "{}" }), options)).status, 405);
  assert.equal(calls, 0);
});

test("real upstream response over thirty seconds succeeds within the ML deadline", { skip: process.env.RUN_ML_PROXY_SLOW_TEST !== "true", timeout: 45_000 }, async t => {
  const origin = await stub(t, (_req, res) => { const timer = setTimeout(() => { res.writeHead(200, { "Content-Type": "application/json" }); res.end('{"slow_success":true}'); }, 31_100); res.on("close", () => clearTimeout(timer)); });
  const started = Date.now();
  const response = await proxyMLInsights(request(), { backendOrigin: origin });
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { slow_success: true });
  assert.ok(Date.now() - started >= 30_000);
});
