from app.main import app


def test_openapi_advertises_api_key_header():
    schemes = app.openapi()["components"]["securitySchemes"]
    assert any(s.get("type") == "apiKey" and s.get("in") == "header" and s.get("name") == "X-API-Key"
               for s in schemes.values())
