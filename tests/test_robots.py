from app.utils.robots import RobotsGuard
from tests.fakes import FakeResponse, FakeSession

URL = "https://shop.example.com/products.json"


def guard(status, text=""):
    return RobotsGuard(FakeSession(FakeResponse(status_code=status, text=text, content_type="text/plain")))


def test_missing_robots_allows():
    assert guard(404).allowed(URL)


def test_unreadable_robots_denies():
    assert not guard(403).allowed(URL)
    assert not guard(500).allowed(URL)


def test_disallow_rule_applied():
    g = guard(200, "User-agent: *\nDisallow: /private\n")
    assert g.allowed(URL)
    assert not g.allowed("https://shop.example.com/private/x")