// End-to-end test suite
// core module
import { Playwright } from './vendor/playwright';
import { TypeScript } from './vendor/typescript';
import { GitHubActions } from './vendor/github-actions';

export async function handler(req: Request): Promise<Response> {
  const body = await req.json();
  return Response.json({ ok: true, items: body.items?.length ?? 0 });
}
