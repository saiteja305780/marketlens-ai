"""Small client the dashboard uses to talk to the MarketLens API. The dashboard never touches the
database directly, so it only shows what the tested endpoints return."""
import os
from pathlib import Path

import requests

BASE_URL = os.environ.get("MARKETLENS_API", "http://127.0.0.1:8000/api/v1")


def _read_env_key() -> str:
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ.get("API_KEY", "")


API_KEY = _read_env_key()


class ApiError(Exception):
    pass


def call(method: str, path: str, **kwargs):
    try:
        r = requests.request(method, BASE_URL + path, headers={"X-API-Key": API_KEY}, timeout=20, **kwargs)
    except requests.RequestException as exc:
        raise ApiError(f"Cannot reach the API at {BASE_URL}. Is uvicorn running? ({exc.__class__.__name__})")
    if r.status_code == 401:
        raise ApiError("The API rejected the key. Check API_KEY in your .env file.")
    if not r.ok:
        raise ApiError(f"API returned {r.status_code}: {r.text[:200]}")
    return r.json()


def get(path: str, params: dict | None = None):
    return call("GET", path, params=params)


def post(path: str, body: dict):
    return call("POST", path, json=body)


def delete(path: str):
    return call("DELETE", path)

