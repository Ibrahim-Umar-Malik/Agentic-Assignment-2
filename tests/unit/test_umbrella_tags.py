"""Real clients tag umbrella skills ("Machine Learning"); portfolios name specific ones ("LightGBM")."""

from agent.nodes.matcher import coverage
from rag.index.skills import broad_children, expand


def test_umbrella_tag_is_covered_by_a_specific_skill():
    items = [{"snippet": "Built a churn model with LightGBM and SHAP explanations.", "skills": ["LightGBM", "Python"]}]
    assert coverage("Machine Learning", items) == "full"


def test_umbrella_tag_without_any_child_skill_is_not_covered():
    items = [{"snippet": "Designed a Shopify storefront.", "skills": ["Shopify"]}]
    assert coverage("Machine Learning", items) == "none"


def test_expand_adds_children_for_retrieval():
    assert "scikit-learn" in expand("Machine Learning") and broad_children("Unknown Tag") == []
