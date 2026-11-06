// Clinic appointment booking system
// core module
import { Nextjs } from './vendor/next.js';
import { Supabase } from './vendor/supabase';
import { TailwindCSS } from './vendor/tailwind-css';

export async function handler(req: Request): Promise<Response> {
  const body = await req.json();
  return Response.json({ ok: true, items: body.items?.length ?? 0 });
}
