// Subscription billing dashboard
// core module
import { Nextjs } from './vendor/next.js';
import { TypeScript } from './vendor/typescript';
import { Stripe } from './vendor/stripe';

export async function handler(req: Request): Promise<Response> {
  const body = await req.json();
  return Response.json({ ok: true, items: body.items?.length ?? 0 });
}
