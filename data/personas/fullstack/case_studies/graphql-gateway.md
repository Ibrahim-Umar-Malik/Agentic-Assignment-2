---
{"id": "fullstack:case:graphql-gateway", "project": "graphql-gateway", "title": "GraphQL gateway over legacy REST APIs", "client_industry": "fintech", "category": "fullstack_saas", "date": "2022-08-02", "skills": ["GraphQL", "Apollo", "Node.js", "Docker", "TypeScript"]}
---
# GraphQL gateway over legacy REST APIs

## The problem
Mobile clients made 14 REST calls to render one screen.

## What I did
Apollo GraphQL gateway with DataLoader batching and response caching, shipped in Docker.

## Result
Screen load requests from 14 to 1; p95 latency down 48%.

## Stack
GraphQL, Apollo, Node.js, Docker, TypeScript
