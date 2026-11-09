# boss-orchestrator workspace config (sample template v2)

Read by `.boss-orchestrator/runtime-policy.md`. The single fenced `json` block below is the only
machine-read part of this file; `null` means unresolved, never wildcard or permission.
In schema_version 2, the order of enabled entries in `workers[]` defines provider priority
(first enabled worker = highest priority). Exactly one enabled route is allowed per provider instance.

```json
{
  "schema_version": 2,
  "state": "draft",
  "scope": {
    "kind": "workspace",
    "root": "/path/to/workspace",
    "git": false
  },
  "harness": {
    "allowlist": [
      "t3"
    ],
    "unsupported": "cancel_before_writes"
  },
  "parent": {
    "selection": "current_active"
  },
  "workers": [
    {
      "id": "sample-worker-1",
      "label": "Sample Worker 1 (Priority 1)",
      "enabled": true,
      "disabled_reason": null,
      "provider_instance_id": "sample_provider_1",
      "driver_kind": "sample_driver",
      "route_id": "vendor/sample-model-1",
      "options": {
        "thinking_level": "high"
      },
      "thinking": {
        "mode": "explicit",
        "option_key": "thinking_level",
        "selected": "high",
        "allowed_values": [
          "low",
          "medium",
          "high"
        ]
      },
      "model_claim": {
        "name": "Sample Model 1",
        "provenance": "user_declared"
      },
      "upstreams": {
        "mapping": null,
        "independence": "unknown"
      },
      "catalog_evidence": {
        "level": "catalog_verified",
        "source_ref": "declared_catalog",
        "observed_at": "2026-11-06"
      },
      "execution_evidence": null
    },
    {
      "id": "sample-worker-2",
      "label": "Sample Worker 2 (Priority 2)",
      "enabled": true,
      "disabled_reason": null,
      "provider_instance_id": "sample_provider_2",
      "driver_kind": "sample_driver",
      "route_id": "vendor/sample-model-2",
      "options": {
        "thinking_level": "high"
      },
      "thinking": {
        "mode": "explicit",
        "option_key": "thinking_level",
        "selected": "high",
        "allowed_values": [
          "low",
          "medium",
          "high"
        ]
      },
      "model_claim": {
        "name": "Sample Model 2",
        "provenance": "user_declared"
      },
      "upstreams": {
        "mapping": null,
        "independence": "unknown"
      },
      "catalog_evidence": {
        "level": "catalog_verified",
        "source_ref": "declared_catalog",
        "observed_at": "2026-11-06"
      },
      "execution_evidence": null
    },
    {
      "id": "sample-worker-unresolved",
      "label": "Sample Inactive Alternative Route",
      "enabled": false,
      "disabled_reason": "inactive provider route alternative",
      "provider_instance_id": "sample_provider_1",
      "driver_kind": "sample_driver",
      "route_id": "vendor/unresolved-model",
      "options": null,
      "thinking": {
        "mode": "disabled",
        "reason": "route unresolved"
      },
      "model_claim": {
        "name": "Unresolved Model",
        "provenance": "user_declared"
      },
      "upstreams": {
        "mapping": null,
        "independence": "unknown"
      },
      "catalog_evidence": null,
      "execution_evidence": null
    }
  ],
  "boss": {
    "selection": "boss_per_task",
    "review_exception": "small_clear_local_review_fixes",
    "recursive_delegation": "task_explicit_only",
    "builtin_fallback": "excluded",
    "priority": "provider_order",
    "reliability_memory": "session",
    "parallel_scopes": "disjoint_only",
    "quality_feedback": "first",
    "no_progress_rounds": 2,
    "after_change": "escalate",
    "retry_after_successful_tasks": 5
  },
  "confirmation": null
}
```
