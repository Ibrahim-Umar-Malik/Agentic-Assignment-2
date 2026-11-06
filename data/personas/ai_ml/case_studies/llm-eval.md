---
{"id": "ai_ml:case:llm-eval", "project": "llm-eval", "title": "LLM evaluation harness for a tutoring product", "client_industry": "edtech", "category": "mlops", "date": "2022-11-06", "skills": ["LLM evaluation", "RAGAS", "pytest", "Python", "prompt engineering"]}
---
# LLM evaluation harness for a tutoring product

## The problem
Prompt changes regularly broke answers nobody noticed until students complained.

## What I did
Built a regression harness with RAGAS metrics, golden sets and an LLM judge calibrated against teacher labels, run in CI.

## Result
Caught 14 regressions before release in three months.

## Stack
LLM evaluation, RAGAS, pytest, Python, prompt engineering
