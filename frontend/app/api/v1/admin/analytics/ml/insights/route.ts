import { proxyMLInsights } from "@/lib/server/ml-insights-proxy.mjs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 125;

// This static route is resolved before the general external API rewrite. The
// longer deadline belongs only to ML insights; other API limits stay unchanged.
export async function GET(request: Request) {
  return proxyMLInsights(request);
}
