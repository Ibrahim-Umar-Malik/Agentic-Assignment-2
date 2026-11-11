"""Map real marketplace jobs (title, Upwork skill tags, description) to GigBid's job categories.

A transparent keyword scorer, not a model: tags and title count double, the description once. Categories
with no hit fall into "other" (off-domain for all three personas). Tested in tests/unit/test_categories.py and
audited on a hand-checked sample (docs/DATA_CARD.md).
"""

from __future__ import annotations

import re

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "llm_apps": ["llm", "gpt", "chatgpt", "openai", "langchain", "langgraph", "rag", "chatbot", "large language model",
                 "prompt engineering", "ai agent", "generative ai", "vector database", "pinecone", "hugging face",
                 "llama", "claude", "gemini", "retrieval augmented", "ai assistant", "ai chatbot"],
    "computer_vision": ["computer vision", "opencv", "object detection", "yolo", "image processing", "ocr",
                        "image segmentation", "image recognition", "facial recognition", "video analytics"],
    "mlops": ["mlops", "model deployment", "mlflow", "kubeflow", "sagemaker", "vertex ai", "model serving"],
    "classic_ml": ["machine learning", "deep learning", "scikit-learn", "tensorflow", "pytorch", "keras",
                   "predictive model", "predictive modeling", "neural network", "natural language processing", "nlp",
                   "recommendation system", "classification model", "regression model", "artificial intelligence",
                   "data science", "time series forecasting", "xgboost"],
    "data_engineering": ["etl", "data engineering", "airflow", "dbt", "snowflake", "data pipeline", "bigquery",
                         "data warehouse", "apache spark", "pyspark", "databricks", "data integration", "redshift"],
    "bi_dashboards": ["power bi", "tableau", "looker", "dashboard", "data visualization", "looker studio",
                      "google data studio", "business intelligence", "qlik", "metabase"],
    "analytics_stats": ["data analysis", "data analytics", "statistics", "statistical analysis", "a/b testing",
                        "spss", "stata", "regression analysis", "r programming", "survey analysis", "quantitative analysis",
                        "sql", "data analyst", "statistical modeling"],
    "spreadsheet": ["excel", "microsoft excel", "google sheets", "spreadsheet", "vba", "excel formula", "excel macros"],
    "mobile": ["react native", "flutter", "ios development", "android development", "mobile app", "swift",
               "kotlin", "ios app", "android app"],
    "ecommerce": ["shopify", "woocommerce", "magento", "bigcommerce", "e-commerce website", "ecommerce website",
                  "shopify development", "online store"],
    "devops": ["devops", "kubernetes", "docker", "ci/cd", "terraform", "aws", "amazon web services", "azure",
               "google cloud", "linux system administration", "server administration", "github actions"],
    "frontend": ["react", "reactjs", "vue", "vue.js", "angular", "next.js", "nextjs", "front-end", "frontend",
                 "html", "css", "javascript", "typescript", "tailwind", "wordpress", "web design", "landing page",
                 "figma to html", "ui development"],
    "fullstack_saas": ["django", "flask", "fastapi", "node.js", "nodejs", "laravel", "php", "full stack", "full-stack",
                       "back-end", "backend", "api development", "rest api", "postgresql", "ruby on rails",
                       "saas", "web application", "mern", "express.js", "mongodb", "supabase", "firebase"],
}

PERSONA_CATEGORIES: dict[str, set[str]] = {
    "ai_ml": {"llm_apps", "computer_vision", "classic_ml", "mlops"},
    "fullstack": {"fullstack_saas", "frontend", "ecommerce", "mobile", "devops"},
    "data_analyst": {"bi_dashboards", "data_engineering", "analytics_stats", "spreadsheet"},
}

_RX = {c: [re.compile(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])") for k in ks] for c, ks in CATEGORY_KEYWORDS.items()}


def _hits(text: str, cat: str) -> int:
    return sum(1 for rx in _RX[cat] if rx.search(text))


def categorize(title: str, tags: list[str] | None = None, description: str = "") -> tuple[str, dict[str, float]]:
    """Best category and the per-category scores. Returns ("other", scores) when nothing matches."""
    t = str(title or "").lower()
    g = " | ".join(tags or []).lower()
    d = str(description if isinstance(description, str) else "").lower()[:4000]
    scores: dict[str, float] = {}
    strong: dict[str, int] = {}
    for cat in CATEGORY_KEYWORDS:
        th, gh, dh = _hits(t, cat), _hits(g, cat), _hits(d, cat)
        s = 2.0 * th + 2.0 * gh + 1.0 * dh
        if s:
            scores[cat] = s
            strong[cat] = th + gh
    if not scores:
        return "other", scores
    best = max(scores.items(), key=lambda kv: (kv[1], -list(CATEGORY_KEYWORDS).index(kv[0])))
    # Needs a title/tag hit, or several description mentions: one passing mention is not a category.
    if not strong[best[0]] and best[1] < 3.0:
        return "other", scores
    return best[0], scores


def persona_for(category: str) -> str | None:
    for p, cats in PERSONA_CATEGORIES.items():
        if category in cats:
            return p
    return None
