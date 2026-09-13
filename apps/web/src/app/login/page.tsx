"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { api, ApiError, unwrap } from "@/lib/api/client";

const DEMO_ACCOUNTS = [
  { email: "priya.pm@threadline.test", role: "PM" },
  { email: "arjun.analyst@threadline.test", role: "Analyst" },
  { email: "admin@threadline.test", role: "Admin" },
  { email: "viewer@threadline.test", role: "Viewer" },
];

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState(DEMO_ACCOUNTS[0].email);
  const [password, setPassword] = useState("probelens");

  const login = useMutation({
    mutationFn: async () => unwrap(await api.POST("/api/auth/login", { body: { email, password } })),
    onSuccess: () => {
      const next = params.get("next");
      router.replace(next && next.startsWith("/") ? (next as "/") : "/");
    },
  });

  return (
    <form
      className="w-full max-w-sm"
      onSubmit={(e) => {
        e.preventDefault();
        login.mutate();
      }}
    >
      <div className="mb-6">
        <div className="mb-1 text-[15px] font-semibold tracking-tight">Probelens</div>
        <p className="text-fg-muted text-[13px]">Product analytics and experimentation for Threadline.</p>
      </div>
      <div className="space-y-3">
        <Field label="Email" htmlFor="email">
          <Input
            id="email"
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </Field>
        <Field label="Password" htmlFor="password">
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </Field>
        {login.isError ? (
          <p role="alert" className="text-danger text-xs">
            {login.error instanceof ApiError ? login.error.detail : "Login failed"}
          </p>
        ) : null}
        <Button type="submit" variant="primary" className="w-full" loading={login.isPending}>
          Sign in
        </Button>
      </div>
      <div className="border-border mt-6 border-t pt-4">
        <p className="text-fg-subtle mb-2 text-xs">Demo accounts (password: probelens)</p>
        <ul className="space-y-1">
          {DEMO_ACCOUNTS.map((a) => (
            <li key={a.email}>
              <button
                type="button"
                className="hover:bg-surface-2 flex w-full items-center justify-between rounded-sm px-2 py-1 text-left text-xs"
                onClick={() => {
                  setEmail(a.email);
                  setPassword("probelens");
                }}
              >
                <span className="font-mono">{a.email}</span>
                <span className="text-fg-subtle">{a.role}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </form>
  );
}

export default function LoginPage() {
  return (
    <main className="bg-surface flex min-h-screen items-center justify-center px-4">
      <div className="border-border bg-bg rounded-md border p-8">
        <Suspense>
          <LoginForm />
        </Suspense>
      </div>
    </main>
  );
}
