/** A bounded, uncached proxy for the one long-running ML read endpoint. */
const PATH = "/api/v1/admin/analytics/ml/insights/";
const HOP_HEADERS = ["connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade", "host", "content-length", "accept-encoding"];
const RESPONSE_HEADERS = ["content-type", "content-disposition", "retry-after", "www-authenticate", "x-request-id", "location", "allow"];

function privateHeaders() {
  return new Headers({ "Cache-Control": "no-store, private, max-age=0", Pragma: "no-cache", Vary: "Cookie, Authorization", "X-Content-Type-Options": "nosniff" });
}

/** @param {number} status @param {string} code @param {string} detail */
function failure(status, code, detail) {
  return Response.json({ code, detail }, { status, headers: privateHeaders() });
}

/**
 * The destination comes only from server configuration, never request parameters.
 * Keep the timeout active while reading the body, and release the upstream socket
 * when the browser disconnects or replaces its current filter request.
 * @param {Request} request
 * @param {{backendOrigin?: string, timeoutMs?: number, fetchImpl?: typeof fetch}} [options]
 */
export async function proxyMLInsights(request, options = {}) {
  const { backendOrigin = process.env.API_INTERNAL_URL || "http://127.0.0.1:8000", timeoutMs = 120_000, fetchImpl = fetch } = options;
  if (!["GET", "HEAD"].includes(request.method)) {
    const response = failure(405, "method_not_allowed", "This endpoint only reads ML insights.");
    response.headers.set("Allow", "GET, HEAD");
    return response;
  }
  if (request.signal.aborted) return failure(499, "request_cancelled", "The insights request was cancelled.");
  let upstreamURL;
  try {
    const configured = new URL(backendOrigin);
    if (!["http:", "https:"].includes(configured.protocol) || configured.username || configured.password || configured.search || configured.hash || !Number.isFinite(timeoutMs) || timeoutMs <= 0) throw new Error("Invalid proxy configuration");
    upstreamURL = new URL(PATH, configured);
    upstreamURL.search = new URL(request.url).search;
  } catch {
    return failure(502, "insights_unavailable", "ML insights are temporarily unavailable. Please try again.");
  }

  const headers = new Headers(request.headers);
  const nominatedHopHeaders = (headers.get("connection") || "").split(",").map(value => value.trim()).filter(Boolean);
  for (const name of [...HOP_HEADERS, ...nominatedHopHeaders]) headers.delete(name);
  headers.set("Accept", "application/json");
  headers.set("X-Forwarded-Host", new URL(request.url).host);
  if (!headers.has("X-Forwarded-Proto")) headers.set("X-Forwarded-Proto", new URL(request.url).protocol.replace(":", ""));

  const controller = new AbortController();
  let timedOut = false;
  const cancelled = () => controller.abort(request.signal.reason);
  request.signal.addEventListener("abort", cancelled, { once: true });
  if (request.signal.aborted) cancelled();
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  try {
    const upstream = await fetchImpl(upstreamURL, { method: request.method, headers, signal: controller.signal, cache: "no-store", redirect: "manual" });
    const body = await upstream.arrayBuffer();
    const responseHeaders = privateHeaders();
    for (const name of RESPONSE_HEADERS) {
      const value = upstream.headers.get(name);
      if (value !== null) responseHeaders.set(name, value);
    }
    for (const cookie of upstream.headers.getSetCookie()) responseHeaders.append("Set-Cookie", cookie);
    // Native fetch decompresses bodies; transport size/encoding headers are not
    // forwarded, so the browser receives the correct decoded JSON length.
    return new Response(request.method === "HEAD" || [204, 205, 304].includes(upstream.status) ? null : body, { status: upstream.status, headers: responseHeaders });
  } catch {
    if (request.signal.aborted) return failure(499, "request_cancelled", "The insights request was cancelled.");
    if (timedOut) return failure(504, "insights_timeout", "The selected insights took too long to load. Please try again or choose a shorter date range.");
    return failure(502, "insights_unavailable", "Cannot reach the insights service. Please try again.");
  } finally {
    clearTimeout(timer);
    request.signal.removeEventListener("abort", cancelled);
  }
}
