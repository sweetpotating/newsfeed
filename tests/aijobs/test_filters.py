from aijobs.filters import is_ai_role, is_singapore, role_tags


def test_singapore_basic_variants():
    for loc in [
        "Singapore",
        "Singapore, Singapore",
        "Remote - Singapore",
        "APAC (Singapore)",
        "San Francisco | Singapore | London",
        "SG",
        "Remote-SG",
    ]:
        assert is_singapore(loc), loc


def test_non_singapore_rejected():
    for loc in ["San Francisco", "London", "Tokyo", "Sydney", "", "Remote - US"]:
        assert not is_singapore(loc), loc


def test_sg_is_whole_word_only():
    # "sg" must not match inside another word.
    assert not is_singapore("Glasgow")
    assert not is_singapore("Strasbourg")


def test_extra_location_keywords():
    assert not is_singapore("Remote - APAC")
    assert is_singapore("Remote - APAC", extra_keywords=["apac"])
    assert is_singapore("Fully remote", extra_keywords=["remote"])


def test_ai_role_positive():
    for title in [
        "Research Scientist",
        "Research Engineer, Pretraining",
        "Machine Learning Engineer",
        "Senior ML Engineer",
        "Applied Scientist, NLP",
        "AI Engineer",
        "Data Scientist",
        "Member of Technical Staff",
        "Forward Deployed Engineer",
        "AI Safety Researcher",
        "Head of AI",
        "ML Platform Engineer",
        "Generative AI Solutions Architect",
    ]:
        assert is_ai_role(title), title


def test_ai_role_negative():
    for title in [
        "Software Engineer, Billing",
        "Account Executive",
        "Recruiter, Technical",
        "Office Manager",
        "Data Center Technician",
        "Data Entry Clerk",
        "Product Designer",
        "Customer Support Specialist",
        "Financial Analyst",
    ]:
        assert not is_ai_role(title), title


def test_role_tags_classification():
    assert "research" in role_tags("Research Scientist")
    assert "ml" in role_tags("Machine Learning Engineer")
    assert "data" in role_tags("Data Scientist")
    assert "ai-safety" in role_tags("AI Safety Researcher")
    assert "infra" in role_tags("ML Platform Engineer")


def test_exclusion_beats_keyword():
    # "Data Center Technician" brushes the 'data' keyword but must be excluded.
    assert role_tags("Data Center Technician") == []
    # A recruiter for the AI team is still not an AI role.
    assert role_tags("Recruiter, AI Research") == []
