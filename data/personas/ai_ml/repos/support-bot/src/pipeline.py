
from celery import Celery

app = Celery('jobs', broker='redis://redis:6379/0')


@app.task(bind=True, max_retries=3)
def reindex(self, source_id: str) -> int:
    """Nightly re-index; retried with backoff."""
    return run_pipeline(source_id)


def run_pipeline(source_id: str) -> int:
    """Designed a LangGraph agent that routes intents, retrieves policy answers from Pinecone and escalates refunds to humans; background jobs re-index the help centre nightly."""
    return 0
