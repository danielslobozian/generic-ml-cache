# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Inbound ports for the purge capability — explicit invalidation + retention.

Single-method use cases (School B) regrouped into one PurgeService. The soft vs
hard distinction is a command FIELD (``hard``), never a separate use case.
"""
