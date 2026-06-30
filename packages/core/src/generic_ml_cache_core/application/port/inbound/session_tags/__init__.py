# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Inbound ports for the session-tags capability (tag / untag / list).

Three single-method use cases (School B), regrouped into one SessionTagsService
impl. A driving adapter reaches session tagging only through these ports — never
through the metrics out-port directly.
"""
