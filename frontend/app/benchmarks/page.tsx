'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { ArrowLeft, DatabaseZap, ShieldAlert } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { getLatestBenchmark } from '@/lib/api';

type MetricRow = {
  trials?: number;
  root_cause_accuracy?: number;
  selective_accuracy?: number;
  abstention_rate?: number;
  evidence_recall?: number;
  policy_safety_rate?: number;
  p95_total_time_ms?: number;
  input_tokens?: number;
  output_tokens?: number;
  estimated_cost_usd?: number;
};

export default function Benchmarks() {
  const [report, setReport] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void getLatestBenchmark()
      .then(setReport)
      .catch((cause: unknown) => {
        setError(
          cause instanceof Error ? cause.message : 'Unable to load report',
        );
      });
  }, []);

  const manifest = isRecord(report?.manifest) ? report.manifest : {};
  const metrics = isRecord(report?.metrics) ? report.metrics : {};
  const independentlyMeasured = manifest.protocol_version === 'independent-v2';

  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-12">
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-xs text-zinc-500 hover:text-zinc-200"
        >
          <ArrowLeft className="size-3.5" /> Back to incident command
        </Link>
        <div className="mt-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="eyebrow">Evaluation evidence</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-white">
              Measured systems, visible limitations.
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-zinc-400">
              This view reads the checked-in report through the Sentinel API. A
              result becomes a current claim only after the independent-v2
              protocol is recorded in its manifest.
            </p>
          </div>
          <Badge
            variant="outline"
            className={
              independentlyMeasured
                ? 'border-emerald-300/20 bg-emerald-300/7 text-emerald-200'
                : 'border-amber-300/20 bg-amber-300/7 text-amber-200'
            }
          >
            <ShieldAlert />
            {independentlyMeasured
              ? 'independent protocol'
              : 'legacy report quarantined'}
          </Badge>
        </div>

        {error && (
          <div className="mt-8 rounded-xl border border-red-300/20 bg-red-300/7 p-4 text-sm text-red-200">
            {error}
          </div>
        )}

        {independentlyMeasured && (
          <div className="mt-8 grid gap-3 sm:grid-cols-3">
            <ProofPoint
              label="Isolated executions"
              value={stringValue(manifest.independent_trial_count)}
            />
            <ProofPoint
              label="Runtime labels"
              value={
                manifest.evaluator_labels_in_runtime_snapshot === false
                  ? 'excluded'
                  : 'unverified'
              }
            />
            <ProofPoint
              label="Source revision"
              value={shortRevision(manifest.source_revision)}
              mono
            />
          </div>
        )}

        <Card className="mt-8 border-white/8 bg-white/[0.025] ring-0">
          <CardHeader className="border-b border-white/8">
            <CardTitle className="flex items-center gap-2 text-white">
              <DatabaseZap className="size-4 text-cyan-300" /> Systems in latest
              report
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow className="border-white/8 hover:bg-transparent">
                  <TableHead>System</TableHead>
                  <TableHead>Trials</TableHead>
                  <TableHead>Overall</TableHead>
                  <TableHead>Selective</TableHead>
                  <TableHead>Abstention</TableHead>
                  <TableHead>Evidence recall</TableHead>
                  <TableHead>Policy safety</TableHead>
                  <TableHead>p95 total</TableHead>
                  <TableHead>Tokens in/out</TableHead>
                  <TableHead>Cost</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {Object.entries(metrics).map(([system, raw]) => {
                  const row = (isRecord(raw) ? raw : {}) as MetricRow;
                  return (
                    <TableRow key={system} className="border-white/7">
                      <TableCell className="font-mono text-xs text-zinc-200">
                        {system}
                      </TableCell>
                      <TableCell>{row.trials ?? '—'}</TableCell>
                      <TableCell>{percent(row.root_cause_accuracy)}</TableCell>
                      <TableCell>{percent(row.selective_accuracy)}</TableCell>
                      <TableCell>{percent(row.abstention_rate)}</TableCell>
                      <TableCell>{percent(row.evidence_recall)}</TableCell>
                      <TableCell>{percent(row.policy_safety_rate)}</TableCell>
                      <TableCell>
                        {number(row.p95_total_time_ms, 'ms')}
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {tokenPair(row.input_tokens, row.output_tokens)}
                      </TableCell>
                      <TableCell>
                        {number(row.estimated_cost_usd, ' USD')}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
            {!report && !error && (
              <p className="py-12 text-center text-sm text-zinc-600">
                Loading report…
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}

function ProofPoint({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="rounded-xl border border-white/8 bg-white/[0.025] px-4 py-3">
      <p className="text-[10px] uppercase tracking-[0.18em] text-zinc-600">
        {label}
      </p>
      <p className={`mt-1 text-sm text-zinc-200 ${mono ? 'font-mono' : ''}`}>
        {value}
      </p>
    </div>
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function percent(value?: number): string {
  return value === undefined ? '—' : `${(value * 100).toFixed(1)}%`;
}

function number(value?: number, suffix = ''): string {
  return value === undefined ? '—' : `${value.toFixed(2)}${suffix}`;
}

function stringValue(value: unknown): string {
  return typeof value === 'number' || typeof value === 'string'
    ? String(value)
    : '—';
}

function shortRevision(value: unknown): string {
  return typeof value === 'string' ? value.slice(0, 12) : '—';
}

function tokenPair(input?: number, output?: number): string {
  if (input === undefined || output === undefined) return '—';
  return `${input.toLocaleString()}/${output.toLocaleString()}`;
}
