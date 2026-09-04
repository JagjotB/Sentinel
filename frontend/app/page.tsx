'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  Box,
  CheckCircle2,
  CircleDot,
  Clock3,
  FileSearch,
  GitCommitHorizontal,
  Network,
  Radar,
  RefreshCw,
  ShieldCheck,
  XCircle,
  Zap,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  NativeSelect,
  NativeSelectOption,
} from '@/components/ui/native-select';
import { Progress } from '@/components/ui/progress';
import { Textarea } from '@/components/ui/textarea';
import {
  type AgentTask,
  type Evidence,
  type Incident,
  type IncidentBundle,
  type Remediation,
  type Scenario,
  decideRemediation,
  getIncidentBundle,
  getIncidents,
  getScenarios,
  runScenario,
} from '@/lib/api';

export default function Home() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [bundle, setBundle] = useState<IncidentBundle | null>(null);
  const [scenarioId, setScenarioId] = useState('oom_killed_001');
  const [actor, setActor] = useState('oncall@example.com');
  const [reason, setReason] = useState(
    'Evidence and action scope independently reviewed',
  );
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshIncidents = useCallback(async () => {
    const rows = await getIncidents();
    setIncidents(rows);
    setError(null);
    setSelectedId((current) =>
      current && rows.some((row) => row.id === current)
        ? current
        : (rows[0]?.id ?? null),
    );
    return rows;
  }, []);

  const refreshBundle = useCallback(async () => {
    if (!selectedId) {
      setBundle(null);
      return;
    }
    setBundle(await getIncidentBundle(selectedId));
    setError(null);
  }, [selectedId]);

  useEffect(() => {
    void Promise.all([getIncidents(), getScenarios()])
      .then(([rows, loadedScenarios]) => {
        setIncidents(rows);
        setSelectedId(rows[0]?.id ?? null);
        setScenarios(loadedScenarios);
        setError(null);
      })
      .catch((cause: unknown) => setError(messageOf(cause)));
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    void getIncidentBundle(selectedId)
      .then(setBundle)
      .catch((cause: unknown) => setError(messageOf(cause)));
    const timer = window.setInterval(() => {
      void Promise.all([getIncidents(), getIncidentBundle(selectedId)])
        .then(([rows, loadedBundle]) => {
          setIncidents(rows);
          setBundle(loadedBundle);
          setError(null);
        })
        .catch((cause: unknown) => setError(messageOf(cause)));
    }, 3000);
    return () => window.clearInterval(timer);
  }, [selectedId]);

  async function startDemo() {
    setBusy('run');
    setError(null);
    try {
      const state = await runScenario(scenarioId);
      await refreshIncidents();
      setSelectedId(state.incident_id);
    } catch (cause) {
      setError(messageOf(cause));
    } finally {
      setBusy(null);
    }
  }

  async function decide(decision: 'approved' | 'rejected') {
    const remediation = bundle?.remediations.at(-1);
    if (!bundle || !remediation) return;
    setBusy(decision);
    setError(null);
    try {
      await decideRemediation(
        bundle.incident.id,
        remediation.id,
        decision,
        actor.trim(),
        reason.trim(),
      );
      await refreshBundle();
    } catch (cause) {
      setError(messageOf(cause));
    } finally {
      setBusy(null);
    }
  }

  const incident = bundle?.incident ?? null;
  const diagnosis = incident?.diagnosis ?? null;
  const remediation = bundle?.remediations.at(-1) ?? null;
  const budget = bundle?.state?.metadata.budget_usage;
  const policy = bundle?.state?.metadata.budget_policy;

  return (
    <main className="min-h-screen bg-background text-foreground">
      <Header online={!error} onRefresh={() => void refreshBundle()} />
      <div className="mx-auto grid max-w-[1600px] grid-cols-1 gap-5 px-4 py-5 sm:px-6 xl:grid-cols-[280px_minmax(0,1fr)_350px]">
        <aside className="space-y-4 xl:sticky xl:top-[76px] xl:h-[calc(100vh-96px)]">
          <section className="panel p-3.5">
            <div className="mb-3 flex items-center justify-between">
              <p className="eyebrow">Run investigation</p>
              <Zap className="size-3.5 text-amber-300" />
            </div>
            <NativeSelect
              aria-label="Simulator scenario"
              className="w-full"
              value={scenarioId}
              onChange={(event) => setScenarioId(event.target.value)}
            >
              {scenarios.map((scenario) => (
                <NativeSelectOption key={scenario.id} value={scenario.id}>
                  {scenario.service} · {scenario.title}
                </NativeSelectOption>
              ))}
            </NativeSelect>
            <Button
              className="mt-2 w-full bg-cyan-300 text-slate-950 hover:bg-cyan-200"
              disabled={busy !== null || scenarios.length === 0}
              onClick={() => void startDemo()}
            >
              {busy === 'run' ? (
                <RefreshCw className="animate-spin" />
              ) : (
                <Activity />
              )}
              Start evidence run
            </Button>
          </section>

          <section>
            <div className="mb-2 flex items-center justify-between px-1">
              <p className="eyebrow">Incidents</p>
              <span className="font-mono text-[10px] text-zinc-600">
                {String(incidents.length).padStart(2, '0')}
              </span>
            </div>
            <div className="max-h-72 space-y-1 overflow-y-auto">
              {incidents.map((row) => (
                <button
                  key={row.id}
                  aria-label={`Open ${row.service} incident`}
                  className={`incident-row w-full text-left ${row.id === selectedId ? 'incident-row-active' : ''}`}
                  onClick={() => setSelectedId(row.id)}
                >
                  <StatusDot status={row.status} />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center justify-between gap-3">
                      <strong className="truncate text-sm font-medium text-zinc-200">
                        {row.service}
                      </strong>
                      <span className="font-mono text-[10px] text-zinc-600">
                        {relativeTime(row.created_at)}
                      </span>
                    </span>
                    <span className="mt-1 block truncate text-xs text-zinc-500">
                      {row.title}
                    </span>
                  </span>
                </button>
              ))}
              {incidents.length === 0 && (
                <p className="rounded-lg border border-dashed border-white/10 px-3 py-5 text-center text-xs text-zinc-500">
                  No incidents yet. Start a scenario above.
                </p>
              )}
            </div>
          </section>

          <section className="panel p-3.5">
            <div className="mb-3 flex items-center justify-between">
              <p className="eyebrow">Execution budget</p>
              <Zap className="size-3.5 text-amber-300" />
            </div>
            {budget && policy ? (
              <div className="space-y-3">
                <BudgetRow
                  label="Tool calls"
                  value={budget.tool_calls}
                  maximum={policy.max_tool_calls}
                />
                <BudgetRow
                  label="Model tokens"
                  value={budget.model_tokens}
                  maximum={policy.max_model_tokens}
                />
                <BudgetRow
                  label="Runtime seconds"
                  value={Math.round(budget.elapsed_seconds)}
                  maximum={policy.max_runtime_seconds}
                />
                <BudgetRow
                  label="Estimated cost"
                  value={budget.estimated_cost_usd}
                  maximum={policy.max_cost_usd}
                  money
                />
              </div>
            ) : (
              <EmptyLine text="Budget appears when execution starts" />
            )}
          </section>

          <TaskTree tasks={bundle?.tasks ?? []} />
        </aside>

        <section id="incident" className="min-w-0 space-y-5">
          {error && (
            <div className="rounded-xl border border-red-300/20 bg-red-300/7 p-4 text-sm text-red-200">
              <strong className="block">Sentinel API unavailable</strong>
              <span className="mt-1 block text-red-100/70">{error}</span>
            </div>
          )}
          {incident ? (
            <>
              <IncidentHero
                incident={incident}
                workStatus={bundle?.work?.status}
              />
              <EvidencePanel evidence={bundle?.evidence ?? []} />
              <DiagnosisPanel incident={incident} />
              <TracePanel
                trace={bundle?.trace ?? []}
                traceId={bundle?.state?.trace_id}
              />
            </>
          ) : (
            <section className="hero-panel grid min-h-96 place-items-center p-8 text-center">
              <div>
                <Radar className="mx-auto size-10 text-cyan-300" />
                <h1 className="mt-4 text-2xl font-semibold text-white">
                  Evidence-backed incident command
                </h1>
                <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-zinc-500">
                  Start a deterministic scenario or ingest an alert to watch the
                  real agent graph, evidence, diagnosis, and approval state
                  appear here.
                </p>
              </div>
            </section>
          )}
        </section>

        <aside className="space-y-5 xl:sticky xl:top-[76px] xl:h-[calc(100vh-96px)]">
          <VerifierPanel
            tasks={bundle?.tasks ?? []}
            diagnosisStatus={diagnosis?.status}
          />
          <RemediationPanel
            remediation={remediation}
            actor={actor}
            reason={reason}
            busy={busy}
            onActor={setActor}
            onReason={setReason}
            onDecision={(value) => void decide(value)}
          />
          <section className="panel p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="eyebrow">Measured evaluation</p>
                <p className="mt-1 text-sm font-medium text-white">
                  Independent results
                </p>
              </div>
              <Network className="size-4 text-violet-300" />
            </div>
            <Link
              href="/benchmarks"
              className="mt-3 flex items-center justify-between rounded-lg border border-white/7 px-3 py-2 text-[11px] text-zinc-500 transition-colors hover:border-white/15 hover:text-zinc-300"
            >
              <span>Open evaluation report</span>
              <ArrowUpRight className="size-3" />
            </Link>
          </section>
        </aside>
      </div>
    </main>
  );
}

