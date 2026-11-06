"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useApp } from "@/components/Providers";
import { refreshSession } from "@/lib/api";

/** Back from GitHub / Google with a session cookie: get this tab's access token, then go home. */
export default function SignInDone() {
  const { signIn } = useApp();
  const router = useRouter();
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    void (async () => {
      const token = await refreshSession();
      if (!token) return setFailed(true);
      try {
        await signIn(token);
        router.replace("/");
      } catch {
        setFailed(true);
      }
    })();
  }, [signIn, router]);
  return (
    <div className="auth-page">
      <div className="auth-card">
        {failed ? <p>Sign-in did not complete. <Link href="/signin">Try again</Link></p> : <p className="hint">Signing you in…</p>}
      </div>
    </div>
  );
}
