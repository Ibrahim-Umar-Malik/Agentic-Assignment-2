---
{"id": "ai_ml:case:vector-migration", "project": "vector-migration", "title": "Semantic search migration to Pinecone", "client_industry": "media", "category": "llm_apps", "date": "2023-04-26", "skills": ["Pinecone", "Elasticsearch", "embeddings", "semantic search", "Python"]}
---
# Semantic search migration to Pinecone

## The problem
Keyword search on a 2M-article archive returned poor results for natural questions.

## What I did
Migrated to hybrid semantic search on Pinecone with a re-ranker, keeping BM25 for exact names.

## Result
Search success rate up 27%; p95 latency 180 ms.

## Stack
Pinecone, Elasticsearch, embeddings, semantic search, Python
