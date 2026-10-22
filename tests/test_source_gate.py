import pytest

from app.scrapers.base import SourceConfigError
from app.scrapers.registry import STORES, build_source


def test_unapproved_sources_cannot_be_built():
    for name, cfg in STORES.items():
        if cfg.status != "approved":
            with pytest.raises(SourceConfigError):
                build_source(name)


def test_boat_is_blocked():
    assert STORES["boat"].status == "blocked"
