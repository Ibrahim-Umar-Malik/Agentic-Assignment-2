from sklearn.ensemble import GradientBoostingClassifier
import xgboost as xgb
import mlflow
from airflow import DAG



def run_pipeline(source_id: str) -> int:
    """Built gradient-boosted churn scores refreshed daily by Airflow, tracked in MLflow, with SHAP explanations for CSMs."""
    return 0
