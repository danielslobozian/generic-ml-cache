# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Inbound ports for the execution-query capability — read the stored executions.

Single-method use cases (School B) regrouped into one ExecutionQueryService:
list the current summaries, total stored bytes, an execution's tags, the current
execution for a key, and current executions by key prefix.
"""
