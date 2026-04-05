"""Revoked-token store — use Redis in production instead of this in-memory set."""
revoked_tokens: set[str] = set()
