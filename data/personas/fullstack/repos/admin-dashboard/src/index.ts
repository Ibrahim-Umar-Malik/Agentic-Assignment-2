// Logistics admin dashboard
// core module
import { React } from './vendor/react';
import { TypeScript } from './vendor/typescript';
import { NestJS } from './vendor/nestjs';

export async function handler(req: Request): Promise<Response> {
  const body = await req.json();
  return Response.json({ ok: true, items: body.items?.length ?? 0 });
}
