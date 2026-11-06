---
{"id": "ai_ml:case:invoice-ocr", "project": "invoice-ocr", "title": "Invoice field extraction pipeline", "client_industry": "fintech", "category": "computer_vision", "date": "2021-07-09", "skills": ["LayoutLM", "HuggingFace Transformers", "PyTorch", "FastAPI", "Docker", "OCR"]}
---
# Invoice field extraction pipeline

## The problem
An accounts-payable team keyed 20 fields from 4,000 supplier invoices a month.

## What I did
Fine-tuned LayoutLMv3 on 1,200 labelled invoices and served it behind a FastAPI endpoint in Docker.

## Result
Field-level F1 of 0.94; manual keying time down 70%.

## Stack
LayoutLM, HuggingFace Transformers, PyTorch, FastAPI, Docker, OCR
