"""Focused async SQLite repositories for durable chat persistence.

Higher-level services own short atomic transactions; repository methods accept
an existing ``AsyncSession`` and never commit or open hidden sessions.
"""
