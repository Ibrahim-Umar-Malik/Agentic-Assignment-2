"""Which REAL Upwork skill tags each synthetic persona can honestly claim.

Hand-written once, before any evaluation run, from each persona's portfolio (scripts/generate_standin_data.py):
a tag is listed only if at least one portfolio project shows that skill. It plays the role of the skills a
freelancer declares on their profile. NEUTRAL tags describe the client or the job type, not a skill, and are
ignored when measuring coverage. Labels built from this list are silver labels (see docs/DATA_CARD.md).
"""

from __future__ import annotations

NEUTRAL = {
    "business with 1-9 employees", "business with 10-99 employees", "business with 100-999 employees",
    "business with more than 1000 employees", "english", "researcher", "automation", "api", "prototyping",
    "web application", "website", "report", "communications", "analytics", "visualization", "database",
}

PERSONA_TAGS: dict[str, set[str]] = {
    "ai_ml": {
        "machine learning", "python", "data science", "artificial intelligence", "deep learning",
        "natural language processing", "tensorflow", "chatbot development", "neural network", "artificial neural network",
        "api integration", "pytorch", "machine learning model", "chatgpt", "chatbot", "model optimization",
        "computer vision", "data science consultation", "opencv", "bot development", "numpy", "model tuning", "keras",
        "python scikit-learn", "scikit-learn", "pandas", "algorithm development", "natural language generation",
        "deep neural network", "openai codex", "generative model", "gpt-3", "gpt-4", "recommendation system",
        "convolutional neural network", "feature extraction", "nltk", "amazon sagemaker", "artificial intelligence software",
        "docker", "azure openai", "ai chatbot", "langchain", "large language model", "llm", "openai api",
        "fastapi", "flask", "data analysis", "statistics", "predictive analytics", "time series analysis",
        "image processing", "object detection", "ocr", "optical character recognition", "image recognition",
        "speech recognition", "automatic speech recognition", "text classification", "sentiment analysis",
        "mlops", "mlflow", "hugging face", "transformers", "bert", "fine-tuning", "rag", "vector database",
        "pinecone", "langgraph", "prompt engineering", "ai development", "ai agent development", "xgboost",
        "lightgbm", "forecasting", "data modeling", "postgresql", "redis", "aws", "amazon web services", "kubernetes",
    },
    "fullstack": {
        "web development", "javascript", "html", "css", "html5", "css 3", "react", "reactjs", "node.js", "nodejs",
        "typescript", "next.js", "web design", "responsive design", "front-end development", "back-end development",
        "full-stack development", "api integration", "api development", "restful api", "graphql", "postgresql",
        "mongodb", "mysql", "database design", "database architecture", "django", "python", "react native",
        "mobile app development", "hybrid app development", "android", "ios", "smartphone", "tablet", "firebase",
        "shopify", "shopify apps", "shopify development", "ecommerce website", "ecommerce platform development",
        "ecommerce", "stripe", "payment gateway integration", "wordpress", "wordpress development", "website redesign",
        "website customization", "landing page", "tailwind css", "bootstrap", "jquery", "docker", "kubernetes",
        "amazon web services", "aws", "git", "user authentication", "single sign-on", "progressive web app",
        "websocket", "expressjs", "express.js", "vue.js", "figma", "ui development", "user interface design",
        "test automation", "playwright", "selenium", "ci/cd", "devops", "sql", "web application development",
    },
    "data_analyst": {
        "microsoft excel", "data analysis", "data visualization", "sql", "python", "google analytics", "dashboard",
        "microsoft power bi", "google data studio", "looker studio", "marketing analytics", "google sheets",
        "business intelligence", "data analytics", "a/b testing", "etl pipeline", "etl", "data science", "statistics",
        "r", "tableau", "microsoft sql server", "data integration", "data engineering", "spreadsheet software",
        "microsoft power bi data visualization", "microsoft power bi development", "data modeling", "apache airflow",
        "airflow", "dbt", "snowflake", "bigquery", "database design", "database architecture", "data cleansing",
        "data cleaning", "microsoft excel powerpivot", "google analytics api", "hypothesis testing", "growth analytics",
        "mysql programming", "mysql", "postgresql", "quantitative analysis", "funnel testing", "query development",
        "data interpretation", "visual basic for applications", "sql programming", "data analytics & visualization software",
        "campaign reporting", "web analytics", "financial modeling", "forecasting", "regression analysis",
        "statistical analysis", "survey data analysis", "spss", "pandas", "looker", "cohort analysis",
        "conversion rate optimization", "google optimize", "optimizely", "operations analytics", "excel formula",
        "excel macros", "pivot tables", "data mining", "data extraction", "market analysis",
    },
}


_EVIDENCED: dict[str, set[str]] = {}


def evidenced_tags(persona: str, vocab: list[str]) -> set[str]:
    """Declared tags the portfolio can actually prove: the tag (or an alias, or for an umbrella tag a specific
    skill under it) appears somewhere in the persona's portfolio files: case studies, READMEs, code, CV,
    reviews, past proposals. A declared tag with no such evidence is dropped, so a label never rewards a claim
    the Writer could not support."""
    if persona not in _EVIDENCED:
        import re
        from pathlib import Path

        from rag.index.skills import all_aliases, broad_children

        root = Path(__file__).resolve().parents[1] / "data" / "personas" / persona
        corpus = " ".join(f.read_text(errors="ignore") for f in root.rglob("*") if f.is_file()).lower()
        corpus += " " + " ".join(vocab).lower()
        aliases = {k.lower(): [a.lower() for a in v] for k, v in all_aliases().items()}

        def seen(term: str) -> bool:
            return re.search(r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?![a-z0-9])", corpus) is not None

        keep = set()
        for t in PERSONA_TAGS[persona]:
            names = [t, t.replace("microsoft ", ""), t.replace(" development", ""), t.replace("python ", "")]
            if (any(seen(n) for n in names) or any(seen(a) for a in aliases.get(t, []))
                    or any(seen(c) for c in broad_children(t))):
                keep.add(t)
        _EVIDENCED[persona] = keep
    return _EVIDENCED[persona]


def coverage(persona: str, tags: list[str], vocab: list[str] | None = None) -> tuple[float, list[str], list[str]]:
    """Share of the job's skill tags the persona can claim, and which are covered / missing."""
    allowed = evidenced_tags(persona, vocab) if vocab is not None else PERSONA_TAGS[persona]
    real = [t for t in tags if t.lower() not in NEUTRAL]
    if not real:
        return 0.0, [], []
    have = [t for t in real if t.lower() in allowed]
    miss = [t for t in real if t.lower() not in allowed]
    return len(have) / len(real), have, miss
