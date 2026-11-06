// WordPress to Next.js migration
// core module
import { WordPress } from './vendor/wordpress';
import { Nextjs } from './vendor/next.js';
import { TailwindCSS } from './vendor/tailwind-css';

export async function handler(req: Request): Promise<Response> {
  const body = await req.json();
  return Response.json({ ok: true, items: body.items?.length ?? 0 });
}
