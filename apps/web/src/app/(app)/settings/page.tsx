"use client";

import { ProfilePanel } from "@/components/settings/profile-panel";
import { SystemPanel } from "@/components/settings/system-panel";
import { UsersPanel } from "@/components/settings/users-panel";
import { PageHeader } from "@/components/ui/panel";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useMe, usePermission } from "@/lib/api/hooks";
import { useUrlState } from "@/lib/url-state";

type Tab = "profile" | "users" | "system";

export default function SettingsPage() {
  const url = useUrlState();
  const me = useMe();
  const isAdmin = usePermission("manage_users");
  const requested = url.get("tab") as Tab | null;
  const tab: Tab = requested && (requested !== "users" || isAdmin) ? requested : "profile";

  return (
    <>
      <PageHeader
        title="Settings"
        description={
          me.data
            ? `Signed in as ${me.data.name} · ${me.data.role}. Roles are additive: viewer < analyst < pm < admin.`
            : "Account, access and system health."
        }
      />
      <Tabs value={tab} onValueChange={(v) => url.set({ tab: v === "profile" ? null : v })}>
        <TabsList>
          <TabsTrigger value="profile">Profile</TabsTrigger>
          {isAdmin ? <TabsTrigger value="users">Users &amp; roles</TabsTrigger> : null}
          <TabsTrigger value="system">System</TabsTrigger>
        </TabsList>
        <TabsContent value="profile">
          <ProfilePanel />
        </TabsContent>
        {isAdmin ? (
          <TabsContent value="users">
            <UsersPanel />
          </TabsContent>
        ) : null}
        <TabsContent value="system">
          <SystemPanel />
        </TabsContent>
      </Tabs>
    </>
  );
}
