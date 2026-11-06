---
{"id": "ai_ml:case:churn-model", "project": "churn-model", "title": "Subscription churn prediction", "client_industry": "SaaS", "category": "classic_ml", "date": "2021-10-04", "skills": ["scikit-learn", "XGBoost", "MLflow", "Airflow", "Python", "feature engineering"]}
---
# Subscription churn prediction

## The problem
A B2B SaaS lost 4% of accounts a month with no early warning.

## What I did
Built gradient-boosted churn scores refreshed daily by Airflow, tracked in MLflow, with SHAP explanations for CSMs.

## Result
AUC 0.87; retention team saved an estimated $310k ARR in two quarters.

## Stack
scikit-learn, XGBoost, MLflow, Airflow, Python, feature engineering
