# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Inbound ports for the session-report capability (report a session / a tag).

Two single-method use cases (School B) regrouped into one SessionReportService,
which relocates the event->usage aggregation out of the driving controllers.
"""