function Header({
  online,
  onRefresh,
}: {
  online: boolean;
  onRefresh: () => void;
}) {
  return (
    <header className="sticky top-0 z-30 border-b border-white/8 bg-background/85 backdrop-blur-xl">
      <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-4 px-4 sm:px-6">
        <div className="flex items-center gap-2.5">
          <span className="grid size-8 place-items-center rounded-lg border border-cyan-300/25 bg-cyan-300/8 text-cyan-300">
            <Radar className="size-4" />
          </span>
          <span className="font-mono text-sm font-bold tracking-[0.2em] text-white">
            SENTINEL
          </span>
        </div>
        <nav className="hidden items-center gap-1 text-xs text-muted-foreground sm:flex">
          <Link
            className="rounded-md bg-white/7 px-3 py-1.5 text-white"
            href="#incident"
          >
            Incidents
          </Link>
          <Link
            className="rounded-md px-3 py-1.5 hover:text-white"
            href="#evidence"
          >
            Evidence
          </Link>
          <Link
            className="rounded-md px-3 py-1.5 hover:text-white"
            href="/benchmarks"
          >
            Benchmarks
          </Link>
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <Badge
            variant="outline"
            className={
              online
                ? 'border-emerald-400/20 bg-emerald-400/8 text-emerald-300'
                : 'border-red-400/20 bg-red-400/8 text-red-300'
            }
          >
            <span
              className={`size-1.5 rounded-full ${online ? 'bg-emerald-300' : 'bg-red-300'}`}
            />
            {online ? 'API connected' : 'API offline'}
          </Badge>
          <Button variant="outline" size="sm" onClick={onRefresh}>
            <RefreshCw /> Refresh
          </Button>
        </div>
      </div>
    </header>
  );
}

