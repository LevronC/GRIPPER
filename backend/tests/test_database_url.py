"""Database URL normalisation (explicit psycopg2 driver)."""

import pytest

from app.core.database_url import normalize_database_url


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("postgresql://u:p@h:5432/db", "postgresql+psycopg2://u:p@h:5432/db"),
        ("postgres://u:p@h:5432/db", "postgresql+psycopg2://u:p@h:5432/db"),
        ("postgresql+psycopg2://u:p@h/db", "postgresql+psycopg2://u:p@h/db"),
        ("postgresql://u:p%40ss@h/db?sslmode=require", "postgresql+psycopg2://u:p%40ss@h/db?sslmode=require"),
        ("postgresql://u:p@ss@h/db", "postgresql+psycopg2://u:p%40ss@h/db"),
    ],
)
def test_normalize_database_url(raw, expected):
    assert normalize_database_url(raw) == expected


def test_normalize_leaves_empty_untouched():
    assert normalize_database_url("") == ""
