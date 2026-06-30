# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Adapter discovery: catalogs, resolvers, and descriptor helpers.

This is infrastructure — it may scan installed entry points and construct
concrete adapter classes. Core only sees the AdapterCatalogPort / AdapterResolverPort
contracts; the implementations live here and are injected by the composition root.
"""
