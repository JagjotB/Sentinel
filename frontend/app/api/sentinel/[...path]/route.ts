const sentinelUrl = process.env.SENTINEL_API_URL ?? 'http://127.0.0.1:8000';
const sentinelToken = process.env.SENTINEL_API_TOKEN ?? 'sentinel-local-token';

type RouteContext = { params: Promise<{ path: string[] }> };

async function forward(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  const { path } = await context.params;
  const incoming = new URL(request.url);
  const target = new URL(
    `/${path.map(encodeURIComponent).join('/')}`,
    sentinelUrl,
  );
  target.search = incoming.search;
  const headers = new Headers({
    Accept: 'application/json',
    Authorization: `Bearer ${sentinelToken}`,
  });
  for (const name of ['content-type', 'idempotency-key', 'x-approval-token']) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const upstream = await fetch(target, {
    method: request.method,
    headers,
    body:
      request.method === 'GET' || request.method === 'HEAD'
        ? undefined
        : await request.text(),
    cache: 'no-store',
  });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      'Content-Type':
        upstream.headers.get('content-type') ?? 'application/json',
      'X-Sentinel-Upstream-Status': String(upstream.status),
    },
  });
}

export const GET = forward;
export const POST = forward;
