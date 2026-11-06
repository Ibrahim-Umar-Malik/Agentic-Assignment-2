// Live crypto price dashboard
// core module
import { WebSockets } from './vendor/websockets';
import { React } from './vendor/react';
import { D3js } from './vendor/d3.js';

export async function handler(req: Request): Promise<Response> {
  const body = await req.json();
  return Response.json({ ok: true, items: body.items?.length ?? 0 });
}
