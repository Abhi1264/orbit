"use client";

import { FeedbackTab } from "@/components/ops/feedback-tab";
import { KnowledgeTab } from "@/components/ops/knowledge-tab";
import { SopsTab } from "@/components/ops/sops-tab";
import { PageHeader } from "@/components/ui/panel";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useUrlState } from "@/lib/url-state";

type Tab = "sops" | "knowledge" | "feedback";

export default function OpsPage() {
  const url = useUrlState();
  const tab = (url.get("tab") as Tab | null) ?? "sops";

  return (
    <>
      <PageHeader
        title="Product Ops"
        description="The operating layer around the numbers: how we launch (SOPs and checklists), what we know (knowledge base), and what people are telling us (feedback intake with themes)."
      />
      <Tabs
        value={tab}
        onValueChange={(v) => url.set({ tab: v === "sops" ? null : v, doc: null, sop: null })}
      >
        <TabsList>
          <TabsTrigger value="sops">SOPs &amp; checklists</TabsTrigger>
          <TabsTrigger value="knowledge">Knowledge base</TabsTrigger>
          <TabsTrigger value="feedback">Feedback</TabsTrigger>
        </TabsList>
        <TabsContent value="sops">
          <SopsTab />
        </TabsContent>
        <TabsContent value="knowledge">
          <KnowledgeTab />
        </TabsContent>
        <TabsContent value="feedback">
          <FeedbackTab />
        </TabsContent>
      </Tabs>
    </>
  );
}
