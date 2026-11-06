---
{"id": "ai_ml:case:doc-classifier", "project": "doc-classifier", "title": "Insurance document classifier", "client_industry": "insurance", "category": "mlops", "date": "2023-02-23", "skills": ["BERT", "PyTorch", "Docker", "Kubernetes", "MLOps"]}
---
# Insurance document classifier

## The problem
Claims documents were sorted into 27 types by hand.

## What I did
Fine-tuned a BERT classifier and deployed it on Kubernetes with canary releases and drift monitoring.

## Result
97.2% accuracy; triage time from 2 days to 2 hours.

## Stack
BERT, PyTorch, Docker, Kubernetes, MLOps
