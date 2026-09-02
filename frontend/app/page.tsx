'use client';

import { useState } from 'react';
import Link from 'next/link';

import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  Box,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Clock3,
  GitCommitHorizontal,
  Network,
  Radar,
  ShieldCheck,
  TerminalSquare,
  Zap,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';

const tasks = [
  ['Infrastructure', 'Kubernetes state collected', 'complete'],
  ['Telemetry', 'Anomaly onset correlated', 'complete'],
  ['Change analysis', 'Deployment diff inspected', 'complete'],
  ['Verifier', 'Falsifying top hypothesis', 'active'],
];

const evidence = [
  {
    id: 'EV-018',
    icon: Activity,
    source: 'Telemetry / neural model',
    title: 'Memory anomaly began 42s after rollout',
    detail: 'score 0.94 · payments memory +286% · onset 14:31:08',
    tone: 'cyan',
  },
  {
    id: 'EV-021',
    icon: Box,
    source: 'Kubernetes',
    title: 'payments-7fc8 restarted with OOMKilled',
    detail: 'exit 137 · restart count 4 · limit 256Mi',
    tone: 'red',
  },
  {
    id: 'EV-026',
    icon: GitCommitHorizontal,
    source: 'Change analysis',
    title: 'Memory limit reduced in release 8f2c1a',
    detail: '512Mi → 256Mi · deployed by release-bot',
    tone: 'amber',
  },
];

