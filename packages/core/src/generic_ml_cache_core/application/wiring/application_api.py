# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import dataclass

from generic_ml_cache_core.application.port.inbound.artifact_content.read_artifact_blob_use_case import (
    ReadArtifactBlobUseCase,
)
from generic_ml_cache_core.application.port.inbound.execution_query.find_current_execution_use_case import (
    FindCurrentExecutionUseCase,
)
from generic_ml_cache_core.application.port.inbound.execution_query.find_executions_by_key_prefix_use_case import (
    FindExecutionsByKeyPrefixUseCase,
)
from generic_ml_cache_core.application.port.inbound.execution_query.list_execution_summaries_use_case import (
    ListExecutionSummariesUseCase,
)
from generic_ml_cache_core.application.port.inbound.execution_query.tags_for_execution_use_case import (
    TagsForExecutionUseCase,
)
from generic_ml_cache_core.application.port.inbound.execution_query.total_stored_bytes_use_case import (
    TotalStoredBytesUseCase,
)
from generic_ml_cache_core.application.port.inbound.probe.probe_use_case import ProbeUseCase
from generic_ml_cache_core.application.port.inbound.purge.evict_stale_use_case import (
    EvictStaleUseCase,
)
from generic_ml_cache_core.application.port.inbound.purge.evict_to_quota_use_case import (
    EvictToQuotaUseCase,
)
from generic_ml_cache_core.application.port.inbound.purge.purge_all_use_case import PurgeAllUseCase
from generic_ml_cache_core.application.port.inbound.purge.purge_by_key_use_case import (
    PurgeByKeyUseCase,
)
from generic_ml_cache_core.application.port.inbound.purge.purge_by_session_tag_use_case import (
    PurgeBySessionTagUseCase,
)
from generic_ml_cache_core.application.port.inbound.purge.purge_by_session_use_case import (
    PurgeBySessionUseCase,
)
from generic_ml_cache_core.application.port.inbound.purge.purge_by_tag_use_case import (
    PurgeByTagUseCase,
)
from generic_ml_cache_core.application.port.inbound.run_ml_execution.run_ml_execution_use_case import (
    RunMlExecutionUseCase,
)
from generic_ml_cache_core.application.port.inbound.session_admin.clear_session_spec_use_case import (
    ClearSessionSpecUseCase,
)
from generic_ml_cache_core.application.port.inbound.session_admin.execution_keys_for_session_use_case import (
    ExecutionKeysForSessionUseCase,
)
from generic_ml_cache_core.application.port.inbound.session_admin.get_session_spec_use_case import (
    GetSessionSpecUseCase,
)
from generic_ml_cache_core.application.port.inbound.session_admin.list_session_ids_use_case import (
    ListSessionIdsUseCase,
)
from generic_ml_cache_core.application.port.inbound.session_admin.sessions_for_tag_use_case import (
    SessionsForTagUseCase,
)
from generic_ml_cache_core.application.port.inbound.session_admin.set_session_spec_use_case import (
    SetSessionSpecUseCase,
)
from generic_ml_cache_core.application.port.inbound.session_report.report_for_session_use_case import (
    ReportForSessionUseCase,
)
from generic_ml_cache_core.application.port.inbound.session_report.report_for_tag_use_case import (
    ReportForTagUseCase,
)
from generic_ml_cache_core.application.port.inbound.session_tags.list_session_tags_use_case import (
    ListSessionTagsUseCase,
)
from generic_ml_cache_core.application.port.inbound.session_tags.tag_session_use_case import (
    TagSessionUseCase,
)
from generic_ml_cache_core.application.port.inbound.session_tags.untag_session_use_case import (
    UntagSessionUseCase,
)
from generic_ml_cache_core.application.port.inbound.store_repair.repair_store_use_case import (
    RepairStoreUseCase,
)
from generic_ml_cache_core.application.port.inbound.store_stats.event_counts_use_case import (
    EventCountsUseCase,
)
from generic_ml_cache_core.application.port.inbound.store_stats.hit_counts_by_key_use_case import (
    HitCountsByKeyUseCase,
)


@dataclass(frozen=True)
class ApplicationApi:
    """The application's API surface: the bundle of inbound ports the drivers call.

    Constructed by the composition root (``bootstrap.build_application_api``) and
    passed to controllers. **Every field is a single-method inbound-port ABC** —
    one field per use case, never a concrete ``*Service``. The out-ports (blob
    store, repository, metrics, diagnostics) are deliberately NOT here: the
    composition root injects them into the use-case impls, so a controller
    literally cannot reach an outbound adapter — "make illegal states
    unrepresentable". Enforced by import-linter Rule 10.

    **Interfaces are segregated by client role; implementations are grouped by
    machinery (B-1).** A capability's operations share one application service
    (e.g. ``PurgeService`` implements all seven purge/evict ABCs, because its
    operations share private internals), but that service is exposed here only
    through its per-operation ports: the composition root assigns the one
    ``PurgeService`` instance to each of ``purge_by_key`` … ``evict_to_quota``.
    So a controller depends on exactly the one operation it invokes (ISP), and no
    caller can reach a sibling operation it never uses. There is no aggregate
    façade interface — that would be a header interface mirroring the impl, which
    inverts no dependency. The field name is the operation; the method it carries
    keeps the service's own name (``wired.purge_by_key.purge_by_key(cmd)``,
    ``wired.tag_session.tag(cmd)``).

    This is a wiring concern, not a port — it lives outside ``application.port``
    precisely so the port ring can stay free of use-case imports.
    """

    # run / probe — single-operation capabilities (execute-shaped)
    run_ml: RunMlExecutionUseCase
    probe: ProbeUseCase

    # purge — one PurgeService implements all seven
    purge_by_key: PurgeByKeyUseCase
    purge_by_tag: PurgeByTagUseCase
    purge_by_session: PurgeBySessionUseCase
    purge_by_session_tag: PurgeBySessionTagUseCase
    purge_all: PurgeAllUseCase
    evict_stale: EvictStaleUseCase
    evict_to_quota: EvictToQuotaUseCase

    # session tags — one SessionTagsService implements all three
    tag_session: TagSessionUseCase
    untag_session: UntagSessionUseCase
    list_session_tags: ListSessionTagsUseCase

    # session admin — one SessionAdminService implements all six
    set_session_spec: SetSessionSpecUseCase
    clear_session_spec: ClearSessionSpecUseCase
    get_session_spec: GetSessionSpecUseCase
    list_session_ids: ListSessionIdsUseCase
    sessions_for_tag: SessionsForTagUseCase
    execution_keys_for_session: ExecutionKeysForSessionUseCase

    # session report — one SessionReportService implements both
    report_for_session: ReportForSessionUseCase
    report_for_tag: ReportForTagUseCase

    # execution query — one ExecutionQueryService implements all five
    list_execution_summaries: ListExecutionSummariesUseCase
    total_stored_bytes: TotalStoredBytesUseCase
    tags_for_execution: TagsForExecutionUseCase
    find_current_execution: FindCurrentExecutionUseCase
    find_executions_by_key_prefix: FindExecutionsByKeyPrefixUseCase

    # store stats — one StoreStatsService implements both
    event_counts: EventCountsUseCase
    hit_counts_by_key: HitCountsByKeyUseCase

    # artifact content — one ArtifactContentService
    read_artifact_blob: ReadArtifactBlobUseCase

    # store repair — one RepairStoreService (C-4 reconcile-against-presence)
    repair_store: RepairStoreUseCase
