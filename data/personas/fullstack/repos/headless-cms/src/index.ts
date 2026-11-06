// Headless CMS migration for a publisher
// core module
import { Nextjs } from './vendor/next.js';
import { Sanity } from './vendor/sanity';
import { Vercel } from './vendor/vercel';

export async function handler(req: Request): Promise<Response> {
  const body = await req.json();
  return Response.json({ ok: true, items: body.items?.length ?? 0 });
}
