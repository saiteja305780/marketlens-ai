class FakeResponse:
    def __init__(self, status_code=200, payload=None, text="",
                 content_type="application/json", url="https://shop.example.com/products.json"):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.headers = {"Content-Type": content_type}
        self.url = url

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        return self.response


class AllowAll:
    def allowed(self, url): return True
    def crawl_delay(self, url): return None


class DenyAll:
    def allowed(self, url): return False
    def crawl_delay(self, url): return None