# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Journal event names recorded through the call journal (RecordCallEventPort).

The shared vocabulary every use case logs against. Caching and metrics are
independent concerns: every resolution emits exactly one event, including the
ones that store nothing — so even a non-cached run is surfaced.
"""

from __future__ import annotations

#: served from an existing stored execution (a replay)
HIT = "hit"
#: a fresh real call was made and stored
RECORD = "record"
#: wanted the cache but found nothing servable (an offline miss)
MISS = "miss"
#: a fresh real call ran but was not stored (uncacheable, or a non-persisted/failed run)
RUN = "run"
#: a METER call ran (never replays) and a stored entry existed — it *would* have hit
WOULD_HIT = "would_hit"
#: a METER call ran (never replays) and no stored entry existed — it *would* have missed
WOULD_MISS = "would_miss"