export default function Home() {
  const [decision, setDecision] = useState<'pending' | 'approved' | 'rejected'>(
    'pending',
  );

  return (
    <main className="min-h-screen bg-background text-foreground">
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
          <span className="hidden h-5 w-px bg-white/10 sm:block" />
          <nav
            aria-label="Primary"
            className="hidden items-center gap-1 text-xs text-muted-foreground sm:flex"
          >
            <Link
              className="rounded-md bg-white/7 px-3 py-1.5 text-white"
              href="#incident"
            >
              Incidents
            </Link>
            <Link
              className="rounded-md px-3 py-1.5 hover:bg-white/5 hover:text-white"
              href="#evidence"
            >
              Evidence
            </Link>
            <Link
              className="rounded-md px-3 py-1.5 hover:bg-white/5 hover:text-white"
              href="/benchmarks"
            >
              Benchmarks
            </Link>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <Badge
              variant="outline"
              className="border-emerald-400/20 bg-emerald-400/8 text-emerald-300"
            >
              <span className="size-1.5 rounded-full bg-emerald-300 shadow-[0_0_8px_#6ee7b7]" />
              System nominal
            </Badge>
            <Button
              variant="outline"
              size="sm"
              className="hidden border-white/10 bg-white/4 text-zinc-300 sm:inline-flex"
            >
              <TerminalSquare /> Trace console
            </Button>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-[1600px] grid-cols-1 gap-5 px-4 py-5 sm:px-6 xl:grid-cols-[260px_minmax(0,1fr)_330px]">
        <aside className="space-y-4 xl:sticky xl:top-[76px] xl:h-[calc(100vh-96px)]">
          <section>
            <div className="mb-2 flex items-center justify-between px-1">
              <p className="eyebrow">Active incidents</p>
              <span className="font-mono text-[10px] text-zinc-600">03</span>
            </div>
            <button
              aria-label="Open checkout-api incident"
              className="incident-row incident-row-active w-full text-left"
            >
              <span className="mt-1 size-2 shrink-0 rounded-full bg-red-400 shadow-[0_0_10px_#f87171]" />
              <span className="min-w-0 flex-1">
                <span className="flex items-center justify-between gap-3">
                  <strong className="truncate text-sm font-medium text-white">
                    checkout-api
                  </strong>
                  <span className="font-mono text-[10px] text-zinc-500">
                    04:12
                  </span>
                </span>
                <span className="mt-1 block truncate text-xs text-zinc-400">
                  Error rate &amp; latency spike
                </span>
              </span>
            </button>
            <button
              aria-label="Open worker-queue incident"
              className="incident-row w-full text-left"
            >
              <span className="mt-1 size-2 shrink-0 rounded-full bg-amber-400" />
              <span className="min-w-0 flex-1">
                <span className="flex items-center justify-between gap-3">
                  <strong className="truncate text-sm font-medium text-zinc-300">
                    worker-queue
                  </strong>
                  <span className="font-mono text-[10px] text-zinc-600">
                    18:40
                  </span>
                </span>
                <span className="mt-1 block truncate text-xs text-zinc-500">
                  Queue depth saturation
                </span>
              </span>
            </button>
          </section>

          <section className="panel p-3.5">
            <div className="mb-3 flex items-center justify-between">
              <p className="eyebrow">Execution budget</p>
              <Zap className="size-3.5 text-amber-300" />
            </div>
            <div className="space-y-3">
              <BudgetRow label="Tool calls" value="18 / 40" percent={45} />
              <BudgetRow
                label="Model tokens"
                value="21.4k / 60k"
                percent={36}
              />
              <BudgetRow label="Runtime" value="84s / 300s" percent={28} />
              <BudgetRow
                label="Estimated cost"
                value="$0.18 / $1.00"
                percent={18}
              />
            </div>
          </section>

          <section className="panel p-3.5">
            <p className="eyebrow mb-3">Agent task tree</p>
            <ol className="space-y-3">
              {tasks.map(([name, detail, status], index) => (
                <li key={name} className="relative flex gap-3">
                  {index < tasks.length - 1 && (
                    <span className="absolute left-[7px] top-5 h-7 w-px bg-white/10" />
                  )}
                  {status === 'complete' ? (
                    <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-emerald-300" />
                  ) : (
                    <CircleDot className="mt-0.5 size-3.5 shrink-0 animate-pulse text-cyan-300" />
                  )}
                  <span>
                    <strong className="block text-xs font-medium text-zinc-200">
                      {name}
                    </strong>
                    <span className="mt-0.5 block text-[11px] leading-4 text-zinc-500">
                      {detail}
                    </span>
                  </span>
                </li>
              ))}
            </ol>
          </section>
        </aside>

        <section id="incident" className="min-w-0 space-y-5">
          <Card className="hero-panel border-0 py-0 ring-0">
            <CardContent className="relative overflow-hidden p-5 sm:p-6">
              <div className="absolute -right-16 -top-24 size-64 rounded-full bg-red-400/8 blur-3xl" />
              <div className="relative flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
                <div>
                  <div className="mb-3 flex flex-wrap items-center gap-2">
                    <Badge
                      variant="destructive"
                      className="bg-red-400/12 text-red-300"
                    >
                      SEV-2
                    </Badge>
                    <Badge
                      variant="outline"
                      className="border-white/10 text-zinc-400"
                    >
                      INC-2026-0902-0041
                    </Badge>
                    <span className="flex items-center gap-1.5 text-xs text-zinc-500">
                      <Clock3 className="size-3" /> started 4m 12s ago
                    </span>
                  </div>
                  <h1 className="text-balance text-2xl font-semibold tracking-[-0.035em] text-white sm:text-3xl">
                    checkout-api degradation
                  </h1>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-400">
                    Error rate increased from 1.3% to 24.8% while p95 latency
                    reached 3.7s. Sentinel is correlating deployment, runtime,
                    and telemetry evidence.
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Badge
                    variant="outline"
                    className="h-7 border-cyan-300/20 bg-cyan-300/7 px-3 text-cyan-200"
                  >
                    <span className="size-1.5 animate-pulse rounded-full bg-cyan-300" />{' '}
                    Verifying
                  </Badge>
                  <Button
                    variant="outline"
                    size="sm"
                    className="border-white/10 bg-white/4 text-zinc-300"
                  >
                    Escalate
                  </Button>
                </div>
              </div>
              <div className="relative mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Metric
                  label="Error rate"
                  value="24.8%"
                  delta="+23.5 pp"
                  alert
                />
                <Metric
                  label="p95 latency"
                  value="3.7s"
                  delta="+1,933%"
                  alert
                />
                <Metric label="Restarts" value="4" delta="last 5 min" />
                <Metric
                  label="Confidence"
                  value="91%"
                  delta="provisional"
                  good
                />
              </div>
            </CardContent>
          </Card>

          <section id="evidence" className="panel overflow-hidden">
            <div className="flex items-center justify-between border-b border-white/8 px-4 py-3.5 sm:px-5">
              <div>
                <p className="eyebrow">Evidence timeline</p>
                <h2 className="mt-1 text-sm font-medium text-white">
                  Correlated signals
                </h2>
              </div>
              <Button
                variant="ghost"
                size="sm"
                className="text-xs text-zinc-400"
              >
                18 artifacts <ArrowUpRight />
              </Button>
            </div>
            <div className="divide-y divide-white/7">
              {evidence.map((item) => (
                <article
                  key={item.id}
                  className="group grid gap-3 px-4 py-4 transition-colors hover:bg-white/[0.025] sm:grid-cols-[38px_minmax(0,1fr)_auto] sm:px-5"
                >
                  <span className={`evidence-icon evidence-icon-${item.tone}`}>
                    <item.icon className="size-4" />
                  </span>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-[10px] text-zinc-600">
                        {item.id}
                      </span>
                      <span className="text-[10px] uppercase tracking-wider text-zinc-500">
                        {item.source}
                      </span>
                    </div>
                    <h3 className="mt-1.5 text-sm font-medium text-zinc-200">
                      {item.title}
                    </h3>
                    <p className="mt-1 font-mono text-[11px] text-zinc-500">
                      {item.detail}
                    </p>
                  </div>
                  <ChevronRight className="hidden size-4 self-center text-zinc-700 transition-transform group-hover:translate-x-0.5 group-hover:text-zinc-400 sm:block" />
                </article>
              ))}
            </div>
          </section>

          <section className="panel p-4 sm:p-5">
            <div className="mb-4 flex items-start justify-between gap-4">
              <div>
                <p className="eyebrow">Ranked hypothesis</p>
                <h2 className="mt-1.5 text-base font-medium text-white">
                  Memory limit regression caused OOM crash loop
                </h2>
              </div>
              <span className="font-mono text-xl font-semibold text-cyan-200">
                0.91
              </span>
            </div>
            <p className="text-sm leading-6 text-zinc-400">
              The payments memory limit was halved in the most recent release.
              Memory saturation began immediately after rollout and precedes
              every OOMKilled event.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {['EV-018', 'EV-021', 'EV-026'].map((id) => (
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
                <ShieldCheck /> evidence valid
              </Badge>
            </div>
          </section>
        </section>

        <aside className="space-y-5 xl:sticky xl:top-[76px] xl:h-[calc(100vh-96px)]">
          <section className="panel overflow-hidden">
            <div className="border-b border-white/8 px-4 py-3.5">
              <p className="eyebrow">Verifier / critic</p>
              <div className="mt-2 flex items-center gap-2 text-sm font-medium text-white">
                <ShieldCheck className="size-4 text-cyan-300" /> Falsification
                in progress
              </div>
            </div>
            <div className="space-y-3 p-4">
              <VerifierRow label="Deployment timing" status="supported" />
              <VerifierRow
                label="Traffic-spike alternative"
                status="rejected"
              />
              <VerifierRow
                label="Database lock alternative"
                status="rejected"
              />
              <VerifierRow
                label="Node pressure correlation"
                status="checking"
              />
            </div>
          </section>

          <section className="panel overflow-hidden">
            <div className="border-b border-white/8 px-4 py-3.5">
              <p className="eyebrow">Proposed remediation</p>
              <h2 className="mt-1.5 text-sm font-medium text-white">
                Restore payments memory limit
              </h2>
            </div>
            <div className="p-4">
              <div className="mb-3 flex items-center justify-between">
                <Badge
                  variant="outline"
                  className="border-amber-300/20 bg-amber-300/7 text-amber-200"
                >
                  <AlertTriangle /> Low-risk write
                </Badge>
                <span className="font-mono text-[10px] text-zinc-600">
                  PATCH-0041
                </span>
              </div>
              <pre className="overflow-x-auto rounded-lg border border-white/8 bg-black/30 p-3 font-mono text-[11px] leading-5 text-zinc-400">
                <code>
                  <span className="text-red-300">- memory: 256Mi</span>
                  {'\n'}
                  <span className="text-emerald-300">+ memory: 512Mi</span>
                </code>
              </pre>
              <p className="mt-3 text-xs leading-5 text-zinc-500">
                Validated against policy and Kubernetes schema. Execution
                requires explicit approval.
              </p>
              {decision === 'pending' ? (
                <div className="mt-4 grid grid-cols-2 gap-2">
                  <Button
                    onClick={() => setDecision('rejected')}
                    variant="outline"
                    className="border-white/10 bg-white/4 text-zinc-300"
                  >
                    Reject
                  </Button>
                  <Button
                    onClick={() => setDecision('approved')}
                    className="bg-cyan-300 text-slate-950 hover:bg-cyan-200"
                  >
                    <ShieldCheck /> Approve
                  </Button>
                </div>
              ) : (
                <output
                  className={`mt-4 block rounded-lg border px-3 py-2.5 text-center text-xs ${decision === 'approved' ? 'border-emerald-300/20 bg-emerald-300/7 text-emerald-200' : 'border-red-300/20 bg-red-300/7 text-red-200'}`}
                >
                  Proposal {decision}. Decision recorded in the audit trail.
                </output>
              )}
            </div>
          </section>

          <section id="benchmarks" className="panel p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="eyebrow">Benchmark pulse</p>
                <p className="mt-1 text-sm font-medium text-white">
                  Smoke suite · 8 scenarios
                </p>
              </div>
              <Network className="size-4 text-violet-300" />
            </div>
            <div className="mt-4 grid grid-cols-3 gap-2 text-center">
              <MiniMetric value="87.5%" label="accuracy" />
              <MiniMetric value="0%" label="unsafe" />
              <MiniMetric value="1.2s" label="p95" />
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

function BudgetRow({
  label,
  value,
  percent,
}: {
  label: string;
  value: string;
  percent: number;
}) {
  return (
    <div>
      <div className="mb-1.5 flex justify-between text-[11px]">
        <span className="text-zinc-500">{label}</span>
        <span className="font-mono text-zinc-400">{value}</span>
      </div>
      <Progress
        value={percent}
        className="[&_[data-slot=progress-indicator]]:bg-cyan-300/80 [&_[data-slot=progress-track]]:bg-white/7"
      />
    </div>
  );
}

function Metric({
  label,
  value,
  delta,
  alert,
  good,
}: {
  label: string;
  value: string;
  delta: string;
  alert?: boolean;
  good?: boolean;
}) {
  return (
    <div className="metric">
      <span className="text-[10px] uppercase tracking-[0.12em] text-zinc-600">
        {label}
      </span>
      <strong
        className={`mt-1 block font-mono text-xl ${alert ? 'text-red-300' : good ? 'text-emerald-300' : 'text-white'}`}
      >
        {value}
      </strong>
      <span className="mt-0.5 block text-[10px] text-zinc-600">{delta}</span>
    </div>
  );
}

function VerifierRow({ label, status }: { label: string; status: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <span
        className={`size-1.5 rounded-full ${status === 'supported' ? 'bg-emerald-300' : status === 'checking' ? 'animate-pulse bg-cyan-300' : 'bg-zinc-700'}`}
      />
      <span className="flex-1 text-xs text-zinc-400">{label}</span>
      <span className="font-mono text-[9px] uppercase tracking-wider text-zinc-600">
        {status}
      </span>
    </div>
  );
}

function MiniMetric({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-lg border border-white/7 bg-white/[0.025] py-2.5">
      <strong className="block font-mono text-sm text-zinc-200">{value}</strong>
      <span className="mt-0.5 block text-[9px] uppercase tracking-wider text-zinc-600">
        {label}
      </span>
    </div>
  );
}
