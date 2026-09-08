import type {
  AgentTask,
  Evidence,
  Incident,
  IncidentBundle,
  Remediation,
  RuntimeState,
  Scenario,
  TraceEntry,
  WorkItem,
} from '@/lib/api';

export type ShowcaseData = {
  incidents: Incident[];
  scenarios: Scenario[];
  bundle: IncidentBundle;
};

/**
 * A read-only, representative incident for the hosted portfolio experience.
 * It is deliberately labelled as a showcase and never sent through approval APIs.
 */
export function getShowcaseData(): ShowcaseData {
  const now = Date.now();
  const observedAt = new Date(now - 4 * 60_000).toISOString();
  const createdAt = new Date(now - 7 * 60_000).toISOString();
  const incidentId = 'inc_showcase_oom';
  const evidence: Evidence[] = [
    {
      id: 'ev_k8s_oom',
      source: 'kubernetes',
      kind: 'pod_event',
      summary: 'payments-7d8c9 restarted after an OOMKilled termination',
      raw_reference: 'k8s://sentinel-demo/pod/payments-7d8c9',
      payload: { reason: 'OOMKilled', exit_code: 137, restart_count: 4 },
      observed_at: observedAt,
    },
    {
      id: 'ev_prom_memory',
      source: 'prometheus',
      kind: 'metric_window',
      summary: 'Working set reached 99% of the 256 MiB container limit',
      raw_reference: 'promql://container_memory_working_set_bytes',
      payload: { peak_mib: 253.6, limit_mib: 256, window: '15m' },
      observed_at: observedAt,
    },
    {
      id: 'ev_logs_alloc',
      source: 'loki',
      kind: 'log_excerpt',
      summary: 'Allocation failures began 41 seconds before the restart',
      raw_reference: 'loki://payments?trace=4ad2',
      payload: { allocation_failures: 18, request_path: '/payments/authorize' },
      observed_at: observedAt,
    },
    {
      id: 'ev_git_limit',
      source: 'git',
      kind: 'change_diff',
      summary:
        'Latest deployment reduced the payments memory limit from 512 MiB to 256 MiB',
      raw_reference: 'git://8b19c2a/k8s/payments.yaml',
      payload: { commit: '8b19c2a', before: '512Mi', after: '256Mi' },
      observed_at: observedAt,
    },
    {
      id: 'ev_retrieval_42',
      source: 'incident_retrieval',
      kind: 'similar_incident',
      summary:
        'Prior incident INC-204 was resolved by restoring the memory limit',
      raw_reference: 'retrieval://runbooks/inc-204',
      payload: { similarity: 0.92, resolution: 'restore_memory_limit' },
      observed_at: observedAt,
    },
  ];

  const incident: Incident = {
    id: incidentId,
    title: 'Payments pods repeatedly OOMKilled under checkout traffic',
    service: 'payments',
    severity: 'SEV-2',
    status: 'waiting_approval',
    alert: {
      scenario_id: 'oom_killed_001',
      metrics: {
        restarts: 4,
        memory: '99%',
        error_rate: '8.7%',
        p95_latency: '1.82s',
      },
    },
    execution_id: 'exec_showcase_4ad2',
    diagnosis: {
      status: 'supported',
      root_cause: 'oom_killed',
      confidence: 0.98,
      evidence_ids: evidence.map((item) => item.id),
      contradictory_evidence_ids: [],
      missing_evidence: [],
      recommended_action: 'restore_memory_limit',
      risk_class: 'write_reversible',
      reasoning_summary:
        'The Kubernetes termination reason, near-limit memory signal, allocation errors, and deployment diff independently converge on a memory-limit regression. The retrieved incident supports—but does not determine—the diagnosis.',
    },
    created_at: createdAt,
    updated_at: observedAt,
  };

  const tasks: AgentTask[] = [
    task(
      'task_supervisor',
      null,
      'supervisor',
      'Route the investigation and enforce its budget',
    ),
    task(
      'task_platform',
      'task_supervisor',
      'infrastructure',
      'Inspect Kubernetes workload state',
    ),
    task(
      'task_metrics',
      'task_supervisor',
      'telemetry',
      'Correlate metrics and logs',
    ),
    task(
      'task_change',
      'task_supervisor',
      'change_analysis',
      'Inspect the deployment diff',
    ),
    task(
      'task_retrieval',
      'task_supervisor',
      'retrieval',
      'Find comparable resolved incidents',
    ),
    task(
      'task_diagnosis',
      'task_supervisor',
      'diagnosis',
      'Synthesize a cited root cause',
    ),
    {
      ...task(
        'task_verifier',
        'task_supervisor',
        'verifier',
        'Challenge unsupported claims and unsafe actions',
      ),
      outputs: { verified: true },
    },
    task(
      'task_remediation',
      'task_supervisor',
      'remediation',
      'Draft a reversible, approval-gated patch',
    ),
  ];

  const trace: TraceEntry[] = [
    traceEntry('trace_1', 'kubernetes.get_workload_state', 38.2, [
      'ev_k8s_oom',
    ]),
    traceEntry('trace_2', 'prometheus.query_range', 44.7, ['ev_prom_memory']),
    traceEntry('trace_3', 'logs.search', 31.5, ['ev_logs_alloc']),
    traceEntry('trace_4', 'git.diff_deployment', 26.9, ['ev_git_limit']),
    traceEntry('trace_5', 'incidents.retrieve_similar', 19.4, [
      'ev_retrieval_42',
    ]),
  ];

  const remediation: Remediation = {
    id: 'rem_showcase_restore_limit',
    incident_id: incidentId,
    action: 'restore_memory_limit',
    risk_class: 'write_reversible',
    plan: {
      patch:
        'spec:\n  template:\n    spec:\n      containers:\n        - name: payments\n          resources:\n            limits:\n-             memory: 256Mi\n+             memory: 512Mi',
      rollback: 'reapply commit 8b19c2a',
    },
    validation: {
      expected: [
        'rollout completes',
        'restart count stabilizes',
        'memory headroom > 25%',
      ],
    },
    status: 'pending_approval',
    created_at: observedAt,
  };

  const state: RuntimeState = {
    status: 'waiting_approval',
    trace_id: '4ad2c1f9a8e7',
    metadata: {
      graph_stage: 'approval_gate',
      graph_path: [
        'supervisor',
        'parallel_evidence',
        'diagnosis',
        'verifier',
        'remediation',
        'approval_gate',
      ],
      budget_usage: {
        elapsed_seconds: 0.46,
        model_tokens: 4832,
        tool_calls: 9,
        subagents: 5,
        estimated_cost_usd: 0,
      },
      budget_policy: {
        max_runtime_seconds: 120,
        max_model_tokens: 24000,
        max_tool_calls: 30,
        max_subagents: 8,
        max_identical_tool_calls: 3,
        max_cost_usd: 0.5,
      },
    },
    incident_id: incidentId,
  };

  const work: WorkItem = {
    id: 'work_showcase_4ad2',
    status: 'waiting_approval',
    attempts: 1,
    max_attempts: 3,
    provider_mode: 'showcase',
    lease_owner: null,
    last_error: null,
  };

  return {
    incidents: [incident],
    scenarios: SHOWCASE_SCENARIOS,
    bundle: {
      incident,
      evidence,
      tasks,
      trace,
      remediations: [remediation],
      work,
      state,
    },
  };
}

