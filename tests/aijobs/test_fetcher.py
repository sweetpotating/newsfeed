"""Adapter tests — feed each provider a fixture JSON and check normalisation.

No network: we stub ``requests.Session.get`` to return canned payloads.
"""

from datetime import timezone

from aijobs import fetcher
from aijobs.sources import Company


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _patch(monkeypatch, payload):
    monkeypatch.setattr(
        fetcher.requests.Session, "get",
        lambda self, url, timeout=0: _FakeResp(payload),
    )


def test_greenhouse_adapter(monkeypatch):
    payload = {"jobs": [{
        "id": 123,
        "title": "Research Scientist",
        "absolute_url": "https://boards.greenhouse.io/anthropic/jobs/123",
        "location": {"name": "Singapore"},
        "departments": [{"name": "Research"}],
        "updated_at": "2026-05-30T10:00:00Z",
    }]}
    _patch(monkeypatch, payload)
    jobs = fetcher.fetch_company(
        Company("Anthropic", "greenhouse", "anthropic", is_priority_lab=True), 10)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "Research Scientist"
    assert j.company == "Anthropic"
    assert j.location == "Singapore"
    assert j.is_priority_lab is True
    assert j.department == "Research"
    assert j.url.endswith("/123")
    assert j.posted is not None and j.posted.tzinfo == timezone.utc
    assert j.uid  # non-empty stable id


def test_lever_adapter_multi_location(monkeypatch):
    payload = [{
        "id": "abc",
        "text": "Machine Learning Engineer",
        "hostedUrl": "https://jobs.lever.co/grab/abc",
        "categories": {"location": "Singapore",
                       "allLocations": ["Singapore", "Jakarta"],
                       "team": "Data Science"},
        "createdAt": 1764500000000,  # epoch ms
        "descriptionPlain": "Build ML systems.",
    }]
    _patch(monkeypatch, payload)
    jobs = fetcher.fetch_company(Company("Grab", "lever", "grab"), 10)
    assert len(jobs) == 1
    j = jobs[0]
    assert "Singapore" in j.location
    assert j.department == "Data Science"
    assert j.summary == "Build ML systems."
    assert j.posted is not None  # ms timestamp parsed


def test_ashby_adapter_secondary_locations(monkeypatch):
    payload = {"jobs": [
        {
            "title": "Member of Technical Staff",
            "jobUrl": "https://jobs.ashbyhq.com/openai/1",
            "location": "San Francisco",
            "secondaryLocations": [{"location": "Singapore"}],
            "department": "Research",
            "publishedAt": "2026-05-29T00:00:00Z",
            "isListed": True,
        },
        {
            "title": "Hidden role",
            "jobUrl": "https://jobs.ashbyhq.com/openai/2",
            "location": "Singapore",
            "isListed": False,  # must be skipped
        },
    ]}
    _patch(monkeypatch, payload)
    jobs = fetcher.fetch_company(
        Company("OpenAI", "ashby", "openai", is_priority_lab=True), 10)
    assert len(jobs) == 1  # the unlisted one is dropped
    assert "Singapore" in jobs[0].location


def test_google_adapter(monkeypatch):
    payload = {"jobs": [{
        "id": "jobs/12345",
        "title": "Research Engineer, Gemini",
        "company_name": "Google DeepMind",
        "locations": [{"display": "Singapore"}],
        "apply_url": "https://careers.google.com/jobs/results/12345",
        "publish_date": "2026-05-28T00:00:00Z",
        "categories": ["AI/ML"],
        "summary": "Work on Gemini.",
    }]}
    _patch(monkeypatch, payload)
    jobs = fetcher.fetch_company(
        Company("Google DeepMind / Gemini", "google", "ai", is_priority_lab=True), 10)
    assert len(jobs) == 1
    assert jobs[0].company == "Google DeepMind"
    assert jobs[0].location == "Singapore"


def test_unknown_provider_returns_empty():
    assert fetcher.fetch_company(Company("X", "workday", "x"), 10) == []


def test_network_error_is_swallowed(monkeypatch):
    def boom(self, url, timeout=0):
        raise fetcher.requests.RequestException("down")
    monkeypatch.setattr(fetcher.requests.Session, "get", boom)
    assert fetcher.fetch_company(Company("Anthropic", "greenhouse", "anthropic"), 10) == []
