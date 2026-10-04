"use client";

import { ArrowUpRight, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { KeyValue, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { EmptyState, ErrorState, Skeleton, TableSkeleton } from "@/components/ui/states";
import {
  type DebugEvent,
  type IntegrationsStatus,
  useAnalyticsDebugEvents,
  useIntegrations,
  useRecheckIntegrations,
} from "@/lib/api/admin";
import { formatDateTime, titleCase } from "@/lib/format";
import {
  deliveryBadge,
  exportSummary,
  integrationBadge,
  propertyPairs,
  showAnalyticsDebugger,
} from "@/lib/integrations";

function Code({ children }: { children: ReactNode }) {
  return <span className="text-2xs text-fg-muted bg-surface-2 rounded-sm px-1 font-mono">{children}</span>;
}

function ExternalLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="text-accent inline-flex items-center gap-0.5 text-xs hover:underline"
    >
      {children}
      <ArrowUpRight className="size-3" />
    </a>
  );
}

function AmplitudePanel({ amplitude: a }: { amplitude: IntegrationsStatus["amplitude"] }) {
  const badge = integrationBadge(a.status);
  const items: { label: string; value: ReactNode }[] = [
    { label: "Status", value: a.detail },
    ...(a.server_zone ? [{ label: "Data center", value: a.server_zone }] : []),
    { label: "Tracking plan", value: `${a.event_types} event types, sent server-side` },
  ];
  if (a.status !== "not_configured") {
    items.push({
      label: "Last export",
      value: a.last_export ? (
        <>
          <span>
            {titleCase(a.last_export.source)} · {formatDateTime(a.last_export.finished_at)}
          </span>
          <span className="text-fg-muted block text-xs">{exportSummary(a.last_export)}</span>
          {a.last_export.detail ? (
            <span className="text-danger block text-xs">{a.last_export.detail}</span>
          ) : null}
        </>
      ) : (
        <span className="text-fg-muted">
          None recorded. Run <Code>make amplitude-backfill</Code> or reseed.
        </span>
      ),
    });
  }
  return (
    <Panel className="self-start">
      <PanelHeader
        title="Amplitude"
        description="Behavioral product analytics. Events reach Amplitude only after ClickHouse has stored them."
        actions={<Badge tone={badge.tone}>{badge.label}</Badge>}
      />
      <PanelBody>
        <KeyValue items={items} />
      </PanelBody>
      {a.status === "not_configured" ? (
        <PanelBody className="border-border text-fg-muted border-t text-xs">
          Add <Code>AMPLITUDE_API_KEY</Code> (and <Code>AMPLITUDE_SERVER_ZONE=EU</Code> for EU projects) to{" "}
          <Code>.env</Code>, restart the API, then run <Code>make amplitude-backfill</Code>.
        </PanelBody>
      ) : null}
    </Panel>
  );
}

