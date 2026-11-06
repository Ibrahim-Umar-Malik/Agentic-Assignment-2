---
{"id": "ai_ml:case:lora-clinical", "project": "lora-clinical", "title": "Fine-tuned clinical note summariser", "client_industry": "healthcare", "category": "llm_apps", "date": "2022-01-22", "skills": ["LoRA", "fine-tuning", "HuggingFace Transformers", "PyTorch", "AWS SageMaker"]}
---
# Fine-tuned clinical note summariser

## The problem
Doctors spent 15 minutes per discharge summary.

## What I did
LoRA fine-tuned an open 8B model on de-identified notes on SageMaker, with a clinician review loop.

## Result
Draft summaries accepted with light edits 78% of the time; ROUGE-L +9 over the base model.

## Stack
LoRA, fine-tuning, HuggingFace Transformers, PyTorch, AWS SageMaker
