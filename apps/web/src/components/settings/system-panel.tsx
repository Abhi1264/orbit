"use client";

import { Badge, type BadgeTone } from "@/components/ui/badge";
import { KeyValue, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { ErrorState, Skeleton } from "@/components/ui/states";
import { type SystemStatus, useSystemStatus } from "@/lib/api/admin";
import { formatCompactCount, formatDate, formatDateTime, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";

function Dot({ tone }: { tone: BadgeTone }) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-block size-2 rounded-full",
        tone === "success" && "bg-success",
        tone === "danger" && "bg-danger",
        tone === "warning" && "bg-warning",
        tone === "neutral" && "bg-fg-subtle",
      )}
    />
  );
}

const DEP_LABEL: Record<string, string> = {
  postgres: "PostgreSQL",
  clickhouse: "ClickHouse",
  redis: "Redis",
};

function Dependencies({ status }: { status: SystemStatus }) {
  return (
    <ul className="divide-border divide-y">
      {status.dependencies.map((d) => (
        <li key={d.name} className="flex items-center gap-3 px-4 py-2 text-[13px]">
          <Dot tone={d.ok ? "success" : "danger"} />
          <span className="text-fg w-24 font-medium">{DEP_LABEL[d.name] ?? titleCase(d.name)}</span>
          <span className="text-fg-muted min-w-0 flex-1 truncate">{d.detail}</span>
          {d.latency_ms != null ? (
            <span className="tabular text-fg-subtle text-xs">{d.latency_ms} ms</span>
          ) : null}
        </li>
      ))}
      <li className="flex items-center gap-3 px-4 py-2 text-[13px]">
        <Dot tone={status.worker_alive ? "success" : "warning"} />
        <span className="text-fg w-24 font-medium">Worker</span>
        <span className="text-fg-muted min-w-0 flex-1 truncate">
          {status.worker_heartbeat
            ? `${status.worker_alive ? "Alive" : "Stale"} · last heartbeat ${formatDateTime(status.worker_heartbeat)}`
            : "No heartbeat. Start it with `make worker`; scheduled anomaly detection depends on it."}
        </span>
      </li>
    </ul>
  );
}

export function SystemPanel() {
  const status = useSystemStatus();

  if (status.isPending) {
    return (
      <div className="grid gap-4 xl:grid-cols-2">
        <Skeleton className="h-48" />
        <Skeleton className="h-48" />
      </div>
    );
  }
  if (status.isError) {
    return <ErrorState error={status.error} onRetry={() => status.refetch()} />;
  }
  const s = status.data;
  const degraded = s.dependencies.some((d) => !d.ok);

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Panel className="self-start">
        <PanelHeader
          title="Dependencies"
          description={`Checked ${formatDateTime(s.generated_at)} · refreshes every 30s`}
          actions={degraded ? <Badge tone="danger">degraded</Badge> : <Badge tone="success">healthy</Badge>}
        />
        <Dependencies status={s} />
      </Panel>

      <Panel className="self-start">
        <PanelHeader title="Runtime" />
        <PanelBody>
          <KeyValue
            items={[
              { label: "Environment", value: s.env },
              { label: "Version", value: s.version },
              {
                label: "AI analyst",
                value:
                  s.llm_mode === "llm" ? (
                    <>
                      <Badge tone="accent">LLM</Badge>{" "}
                      <span className="text-fg-muted ml-1">{s.llm_model}</span>
                    </>
                  ) : (
                    <>
                      <Badge>demo mode</Badge>{" "}
                      <span className="text-fg-subtle ml-1 text-xs">
                        deterministic playbooks; set LLM_API_KEY to enable a model
                      </span>
                    </>
                  ),
              },
              { label: "AI runs today", value: `${s.ai_runs_24h} (${s.ai_errors_24h} failed)` },
              { label: "Query cache", value: `${s.data.cache_keys} keys` },
            ]}
          />
        </PanelBody>
      </Panel>

      <Panel className="self-start">
        <PanelHeader title="Event data" description="ClickHouse `events` table" />
        <PanelBody>
          <KeyValue
            items={[
              {
                label: "Range",
                value:
                  s.data.data_start && s.data.data_end
                    ? `${formatDate(s.data.data_start)} – ${formatDate(s.data.data_end, { month: "short", day: "numeric", year: "numeric" })}`
                    : "empty",
              },
              {
                label: "Events",
                value: <span className="tabular">{s.data.events.toLocaleString("en-IN")}</span>,
              },
              { label: "Users", value: <span className="tabular">{formatCompactCount(s.data.users)}</span> },
              {
                label: "Last anomaly scan",
                value: s.last_anomaly_detection ? formatDateTime(s.last_anomaly_detection) : "never",
              },
            ]}
          />
        </PanelBody>
      </Panel>

      <Panel className="self-start">
        <PanelHeader title="Scheduled jobs" description="Written by the worker after each run." />
        {s.jobs.length === 0 ? (
          <PanelBody className="text-fg-subtle text-[13px]">No job runs recorded.</PanelBody>
        ) : (
          <ul className="divide-border divide-y">
            {s.jobs.map((j) => (
              <li key={j.job} className="px-4 py-2 text-[13px]">
                <div className="flex items-center gap-3">
                  <Dot tone={j.ok === null ? "neutral" : j.ok ? "success" : "danger"} />
                  <span className="text-fg font-medium">{titleCase(j.job)}</span>
                  <span className="text-fg-subtle ml-auto text-xs">
                    {j.at ? formatDateTime(j.at) : "not yet run"}
                  </span>
                </div>
                {Object.keys(j.detail).length ? (
                  <div className="text-fg-muted mt-1 flex flex-wrap gap-x-3 pl-5 text-xs">
                    {Object.entries(j.detail).map(([k, v]) => (
                      <span key={k}>
                        {k} <span className="text-fg tabular">{v}</span>
                      </span>
                    ))}
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel className="self-start xl:col-span-2">
        <PanelHeader title="Application records" />
        <PanelBody className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          {Object.entries(s.counts).map(([k, v]) => (
            <div key={k}>
              <div className="text-fg-subtle text-2xs tracking-wide uppercase">{titleCase(k)}</div>
              <div className="text-fg tabular text-lg font-semibold">{v.toLocaleString("en-IN")}</div>
            </div>
          ))}
        </PanelBody>
      </Panel>
    </div>
  );
}
