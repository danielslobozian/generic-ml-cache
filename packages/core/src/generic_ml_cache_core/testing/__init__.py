# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Shipped test-support kit (E-1, V6).

Reference in-memory fakes + a conformance TCK for the outbound persistence ports,
so the core's own tests can be state-based WITHOUT importing an adapter (isolation),
and a third-party ``PersistenceBackend`` author can prove their adapter against the
same kit the shipped SQLite adapter passes (fake and real can't drift — Fowler's
Contract Test).

Not imported by any production module (import-linter enforces this); its pytest
dependency sits behind the ``[test]`` extra, so the core runtime stays dep-free.
"""