function IncidentHero({
  incident,
  workStatus,
}: {
  incident: Incident;
  workStatus?: string;
}) {
  const metrics = isRecord(incident.alert.metrics)
    ? incident.alert.metrics
    : {};
  const metricRows = Object.entries(metrics).slice(0, 4);
  return (
    <Card className="hero-panel border-0 py-0 ring-0">
      <CardContent className="relative overflow-hidden p-5 sm:p-6">
        <div className="relative flex flex-col gap-5 md:flex-row md:justify-between">
          <div>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Badge
                variant="destructive"
                className="bg-red-400/12 text-red-300"
              >
                {incident.severity}
              </Badge>
              <Badge
                variant="outline"
                className="border-white/10 font-mono text-zinc-400"
              >
                {incident.id}
              </Badge>
              <span className="flex items-center gap-1.5 text-xs text-zinc-500">
                <Clock3 className="size-3" />{' '}
                {relativeTime(incident.created_at)}
              </span>
            </div>
            <h1 className="text-2xl font-semibold tracking-[-0.035em] text-white sm:text-3xl">
              {incident.title}
            </h1>
            <p className="mt-2 text-sm text-zinc-400">
              Service{' '}
              <span className="font-mono text-zinc-200">
                {incident.service}
              </span>{' '}
              · loaded from the Sentinel API
            </p>
          </div>
          <Badge
            variant="outline"
            className="h-7 border-cyan-300/20 bg-cyan-300/7 px-3 text-cyan-200"
          >
            <span className="size-1.5 rounded-full bg-cyan-300" />{' '}
            {workStatus ?? incident.status}
          </Badge>
        </div>
        {metricRows.length > 0 && (
          <div className="relative mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {metricRows.map(([label, value]) => (
              <div key={label} className="metric">
                <span className="text-[10px] uppercase tracking-[0.12em] text-zinc-600">
                  {label.replaceAll('_', ' ')}
                </span>
                <strong className="mt-1 block font-mono text-xl text-white">
                  {String(value)}
                </strong>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function EvidencePanel({ evidence }: { evidence: Evidence[] }) {
  return (
    <section id="evidence" className="panel overflow-hidden">
      <div className="flex items-center justify-between border-b border-white/8 px-4 py-3.5 sm:px-5">
        <div>
          <p className="eyebrow">Evidence timeline</p>
          <h2 className="mt-1 text-sm font-medium text-white">
            Durable provider artifacts
          </h2>
        </div>
        <span className="font-mono text-xs text-zinc-500">
          {evidence.length} artifacts
        </span>
      </div>
      <div className="divide-y divide-white/7">
        {evidence.map((item) => {
          const Icon = evidenceIcon(item.source);
          return (
            <article
              key={item.id}
              className="grid gap-3 px-4 py-4 sm:grid-cols-[38px_minmax(0,1fr)] sm:px-5"
            >
              <span className="evidence-icon evidence-icon-cyan">
                <Icon className="size-4" />
              </span>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-[10px] text-zinc-600">
                    {item.id}
                  </span>
                  <span className="text-[10px] uppercase tracking-wider text-zinc-500">
                    {item.source} / {item.kind}
                  </span>
                </div>
                <h3 className="mt-1.5 text-sm font-medium text-zinc-200">
                  {item.summary}
                </h3>
                <p className="mt-1 truncate font-mono text-[11px] text-zinc-600">
                  {evidenceDetail(item)}
                </p>
              </div>
            </article>
          );
        })}
        {evidence.length === 0 && (
          <EmptyLine text="Evidence collection has not started" />
        )}
      </div>
    </section>
  );
}

function DiagnosisPanel({ incident }: { incident: Incident }) {
  const diagnosis = incident.diagnosis;
  if (!diagnosis) {
    return (
      <section className="panel p-5">
        <EmptyLine text="Diagnosis is pending" />
      </section>
    );
  }
  return (
    <section className="panel p-4 sm:p-5">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <p className="eyebrow">Verified diagnosis</p>
          <h2 className="mt-1.5 text-base font-medium text-white">
            {diagnosis.root_cause.replaceAll('_', ' ')}
          </h2>
        </div>
        <span className="font-mono text-xl font-semibold text-cyan-200">
          {(diagnosis.confidence * 100).toFixed(1)}%
        </span>
      </div>
      <p className="text-sm leading-6 text-zinc-400">
        {diagnosis.reasoning_summary}
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        {diagnosis.evidence_ids.map((id) => (
          <Badge
            key={id}
            variant="outline"
            className="border-white/10 font-mono text-[10px] text-zinc-400"
          >
            {id}
          </Badge>
        ))}
        <Badge
          variant="outline"
          className="border-emerald-300/15 bg-emerald-300/6 text-emerald-300"
        >
          <ShieldCheck /> {diagnosis.status}
        </Badge>
      </div>
    </section>
  );
}

function TaskTree({ tasks }: { tasks: AgentTask[] }) {
  return (
    <section className="panel p-3.5">
      <p className="eyebrow mb-3">Agent task tree</p>
      <ol className="space-y-3">
        {tasks.map((task, index) => (
          <li key={task.id} className="relative flex gap-3">
            {index < tasks.length - 1 && (
              <span className="absolute left-[7px] top-5 h-7 w-px bg-white/10" />
            )}
            {task.status === 'completed' ? (
              <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-emerald-300" />
            ) : task.status === 'failed' ? (
              <XCircle className="mt-0.5 size-3.5 shrink-0 text-red-300" />
            ) : (
              <CircleDot className="mt-0.5 size-3.5 shrink-0 animate-pulse text-cyan-300" />
            )}
            <span>
              <strong className="block text-xs font-medium text-zinc-200">
                {task.agent}
              </strong>
              <span className="mt-0.5 block text-[11px] leading-4 text-zinc-500">
                {task.title}
              </span>
            </span>
          </li>
        ))}
        {tasks.length === 0 && <EmptyLine text="No tasks scheduled" />}
      </ol>
    </section>
  );
}

function VerifierPanel({
  tasks,
  diagnosisStatus,
}: {
  tasks: AgentTask[];
  diagnosisStatus?: string;
}) {
  const verifier = tasks.find((task) => task.agent === 'verifier');
  return (
    <section className="panel overflow-hidden">
      <div className="border-b border-white/8 px-4 py-3.5">
        <p className="eyebrow">Verifier / critic</p>
        <div className="mt-2 flex items-center gap-2 text-sm font-medium text-white">
          <ShieldCheck className="size-4 text-cyan-300" />{' '}
          {verifier?.status ?? 'pending'}
        </div>
      </div>
      <div className="space-y-3 p-4 text-xs text-zinc-400">
        <VerifierRow
          label="Citation provenance"
          status={diagnosisStatus === 'supported' ? 'supported' : 'pending'}
        />
        <VerifierRow
          label="Alternative hypotheses"
          status={primitiveText(verifier?.outputs.verified) ?? 'pending'}
        />
        <VerifierRow label="Policy boundary" status="enforced" />
      </div>
    </section>
  );
}

function RemediationPanel({
  remediation,
  actor,
  reason,
  busy,
  onActor,
  onReason,
  onDecision,
}: {
  remediation: Remediation | null;
  actor: string;
  reason: string;
  busy: string | null;
  onActor: (value: string) => void;
  onReason: (value: string) => void;
  onDecision: (value: 'approved' | 'rejected') => void;
}) {
  if (!remediation) {
    return (
      <section className="panel p-4">
        <EmptyLine text="No remediation proposed" />
      </section>
    );
  }
  const pending = remediation.status === 'pending_approval';
  const patch =
    typeof remediation.plan.patch === 'string' ? remediation.plan.patch : null;
  const execution = isRecord(remediation.validation.execution)
    ? remediation.validation.execution
    : null;
  return (
    <section className="panel overflow-hidden">
      <div className="border-b border-white/8 px-4 py-3.5">
        <p className="eyebrow">Proposed remediation</p>
        <h2 className="mt-1.5 text-sm font-medium text-white">
          {remediation.action}
        </h2>
      </div>
      <div className="p-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <Badge
            variant="outline"
            className="border-amber-300/20 bg-amber-300/7 text-amber-200"
          >
            <AlertTriangle /> {remediation.risk_class.replaceAll('_', ' ')}
          </Badge>
          <span className="font-mono text-[10px] text-zinc-600">
            {remediation.id}
          </span>
        </div>
        {patch && (
          <pre className="overflow-x-auto rounded-lg border border-white/8 bg-black/30 p-3 font-mono text-[11px] leading-5 text-zinc-400">
            {patch}
          </pre>
        )}
        {pending ? (
          <div className="mt-4 space-y-2">
            <Input
              aria-label="Approver identity"
              value={actor}
              onChange={(event) => onActor(event.target.value)}
            />
            <Textarea
              aria-label="Decision reason"
              value={reason}
              onChange={(event) => onReason(event.target.value)}
            />
            <div className="grid grid-cols-2 gap-2">
              <Button
                disabled={
                  busy !== null ||
                  actor.trim().length < 2 ||
                  reason.trim().length < 3
                }
                onClick={() => onDecision('rejected')}
                variant="outline"
              >
                Reject
              </Button>
              <Button
                disabled={
                  busy !== null ||
                  actor.trim().length < 2 ||
                  reason.trim().length < 3
                }
                onClick={() => onDecision('approved')}
                className="bg-cyan-300 text-slate-950 hover:bg-cyan-200"
              >
                <ShieldCheck /> Approve
              </Button>
            </div>
          </div>
        ) : (
          <output
            className={`mt-4 block rounded-lg border px-3 py-2.5 text-xs ${remediation.status === 'rejected' ? 'border-red-300/20 bg-red-300/7 text-red-200' : 'border-emerald-300/20 bg-emerald-300/7 text-emerald-200'}`}
          >
            {remediation.status.replaceAll('_', ' ')}
            {typeof execution?.artifact === 'string'
              ? ` · ${execution.artifact}`
              : ''}
          </output>
        )}
      </div>
    </section>
  );
}

function TracePanel({
  trace,
  traceId,
}: {
  trace: IncidentBundle['trace'];
  traceId?: string;
}) {
  return (
    <section id="trace" className="panel overflow-hidden">
      <div className="border-b border-white/8 px-5 py-3.5">
        <p className="eyebrow">Tool trace</p>
        <p className="mt-1 truncate font-mono text-[11px] text-zinc-500">
          {traceId ?? 'not started'}
        </p>
      </div>
      <div className="divide-y divide-white/7">
        {trace.map((entry) => (
          <div
            key={entry.id}
            className="grid grid-cols-[1fr_auto_auto] gap-3 px-5 py-3 text-xs"
          >
            <span className="font-mono text-zinc-300">{entry.tool_name}</span>
            <span className="text-zinc-500">
              {entry.duration_ms.toFixed(1)}ms
            </span>
            <span
              className={
                entry.status === 'succeeded'
                  ? 'text-emerald-300'
                  : 'text-red-300'
              }
            >
              {entry.status}
            </span>
          </div>
        ))}
        {trace.length === 0 && <EmptyLine text="No tool calls recorded" />}
      </div>
    </section>
  );
}

function BudgetRow({
  label,
  value,
  maximum,
  money = false,
}: {
  label: string;
  value: number;
  maximum: number;
  money?: boolean;
}) {
  const percent = maximum > 0 ? Math.min(100, (value / maximum) * 100) : 0;
  const display = money
    ? `$${value.toFixed(3)} / $${maximum.toFixed(2)}`
    : `${value.toLocaleString()} / ${maximum.toLocaleString()}`;
  return (
    <div>
      <div className="mb-1.5 flex justify-between text-[11px]">
        <span className="text-zinc-500">{label}</span>
        <span className="font-mono text-zinc-400">{display}</span>
      </div>
      <Progress
        value={percent}
        className="[&_[data-slot=progress-indicator]]:bg-cyan-300/80"
      />
    </div>
  );
}

function VerifierRow({ label, status }: { label: string; status: string }) {
  const successful = ['supported', 'true', 'enforced'].includes(status);
  return (
    <div className="flex items-center gap-2.5">
      <span
        className={`size-1.5 rounded-full ${successful ? 'bg-emerald-300' : 'bg-zinc-700'}`}
      />
      <span className="flex-1">{label}</span>
      <span className="font-mono text-[9px] uppercase tracking-wider text-zinc-600">
        {status}
      </span>
    </div>
  );
}

function StatusDot({ status }: { status: string }) {
  const color =
    status === 'failed_system'
      ? 'bg-red-400'
      : status === 'resolved'
        ? 'bg-emerald-300'
        : 'bg-amber-300';
  return <span className={`mt-1 size-2 shrink-0 rounded-full ${color}`} />;
}

function EmptyLine({ text }: { text: string }) {
  return <p className="px-3 py-4 text-center text-xs text-zinc-600">{text}</p>;
}

function evidenceIcon(source: string) {
  if (source.includes('kubernetes')) return Box;
  if (source.includes('git') || source.includes('change')) {
    return GitCommitHorizontal;
  }
  if (source.includes('retrieval') || source.includes('incident')) {
    return FileSearch;
  }
  return Activity;
}

function evidenceDetail(item: Evidence): string {
  const details = Object.entries(item.payload)
    .filter(([, value]) =>
      ['string', 'number', 'boolean'].includes(typeof value),
    )
    .slice(0, 4)
    .map(([key, value]) => `${key}=${String(value)}`);
  return details.join(' · ') || item.raw_reference;
}

function relativeTime(value: string): string {
  const seconds = Math.max(
    0,
    Math.round((Date.now() - new Date(value).getTime()) / 1000),
  );
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : 'Unknown error';
}

function primitiveText(value: unknown): string | null {
  return ['string', 'number', 'boolean'].includes(typeof value)
    ? String(value)
    : null;
}
