---
{"id": "ai_ml:case:energy-forecast", "project": "energy-forecast", "title": "Hourly energy demand forecasting", "client_industry": "energy", "category": "classic_ml", "date": "2022-08-30", "skills": ["time series", "LightGBM", "Prophet", "Airflow", "AWS"]}
---
# Hourly energy demand forecasting

## The problem
A utility over-bought reserve power because forecasts were 9% off.

## What I did
Stacked LightGBM with weather features and Prophet seasonality, retrained weekly by Airflow on AWS.

## Result
MAPE from 9.1% to 3.8%.

## Stack
time series, LightGBM, Prophet, Airflow, AWS
