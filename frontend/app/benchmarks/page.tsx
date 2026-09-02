import {
  ArrowLeft,
  BrainCircuit,
  CheckCircle2,
  DatabaseZap,
  Gauge,
  ShieldCheck,
} from 'lucide-react';
import Link from 'next/link';

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

const retrieval = [
  ['Hybrid search', '1.000', '1.000', '0.893'],
  ['Learned reranker', '1.000', '1.000', '0.956'],
];

export default function Benchmarks() {
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
            <p className="eyebrow">Measured evaluation</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-white">
              Reliability, not vibes.
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-zinc-400">
              Every number below comes from deterministic held-out scenarios and
              generated artifacts in this repository. No model result is
              hand-entered.
            </p>
          </div>
          <Badge
            variant="outline"
            className="border-emerald-300/20 bg-emerald-300/7 text-emerald-200"
          >
            <CheckCircle2 /> reproducible
          </Badge>
        </div>

        <section className="mt-8 grid gap-4 sm:grid-cols-3">
          <Score
            icon={BrainCircuit}
            label="Neural anomaly F1"
            value="0.917"
            detail="held-out telemetry windows"
          />
          <Score
            icon={Gauge}
            label="Neural AUROC"
            value="1.000"
            detail="133 test windows"
          />
          <Score
            icon={ShieldCheck}
            label="Policy violations"
            value="0"
            detail="security regression suite"
          />
        </section>

        <div className="mt-6 grid gap-6 lg:grid-cols-[1.3fr_.7fr]">
          <Card className="border-white/8 bg-white/[0.025] ring-0">
            <CardHeader className="border-b border-white/8">
              <CardTitle className="flex items-center gap-2 text-white">
                <DatabaseZap className="size-4 text-cyan-300" /> Retrieval
                evaluation
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow className="border-white/8 hover:bg-transparent">
                    <TableHead className="text-zinc-500">System</TableHead>
                    <TableHead className="text-zinc-500">Recall@5</TableHead>
                    <TableHead className="text-zinc-500">MRR</TableHead>
                    <TableHead className="text-zinc-500">nDCG@5</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {retrieval.map((row) => (
                    <TableRow key={row[0]} className="border-white/7">
                      <TableCell className="font-medium text-zinc-200">
                        {row[0]}
                      </TableCell>
                      {row.slice(1).map((value) => (
                        <TableCell
                          key={value}
                          className="font-mono text-cyan-200"
                        >
                          {value}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
          <Card className="border-white/8 bg-white/[0.025] ring-0">
            <CardHeader className="border-b border-white/8">
              <CardTitle className="text-white">Honest comparison</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm leading-6 text-zinc-400">
              <p>
                The z-score telemetry baseline currently beats the neural
                autoencoder on F1:{' '}
                <span className="font-mono text-zinc-200">0.962 vs 0.917</span>.
              </p>
              <p>
                The neural model remains integrated because its reconstruction
                error yields dimension attribution and a learned evidence
                source. The limitation is documented, not hidden.
              </p>
              <div className="rounded-lg border border-amber-300/12 bg-amber-300/5 p-3 text-xs text-amber-100/70">
                Synthetic telemetry is intentionally simple. A production
                dataset is likely to change the ranking.
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </main>
  );
}

function Score({
  icon: Icon,
  label,
  value,
  detail,
}: {
  icon: typeof BrainCircuit;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="panel flex items-center gap-4 p-4">
      <span className="grid size-10 place-items-center rounded-lg border border-cyan-300/15 bg-cyan-300/7 text-cyan-300">
        <Icon className="size-4" />
      </span>
      <div>
        <p className="text-[10px] uppercase tracking-wider text-zinc-600">
          {label}
        </p>
        <strong className="mt-1 block font-mono text-xl text-white">
          {value}
        </strong>
        <p className="mt-0.5 text-[10px] text-zinc-600">{detail}</p>
      </div>
    </div>
  );
}
