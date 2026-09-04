export type Incident = {
  id: string;
  title: string;
  service: string;
  severity: string;
  status: string;
  alert: Record<string, unknown>;
  execution_id: string | null;
  diagnosis: Diagnosis | null;
  created_at: string;
  updated_at: string;
};

export type Diagnosis = {
  status: 'supported' | 'insufficient_evidence' | 'escalate';
  root_cause: string;
  confidence: number;
  evidence_ids: string[];
  contradictory_evidence_ids: string[];
  missing_evidence: string[];
  recommended_action: string;
  risk_class: string;
  reasoning_summary: string;
};

export type Evidence = {
  id: string;
  source: string;
  kind: string;
  summary: string;
  raw_reference: string;
  payload: Record<string, unknown>;
  observed_at: string;
};

export type AgentTask = {
  id: string;
  parent_id: string | null;
  agent: string;
  title: string;
  status: string;
  outputs: Record<string, unknown>;
  evidence_ids: string[];
};

export type TraceEntry = {
  id: string;
  tool_name: string;
  permission: string;
  status: string;
  duration_ms: number;
  retry_count: number;
  evidence_ids: string[];
  error: string | null;
  created_at: string;
};

export type Remediation = {
  id: string;
  incident_id: string;
  action: string;
  risk_class: string;
  plan: Record<string, unknown>;
  validation: Record<string, unknown>;
  status: string;
  created_at: string;
};

export type WorkItem = {
  id: string;
  status: string;
  attempts: number;
  max_attempts: number;
  provider_mode: string;
  lease_owner: string | null;
  last_error: string | null;
};

export type RuntimeState = {
  status: string;
  trace_id: string;
  metadata: {
    graph_stage?: string;
    graph_path?: string[];
    budget_usage?: {
      elapsed_seconds: number;
      model_tokens: number;
      tool_calls: number;
      subagents: number;
      estimated_cost_usd: number;
    };
    budget_policy?: {
      max_runtime_seconds: number;
      max_model_tokens: number;
      max_tool_calls: number;
      max_subagents: number;
      max_identical_tool_calls: number;
      max_cost_usd: number;
    };
  };
  incident_id: string;
};

export type Scenario = {
  id: string;
  title: string;
  category: string;
  service: string;
  difficulty: string;
};

export type IncidentBundle = {
  incident: Incident;
  evidence: Evidence[];
  tasks: AgentTask[];
  trace: TraceEntry[];
  remediations: Remediation[];
  work: WorkItem | null;
  state: RuntimeState | null;
};

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!headers.has('Content-Type'))
    headers.set('Content-Type', 'application/json');
  const response = await fetch(`/api/sentinel${path}`, {
    cache: 'no-store',
    ...init,
    headers,
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: string;
      message?: string;
    } | null;
    throw new ApiError(
      response.status,
      payload?.detail ??
        payload?.message ??
        `Sentinel API returned ${response.status}`,
    );
  }
  return (await response.json()) as T;
}

async function optional<T>(path: string): Promise<T | null> {
  try {
    return await request<T>(path);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export function getIncidents(): Promise<Incident[]> {
  return request('/v1/incidents');
}

export function getScenarios(): Promise<Scenario[]> {
  return request('/v1/simulator/scenarios');
}

export async function getIncidentBundle(
  incidentId: string,
): Promise<IncidentBundle> {
  const base = `/v1/incidents/${incidentId}`;
  const [incident, evidence, tasks, trace, remediations, work, state] =
    await Promise.all([
      request<Incident>(base),
      request<Evidence[]>(`${base}/evidence`),
      request<AgentTask[]>(`${base}/tasks`),
      request<TraceEntry[]>(`${base}/trace`),
      request<Remediation[]>(`${base}/remediations`),
      optional<WorkItem>(`${base}/work`),
      optional<RuntimeState>(`${base}/state`),
    ]);
  return { incident, evidence, tasks, trace, remediations, work, state };
}

export function runScenario(scenarioId: string): Promise<RuntimeState> {
  return request('/v1/simulator/run', {
    method: 'POST',
    body: JSON.stringify({ scenario_id: scenarioId }),
  });
}

export async function decideRemediation(
  incidentId: string,
  remediationId: string,
  decision: 'approved' | 'rejected',
  actor: string,
  reason: string,
): Promise<void> {
  const base = `/v1/incidents/${incidentId}/remediations/${remediationId}`;
  const token = await request<{ token: string }>(
    `${base}/approval-token?actor=${encodeURIComponent(actor)}`,
    { method: 'POST', body: '{}' },
  );
  await request(`${base}/approval`, {
    method: 'POST',
    headers: {
      'X-Approval-Token': token.token,
      'Idempotency-Key': crypto.randomUUID(),
    },
    body: JSON.stringify({ decision, actor, reason }),
  });
}

export function getLatestBenchmark(): Promise<Record<string, unknown>> {
  return request('/v1/benchmarks/latest');
}
