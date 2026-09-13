"use client";

import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { ErrorState, TableSkeleton } from "@/components/ui/states";
import {
  type Role,
  type UserAdminOut,
  useAdminUserMutations,
  useAdminUsers,
  useRoles,
} from "@/lib/api/admin";
import { useMe } from "@/lib/api/hooks";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

const ROLES: Role[] = ["viewer", "analyst", "pm", "admin"];
const ROLE_LABEL: Record<Role, string> = { viewer: "Viewer", analyst: "Analyst", pm: "PM", admin: "Admin" };

const ROLE_BLURB: Record<Role, string> = {
  viewer: "Read everything, change nothing.",
  analyst: "Plus: build analyses, ask the analyst, comment, run investigations.",
  pm: "Plus: run experiments, ship releases, own decisions, SOPs and knowledge.",
  admin: "Plus: manage users and system settings.",
};

function UserRow({
  user,
  isSelf,
  onChange,
  onDelete,
  busy,
}: {
  user: UserAdminOut;
  isSelf: boolean;
  onChange: (patch: { role?: Role; is_active?: boolean }) => void;
  onDelete: () => void;
  busy: boolean;
}) {
  return (
    <tr className={cn("border-border border-b last:border-b-0", !user.is_active && "opacity-60")}>
      <td className="px-4 py-2">
        <div className="text-fg font-medium">
          {user.name}
          {isSelf ? <span className="text-fg-subtle ml-1.5 text-xs font-normal">(you)</span> : null}
        </div>
        <div className="text-fg-subtle text-xs">{user.email}</div>
      </td>
      <td className="px-3 py-2">{user.team ?? <span className="text-fg-subtle">—</span>}</td>
      <td className="px-3 py-2">
        <Select
          aria-label={`Role for ${user.name}`}
          value={user.role}
          disabled={isSelf || busy}
          onChange={(e) => onChange({ role: e.target.value as Role })}
          className="h-7 w-28"
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {ROLE_LABEL[r]}
            </option>
          ))}
        </Select>
      </td>
      <td className="px-3 py-2">
        {user.is_active ? <Badge tone="success">active</Badge> : <Badge>deactivated</Badge>}
      </td>
      <td className="tabular text-fg-muted px-3 py-2 whitespace-nowrap">
        {formatDate(user.created_at, { day: "numeric", month: "short", year: "numeric" })}
      </td>
      <td className="px-3 py-2 text-right whitespace-nowrap">
        {isSelf ? null : (
          <>
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() => onChange({ is_active: !user.is_active })}
            >
              {user.is_active ? "Deactivate" : "Reactivate"}
            </Button>
            <Button
              size="icon"
              variant="ghost"
              aria-label={`Delete ${user.name}`}
              disabled={busy}
              onClick={onDelete}
            >
              <Trash2 className="size-3.5" />
            </Button>
          </>
        )}
      </td>
    </tr>
  );
}

export function UsersPanel() {
  const me = useMe();
  const users = useAdminUsers(true);
  const roles = useRoles();
  const { create, update, remove } = useAdminUserMutations();
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "viewer" as Role });
  const [error, setError] = useState<string | null>(null);
  const busy = update.isPending || remove.isPending;

  const submit = () => {
    setError(null);
    create.mutate(form, {
      onSuccess: () => {
        setCreating(false);
        setForm({ name: "", email: "", password: "", role: "viewer" });
      },
      onError: (e) => setError(e.message),
    });
  };

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <Panel>
        <PanelHeader
          title="Users"
          description="Deactivating keeps history intact and ends the user's sessions. Delete is only possible for accounts that never authored anything."
          actions={
            <Button size="sm" variant="primary" onClick={() => setCreating(true)}>
              <Plus className="size-3.5" /> Add user
            </Button>
          }
        />
        {users.isPending ? (
          <TableSkeleton rows={5} cols={5} />
        ) : users.isError ? (
          <PanelBody>
            <ErrorState error={users.error} onRetry={() => users.refetch()} />
          </PanelBody>
        ) : (
          <table className="w-full text-[13px]">
            <thead>
              <tr className="text-fg-subtle text-2xs border-border border-b text-left tracking-wide uppercase">
                <th className="px-4 py-2 font-medium">User</th>
                <th className="px-3 py-2 font-medium">Team</th>
                <th className="px-3 py-2 font-medium">Role</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium">Since</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {users.data.map((u) => (
                <UserRow
                  key={u.id}
                  user={u}
                  isSelf={u.id === me.data?.id}
                  busy={busy}
                  onChange={(patch) =>
                    update.mutate({ id: u.id, ...patch }, { onError: (e) => setError(e.message) })
                  }
                  onDelete={() => {
                    if (window.confirm(`Delete ${u.name}? This cannot be undone.`)) {
                      remove.mutate(u.id, { onError: (e) => setError(e.message) });
                    }
                  }}
                />
              ))}
            </tbody>
          </table>
        )}
        {error && !creating ? (
          <PanelBody className="border-border border-t">
            <p className="text-danger text-xs">{error}</p>
          </PanelBody>
        ) : null}
      </Panel>

      <Panel className="self-start">
        <PanelHeader title="Roles" description="Each role includes everything below it." />
        <PanelBody className="space-y-3">
          {ROLES.map((r) => {
            const perms = roles.data?.find((x) => x.role === r)?.permissions ?? [];
            return (
              <div key={r}>
                <div className="flex items-center gap-2">
                  <Badge tone={r === "admin" ? "accent" : "neutral"}>{r}</Badge>
                  <span className="text-fg-subtle text-xs">{perms.length} permissions</span>
                </div>
                <p className="text-fg-muted mt-1 text-xs">{ROLE_BLURB[r]}</p>
              </div>
            );
          })}
        </PanelBody>
      </Panel>

      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent
          title="Add user"
          description="Joins your team. They can change the password after signing in."
        >
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
          >
            <Field label="Name" htmlFor="nu-name">
              <Input
                id="nu-name"
                required
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </Field>
            <Field label="Email" htmlFor="nu-email">
              <Input
                id="nu-email"
                type="email"
                required
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
              />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Temporary password" htmlFor="nu-pw" hint="At least 8 characters.">
                <Input
                  id="nu-pw"
                  type="text"
                  required
                  minLength={8}
                  autoComplete="off"
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                />
              </Field>
              <Field label="Role" htmlFor="nu-role">
                <Select
                  id="nu-role"
                  value={form.role}
                  onChange={(e) => setForm({ ...form, role: e.target.value as Role })}
                >
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {ROLE_LABEL[r]}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
            {error && creating ? <p className="text-danger text-xs">{error}</p> : null}
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => setCreating(false)}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" loading={create.isPending}>
                Create user
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
