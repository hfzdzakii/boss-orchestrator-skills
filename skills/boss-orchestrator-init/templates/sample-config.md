# boss-orchestrator workspace config (sample template)

Read by `.setting/boss-orchestrator.md`. The single fenced `json` block below is the only
machine-read part of this file; `null` means unresolved, never wildcard or permission.

```json
{
  "schema_version": 1,
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
      "label": "Sample Worker 1",
      "enabled": true,
      "disabled_reason": null,
      "provider_instance_id": "sample_provider_id",
      "driver_kind": "sample_driver",
      "route_id": "vendor/sample-model",
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
        "name": "Sample Model Claim",
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
      "label": "Sample Unresolved Worker",
      "enabled": false,
      "disabled_reason": "unresolved exact catalog route",
      "provider_instance_id": "sample_provider_id",
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
    "priority": "equal",
    "reliability_memory": "session",
    "parallel_scopes": "disjoint_only",
    "quality_feedback": "first",
    "no_progress_rounds": 2,
    "after_change": "escalate",
    "fallback_workers": [
      "sample-worker-1"
    ]
  },
  "confirmation": null
}
```
