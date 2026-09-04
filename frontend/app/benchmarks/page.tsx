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
  abstention_rate?: number;
  policy_safety_rate?: number;
  p95_diagnosis_time_ms?: number;
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
                  <TableHead>Root cause</TableHead>
                  <TableHead>Abstention</TableHead>
                  <TableHead>Policy safety</TableHead>
                  <TableHead>p95 time</TableHead>
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
                      <TableCell>{percent(row.abstention_rate)}</TableCell>
                      <TableCell>{percent(row.policy_safety_rate)}</TableCell>
                      <TableCell>
                        {number(row.p95_diagnosis_time_ms, 'ms')}
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function percent(value?: number): string {
  return value === undefined ? '—' : `${(value * 100).toFixed(1)}%`;
}

function number(value?: number, suffix = ''): string {
  return value === undefined ? '—' : `${value.toFixed(2)}${suffix}`;
}
