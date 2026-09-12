"""User accounts: registration, login and email verification backed by MySQL.

Lives apart from the rest of `ancla/` on purpose: every other package works on
the local YAML profile and needs no network, while this one needs a MySQL
server. Nothing outside `ancla/auth/` and its own web views depends on it, so
the app still starts and works without MySQL configured (the desktop build,
for one) — only the account screens report that the database is unavailable.
"""
