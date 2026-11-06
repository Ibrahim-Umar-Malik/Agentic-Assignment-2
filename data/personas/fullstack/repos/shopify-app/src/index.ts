// Shopify inventory sync app
// core module
import { ShopifyAPI } from './vendor/shopify-api';
import { Nodejs } from './vendor/node.js';
import { GraphQL } from './vendor/graphql';

export async function handler(req: Request): Promise<Response> {
  const body = await req.json();
  return Response.json({ ok: true, items: body.items?.length ?? 0 });
}