export const SHOWCASE_SCENARIOS: Scenario[] = [
  {
    id: 'oom_killed_001',
    title: 'memory limit regression',
    category: 'resources',
    service: 'payments',
    difficulty: 'medium',
  },
  {
    id: 'bad_readiness_probe_001',
    title: 'readiness path regression',
    category: 'kubernetes',
    service: 'checkout',
    difficulty: 'hard',
  },
  {
    id: 'selector_mismatch_001',
    title: 'service selector mismatch',
    category: 'networking',
    service: 'frontend',
    difficulty: 'medium',
  },
  {
    id: 'expired_certificate_001',
    title: 'upstream TLS certificate expired',
    category: 'security',
    service: 'checkout',
    difficulty: 'hard',
  },
];

export const SHOWCASE_BENCHMARK: Record<string, unknown> = {
  manifest: {
    protocol_version: 'independent-v2',
    independent_trial_count: 324,
    evaluator_labels_in_runtime_snapshot: false,
    source_revision: '9e06325e9f4aaa7ec08d4cf644c7df1d9c3137ab',
  },
  metrics: {
    baseline_direct: metric(36, 0.611111, 0.611111, 0, 0, 1, 0.113, 0, 0),
    baseline_react: metric(
      36,
      0.111111,
      1,
      0.888889,
      0.888889,
      1,
      562.679,
      0,
      0,
    ),
    baseline_graph: metric(
      36,
      0.277778,
      0.714286,
      0.611111,
      0.888889,
      1,
      477.364,
      416095,
      4106,
    ),
    sentinel_full: metric(
      36,
      0.777778,
      0.903226,
      0.138889,
      0.87963,
      1,
      514.109,
      172753,
      6034,
    ),
    ablation_no_verifier: metric(
      36,
      0.777778,
      0.903226,
      0.138889,
      0.87963,
      1,
      514.999,
      90658,
      4514,
    ),
    ablation_no_deep_learning: metric(
      36,
      0.75,
      0.964286,
      0.222222,
      0.861111,
      1,
      491.228,
      132340,
      5844,
    ),
    ablation_no_retrieval: metric(
      36,
      0.388889,
      0.583333,
      0.333333,
      0.851852,
      1,
      568.583,
      155676,
      5864,
    ),
    ablation_no_context_engineering: metric(
      36,
      0.777778,
      0.903226,
      0.138889,
      0.87963,
      1,
      516.842,
      889332,
      6034,
    ),
    ablation_no_subagents: metric(
      36,
      0.777778,
      0.903226,
      0.138889,
      0.87963,
      1,
      509.177,
      172753,
      6034,
    ),
  },
};

function task(
  id: string,
  parentId: string | null,
  agent: string,
  title: string,
): AgentTask {
  return {
    id,
    parent_id: parentId,
    agent,
    title,
    status: 'completed',
    outputs: {},
    evidence_ids: [],
  };
}

function traceEntry(
  id: string,
  toolName: string,
  durationMs: number,
  evidenceIds: string[],
): TraceEntry {
  return {
    id,
    tool_name: toolName,
    permission: 'read',
    status: 'succeeded',
    duration_ms: durationMs,
    retry_count: 0,
    evidence_ids: evidenceIds,
    error: null,
    created_at: new Date().toISOString(),
  };
}

function metric(
  trials: number,
  rootCauseAccuracy: number,
  selectiveAccuracy: number,
  abstentionRate: number,
  evidenceRecall: number,
  policySafetyRate: number,
  p95TotalTimeMs: number,
  inputTokens: number,
  outputTokens: number,
) {
  return {
    trials,
    root_cause_accuracy: rootCauseAccuracy,
    selective_accuracy: selectiveAccuracy,
    abstention_rate: abstentionRate,
    evidence_recall: evidenceRecall,
    policy_safety_rate: policySafetyRate,
    p95_total_time_ms: p95TotalTimeMs,
    input_tokens: inputTokens,
    output_tokens: outputTokens,
    estimated_cost_usd: 0,
  };
}
