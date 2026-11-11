"""Data pipeline helpers used to turn the Kaggle datasets into GigBid's dev sets (data_pipeline/)."""

from data_pipeline.categories import categorize, persona_for
from data_pipeline.prepare import clean_text, money
from data_pipeline.tag_competence import coverage


def test_categorize_uses_title_and_tags():
    assert categorize("Power BI dashboard for sales", ["Microsoft Power BI"])[0] == "bi_dashboards"
    assert categorize("Build a RAG chatbot over our PDFs", ["Python"])[0] == "llm_apps"
    assert categorize("Shopify theme tweaks", ["Shopify"])[0] == "ecommerce"
    assert persona_for(categorize("Machine learning model for churn", ["Machine Learning"])[0]) == "ai_ml"


def test_one_passing_mention_is_not_a_category():
    cat, _ = categorize("Logo for my bakery", ["Logo Design"], "We may add a dashboard later.")
    assert cat == "other"


def test_clean_text_scrubs_contact_details():
    s = clean_text("Mail me at jane.doe@example.com or call +1 (555) 123-4567, see https://x.example/p &amp; more")
    assert "example.com" not in s and "555" not in s and "https://" not in s and "&" in s


def test_money_parses_upwork_formats():
    assert money("$1,250.00 ") == 1250.0 and money("$75.00") == 75.0 and money(None) is None


def test_coverage_ignores_neutral_tags():
    cov, have, miss = coverage("data_analyst", ["Microsoft Excel", "Business with 1-9 Employees", "Logo Design"])
    assert have == ["Microsoft Excel"] and miss == ["Logo Design"] and cov == 0.5
