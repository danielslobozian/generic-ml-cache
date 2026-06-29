# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Composition-time wiring containers.

This layer holds the assembled application surface a driver's composition root
hands to its controllers. Unlike ``application.port`` (pure boundaries) it is
allowed to name concrete use cases — assembly is its whole job — so it sits
outside the port ring rather than polluting it.
"""
