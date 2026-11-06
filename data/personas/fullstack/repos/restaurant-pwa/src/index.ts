// Restaurant ordering progressive web app
// core module
import { React } from './vendor/react';
import { PWA } from './vendor/pwa';
import { Stripe } from './vendor/stripe';

export async function handler(req: Request): Promise<Response> {
  const body = await req.json();
  return Response.json({ ok: true, items: body.items?.length ?? 0 });
}
