"use client";

import { Check } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { KeyValue, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { ErrorState, Skeleton } from "@/components/ui/states";
import { useChangePassword, useRoles } from "@/lib/api/admin";
import { useMe } from "@/lib/api/hooks";
import { titleCase } from "@/lib/format";

export function ProfilePanel() {
  const me = useMe();
  const roles = useRoles();
  const change = useChangePassword();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const mismatch = confirm.length > 0 && next !== confirm;
  const canSubmit = current.length > 0 && next.length >= 8 && next === confirm;

  if (me.isPending) {
    return <Skeleton className="h-40 w-full" />;
  }
  if (me.isError) {
    return <ErrorState error={me.error} />;
  }
  const mine = roles.data?.find((r) => r.role === me.data.role);

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Panel className="self-start">
        <PanelHeader title="Account" />
        <PanelBody>
          <KeyValue
            items={[
              { label: "Name", value: me.data.name },
              { label: "Email", value: me.data.email },
              { label: "Role", value: <Badge tone="accent">{me.data.role}</Badge> },
            ]}
          />
          <div className="text-fg-subtle text-2xs mt-4 mb-1.5 tracking-wide uppercase">
            What this role can do
          </div>
          <ul className="grid grid-cols-2 gap-x-4 gap-y-1 text-[13px]">
            {(mine?.permissions ?? me.data.permissions).map((p) => (
              <li key={p} className="text-fg-muted flex items-center gap-1.5">
                <Check className="text-success size-3" /> {titleCase(p)}
              </li>
            ))}
          </ul>
        </PanelBody>
      </Panel>

      <Panel className="self-start">
        <PanelHeader
          title="Change password"
          description="At least 8 characters. Other sessions stay signed in."
        />
        <PanelBody>
          <form
            className="max-w-sm space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (!canSubmit) return;
              change.mutate(
                { current_password: current, new_password: next },
                {
                  onSuccess: () => {
                    setCurrent("");
                    setNext("");
                    setConfirm("");
                  },
                },
              );
            }}
          >
            <Field label="Current password" htmlFor="pw-current">
              <Input
                id="pw-current"
                type="password"
                autoComplete="current-password"
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
              />
            </Field>
            <Field label="New password" htmlFor="pw-next">
              <Input
                id="pw-next"
                type="password"
                autoComplete="new-password"
                minLength={8}
                value={next}
                onChange={(e) => setNext(e.target.value)}
              />
            </Field>
            <Field
              label="Confirm new password"
              htmlFor="pw-confirm"
              hint={mismatch ? "Passwords don't match." : undefined}
            >
              <Input
                id="pw-confirm"
                type="password"
                autoComplete="new-password"
                aria-invalid={mismatch || undefined}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
              />
            </Field>
            <div className="flex items-center gap-3">
              <Button type="submit" variant="primary" disabled={!canSubmit} loading={change.isPending}>
                Update password
              </Button>
              {change.isSuccess ? <span className="text-success text-xs">Password updated.</span> : null}
              {change.isError ? <span className="text-danger text-xs">{change.error.message}</span> : null}
            </div>
          </form>
        </PanelBody>
      </Panel>
    </div>
  );
}