function MetabasePanel({ metabase: m }: { metabase: IntegrationsStatus["metabase"] }) {
  const badge = integrationBadge(m.status);
  return (
    <Panel className="self-start">
      <PanelHeader
        title="Metabase"
        description="Stakeholder dashboards over Orbit's ClickHouse events and experiment readouts."
        actions={
          <>
            {m.url ? <ExternalLink href={m.url}>Open</ExternalLink> : null}
            <Badge tone={badge.tone}>{badge.label}</Badge>
          </>
        }
      />
      <PanelBody>
        <KeyValue
          items={[
            { label: "Status", value: m.detail },
            ...(m.version ? [{ label: "Version", value: m.version }] : []),
            ...(m.provisioned_at
              ? [{ label: "Dashboards built", value: formatDateTime(m.provisioned_at) }]
              : []),
          ]}
        />
      </PanelBody>
      {m.dashboards.length ? (
        <ul className="divide-border border-border divide-y border-t">
          {m.dashboards.map((d) => (
            <li key={d.name} className="flex items-center gap-3 px-4 py-2 text-[13px]">
              <span className="text-fg font-medium">{d.name}</span>
              <span className="text-fg-subtle text-xs">{d.cards} cards</span>
              <span className="ml-auto">{d.url ? <ExternalLink href={d.url}>Open</ExternalLink> : null}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {m.status === "not_configured" ? (
        <PanelBody className="border-border text-fg-muted border-t text-xs">
          Set <Code>METABASE_ADMIN_EMAIL</Code>, <Code>METABASE_ADMIN_PASSWORD</Code> and{" "}
          <Code>METABASE_URL</Code> in <Code>.env</Code>, then run <Code>make bi</Code>.
        </PanelBody>
      ) : null}
    </Panel>
  );
}

const DEBUG_SOURCE: Record<string, (configured: boolean) => string> = {
  last_export: () => "The last events sent to Amplitude, with Amplitude's answer for each.",
  clickhouse_preview: (configured) =>
    `Preview of the latest ClickHouse sessions mapped through the tracking plan. ${
      configured
        ? "These were not part of a recorded export."
        : "Amplitude isn't configured, so nothing was sent."
    }`,
  empty: () => "No events in ClickHouse yet.",
};

function Properties({ event }: { event: DebugEvent }) {
  const userSet = (event.user_properties.$set ?? {}) as Record<string, unknown>;
  const chips = [
    ...propertyPairs(event.event_properties),
    ...propertyPairs(userSet).map(([k, v]): [string, string] => [`user.${k}`, v]),
    ...(event.revenue != null ? [["revenue", String(event.revenue)] as [string, string]] : []),
  ];
  if (!chips.length) return <span className="text-fg-faint text-xs">none</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {chips.map(([k, v]) => (
        <Code key={k}>
          {k}={v}
        </Code>
      ))}
    </div>
  );
}

function AnalyticsDebugger() {
  const events = useAnalyticsDebugEvents(true);
  const data = events.data;
  return (
    <Panel className="xl:col-span-2">
      <PanelHeader
        title="Analytics debugger"
        description={
          data
            ? DEBUG_SOURCE[data.source](data.amplitude_configured)
            : "Events as the analytics layer produced them."
        }
        actions={<Badge tone="warning">development only</Badge>}
      />
      {events.isPending ? (
        <PanelBody>
          <TableSkeleton rows={6} cols={5} />
        </PanelBody>
      ) : events.isError ? (
        <ErrorState error={events.error} onRetry={() => events.refetch()} />
      ) : !data?.events.length ? (
        <EmptyState title="No events yet" description="Load the demo dataset with `make seed`." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="text-2xs text-fg-subtle border-border border-b uppercase">
                <th className="px-4 py-2 text-left font-medium">Time</th>
                <th className="px-3 py-2 text-left font-medium">Event</th>
                <th className="px-3 py-2 text-left font-medium">Properties</th>
                <th className="px-3 py-2 text-left font-medium">ClickHouse</th>
                <th className="px-4 py-2 text-left font-medium">Amplitude</th>
              </tr>
            </thead>
            <tbody>
              {data.events.map((e) => {
                const delivery = deliveryBadge(e.amplitude);
                return (
                  <tr
                    key={e.insert_id}
                    className="border-border hover:bg-surface border-b align-top last:border-b-0"
                  >
                    <td className="tabular text-fg-subtle px-4 py-2 text-xs whitespace-nowrap">
                      {formatDateTime(e.time)}
                    </td>
                    <td className="px-3 py-2">
                      <div className="text-fg font-medium whitespace-nowrap">{e.event_type}</div>
                      <div className="text-fg-subtle text-2xs font-mono">
                        {e.orbit_event ?? "—"} · user {e.user_id}
                        {e.platform ? ` · ${e.platform}` : ""}
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <Properties event={e} />
                    </td>
                    <td className="px-3 py-2">
                      <Badge tone="success">✓ Stored</Badge>
                    </td>
                    <td className="px-4 py-2">
                      <Badge tone={delivery.tone}>{delivery.label}</Badge>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

export function IntegrationsPanel() {
  const status = useIntegrations();
  const recheck = useRecheckIntegrations();

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

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <div className="text-fg-subtle flex items-center gap-3 text-xs xl:col-span-2">
        <span>Live checks against each provider · {formatDateTime(s.checked_at)}</span>
        <Button
          size="sm"
          variant="ghost"
          className="ml-auto"
          onClick={() => recheck.mutate()}
          loading={recheck.isPending}
        >
          <RefreshCw className="size-3.5" />
          Re-check
        </Button>
      </div>
      <AmplitudePanel amplitude={s.amplitude} />
      <MetabasePanel metabase={s.metabase} />
      {showAnalyticsDebugger(process.env.NODE_ENV, s.debugger) ? <AnalyticsDebugger /> : null}
    </div>
  );
}
