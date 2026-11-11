"""A small skill ontology: canonical skill names, aliases and plain-language phrasings clients use.

Used for requirement decomposition (V1), corrective re-querying (V8) and the claim verifier. Extend it in
config rather than code if your persona has other skills: GIGBID_SKILL_ALIASES (JSON) is merged in.
"""

from __future__ import annotations

import json
import os
import re

ALIASES: dict[str, list[str]] = {
    "Celery": ["background task queue", "task queue", "background jobs", "async workers", "job queue"],
    "RAG": ["retrieval-augmented", "answers from our own documents", "chat with documents", "document q&a", "chatbot over docs"],
    "LangGraph": ["agent workflow framework", "agentic workflow", "multi-agent", "agent orchestration"],
    "LangChain": ["llm framework"],
    "pgvector": ["vector search inside postgres", "postgres vector"],
    "Pinecone": ["managed vector database", "vector database", "vector db"],
    "dbt": ["transformation models", "data build tool", "analytics engineering"],
    "Power BI": ["microsoft dashboards", "powerbi", "pbi"],
    "A/B testing": ["split testing", "split test", "experiments", "ab test", "a/b test"],
    "WebSockets": ["real-time updates", "realtime", "live updates", "socket"],
    "React Native": ["cross-platform mobile app", "ios and android app", "mobile app"],
    "Stripe": ["online payments", "subscriptions billing", "payment integration"],
    "Playwright": ["automated browser tests", "end-to-end tests", "e2e tests"],
    "LoRA": ["parameter-efficient fine-tuning", "peft", "adapter fine-tuning"],
    "YOLO": ["object detection", "detect objects"],
    "fine-tuning": ["fine-tune", "finetune", "custom model training"],
    "OCR": ["text from scanned", "extract text from images", "document extraction"],
    "Next.js": ["nextjs", "next js"],
    "Node.js": ["nodejs", "node"],
    "Google Analytics 4": ["ga4", "google analytics"],
    "Snowflake": ["cloud data warehouse"],
    "Airflow": ["scheduled pipelines", "workflow orchestration", "dags"],
    "Excel": ["spreadsheet", "spreadsheets", "xlsx"],
    "Tableau": ["tableau dashboards"],
    "forecasting": ["forecast", "predict demand", "time series"],
    "LLM agents": ["ai agent", "ai agents", "autonomous agent"],
    "Kubernetes": ["k8s"],
    "statistics": ["statistical", "significance"],
}


def _load_extra() -> dict[str, list[str]]:
    raw = os.environ.get("GIGBID_SKILL_ALIASES")
    return json.loads(raw) if raw else {}


def all_aliases() -> dict[str, list[str]]:
    out = {k: list(v) for k, v in ALIASES.items()}
    for k, v in _load_extra().items():
        out.setdefault(k, []).extend(v)
    return out


def find_skills(text: str, vocabulary: list[str]) -> list[str]:
    """Canonical skills mentioned in text, by exact name (word-bounded) or by alias phrase."""
    low = text.lower()
    found: list[str] = []
    for s in sorted(set(vocabulary) | set(ALIASES), key=len, reverse=True):
        pat = r"(?<![a-z0-9])" + re.escape(s.lower()) + r"(?![a-z0-9])"
        if re.search(pat, low):
            found.append(s)
            continue
        for a in all_aliases().get(s, []):
            if a in low:
                found.append(s)
                break
    return list(dict.fromkeys(found))


# Umbrella skill tags used on real marketplaces (from the Upwork job datasets, docs/DATA_CARD.md) and the
# specific skills that evidence them. Real clients tag "Machine Learning", not "LightGBM", so a portfolio item
# showing LightGBM counts as evidence for the umbrella tag. Found by failure analysis on real jobs.
BROAD_TAGS: dict[str, list[str]] = {
    "machine learning": ["scikit-learn", "XGBoost", "LightGBM", "PyTorch", "TensorFlow", "classification", "regression",
                         "forecasting", "churn", "recommender", "model"],
    "machine learning model": ["scikit-learn", "XGBoost", "LightGBM", "PyTorch", "TensorFlow", "classification", "model"],
    "deep learning": ["PyTorch", "TensorFlow", "neural network", "CNN", "transformer", "BERT", "YOLO"],
    "neural network": ["PyTorch", "TensorFlow", "GNN", "CNN", "two-tower"],
    "artificial neural network": ["PyTorch", "TensorFlow", "neural network"],
    "artificial intelligence": ["LLM", "machine learning", "PyTorch", "LangChain", "LangGraph", "OpenAI API", "NLP"],
    "data science": ["pandas", "scikit-learn", "statistics", "forecasting", "XGBoost", "Python"],
    "natural language processing": ["NLP", "spaCy", "BERT", "HuggingFace Transformers", "sentiment", "LLM"],
    "chatbot": ["LLM agents", "RAG", "LangGraph", "support bot", "OpenAI API"],
    "chatbot development": ["LLM agents", "RAG", "LangGraph", "OpenAI API"],
    "ai chatbot": ["LLM agents", "RAG", "LangGraph", "OpenAI API"],
    "chatgpt": ["OpenAI API", "LLM", "GPT"],
    "gpt-3": ["OpenAI API", "LLM", "GPT"],
    "openai codex": ["OpenAI API", "LLM"],
    "generative model": ["LLM", "fine-tuning", "LoRA"],
    "classification": ["classifier", "classification", "churn", "fraud", "sentiment", "LightGBM", "XGBoost"],
    "python scikit-learn": ["scikit-learn"],
    "predictive analytics": ["forecasting", "churn", "XGBoost", "LightGBM", "scikit-learn"],
    "time series analysis": ["forecasting", "Prophet", "time series"],
    "statistics": ["statistics", "statsmodels", "A/B testing", "R"],
    "computer vision": ["OpenCV", "YOLO", "OCR", "image", "defect detection"],
    "model optimization": ["hyperparameter", "quantization", "LoRA", "MLflow"],
    "model tuning": ["hyperparameter", "fine-tuning", "LoRA"],
    "data analysis": ["pandas", "SQL", "Excel", "statistics", "R", "analysis"],
    "data analytics": ["pandas", "SQL", "Excel", "statistics", "dashboard"],
    "data visualization": ["Power BI", "Tableau", "Looker", "dashboard", "matplotlib"],
    "dashboard": ["Power BI", "Tableau", "Looker", "dashboard"],
    "business intelligence": ["Power BI", "Tableau", "Looker", "dbt", "Snowflake"],
    "microsoft excel": ["Excel", "VBA", "Power Query", "spreadsheet"],
    "microsoft power bi": ["Power BI", "DAX"],
    "google data studio": ["Looker Studio", "Google Analytics 4", "dashboard"],
    "marketing analytics": ["Google Analytics 4", "marketing mix", "attribution", "A/B testing"],
    "etl pipeline": ["Airflow", "dbt", "ETL", "Snowflake"],
    "data engineering": ["Airflow", "dbt", "Snowflake", "ETL"],
    "web development": ["React", "Next.js", "Node.js", "Django", "TypeScript", "JavaScript"],
    "web design": ["React", "Next.js", "Tailwind", "CSS", "responsive"],
    "front-end development": ["React", "Next.js", "TypeScript", "CSS"],
    "back-end development": ["Node.js", "Django", "FastAPI", "PostgreSQL", "GraphQL"],
    "full-stack development": ["React", "Node.js", "Django", "PostgreSQL", "Next.js"],
    "mobile app development": ["React Native", "Expo", "mobile"],
    "ecommerce website": ["Shopify", "Stripe", "checkout"],
    "api integration": ["REST", "GraphQL", "webhook", "API"],
    "api development": ["FastAPI", "Node.js", "GraphQL", "REST"],
    "html": ["React", "Next.js", "CSS"],
    "css": ["Tailwind", "CSS", "React"],
}


def broad_children(requirement: str) -> list[str]:
    return BROAD_TAGS.get(requirement.strip().lower(), [])


def expand(requirement: str) -> str:
    """Query expansion for corrective retrieval: add canonical names for alias phrases and vice versa,
    and the specific skills behind an umbrella marketplace tag."""
    low = requirement.lower()
    extra = list(broad_children(requirement)[:5])
    for canon, aliases in all_aliases().items():
        if canon.lower() in low:
            extra.extend(aliases[:2])
        elif any(a in low for a in aliases):
            extra.append(canon)
    return requirement + (" " + " ".join(extra) if extra else "")


# General marketplace skill vocabulary (not persona-specific). Used to recognise what a job title is
# hiring for even when the freelancer has never used it, so "Need Django expert" is not scored only
# on the generic Python/PostgreSQL it also lists.
MARKET_SKILLS = [
    "Django", "Flask", "FastAPI", "Ruby on Rails", "Laravel", "PHP", "Vue", "Angular", "Svelte", "Flutter",
    "Swift", "Kotlin", "React", "React Native", "Next.js", "Node.js", "NestJS", "Express.js", "GraphQL", "MongoDB",
    "Shopify", "WordPress", "Webflow", "Unity3D", "Unreal Engine", "Solidity", "Rust", "Golang", "C#", ".NET", "Java", "Spring Boot",
    "Salesforce", "SAP", "Power BI", "Tableau", "Looker", "Snowflake", "BigQuery", "dbt", "Airflow", "Spark",
    "Kubernetes", "Terraform", "LangGraph", "LangChain", "PyTorch", "TensorFlow", "OpenCV", "YOLO", "RAG",
]
