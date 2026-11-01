"use client";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { Button, Card, Field, Input, Notice, Select } from "@/components/ui";
import { useRouter } from "@/i18n/navigation";
import { api } from "@/lib/api";
import { setDevToken } from "@/lib/auth";
import { DEV_AUTH } from "@/lib/config";
import { supabaseBrowser } from "@/lib/supabase/client";

export function LoginForm() {
  const t = useTranslations("login");
  const locale = useLocale();
  const router = useRouter();
  const sb = supabaseBrowser();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [otp, setOtp] = useState("");
  const [sent, setSent] = useState(false);
  const [role, setRole] = useState("customer");
  const [msg, setMsg] = useState<{ tone: "bad" | "good"; text: string } | null>(null);
  const done = () => router.push("/cases");

  async function signIn(signUp: boolean) {
    if (!sb) return;
    setMsg(null);
    const r = signUp
      ? await sb.auth.signUp({ email, password, options: { data: { preferred_locale: locale } } })
      : await sb.auth.signInWithPassword({ email, password });
    if (r.error) setMsg({ tone: "bad", text: r.error.message });
    else if (signUp && !r.data.session) setMsg({ tone: "good", text: t("checkEmail") });
    else done();
  }
  async function sendOtp() {
    if (!sb) return;
    const r = await sb.auth.signInWithOtp({ phone, options: { data: { preferred_locale: locale } } });
    if (r.error) setMsg({ tone: "bad", text: r.error.message });
    else setSent(true);
  }
  async function verifyOtp() {
    if (!sb) return;
    const r = await sb.auth.verifyOtp({ phone, token: otp, type: "sms" });
    if (r.error) setMsg({ tone: "bad", text: r.error.message });
    else done();
  }
  async function devLogin() {
    try {
      const r = await api<{ access_token: string }>("/dev/login", { body: { email, role } });
      setDevToken(r.access_token);
      router.push(role === "customer" ? "/cases" : "/ops");
    } catch (e: any) {
      setMsg({ tone: "bad", text: e.message });
    }
  }

  return (
    <div className="mx-auto max-w-md space-y-4">
      <h1 className="text-3xl font-semibold">{t("title")}</h1>
      {sb ? (
        <>
          <Card className="space-y-3">
            <Field label={t("email")}><Input type="email" autoComplete="email" className="latin" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
            <Field label={t("password")}><Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
            <div className="flex gap-2"><Button onClick={() => signIn(false)}>{t("signIn")}</Button><Button variant="secondary" onClick={() => signIn(true)}>{t("signUp")}</Button></div>
          </Card>
          <p className="text-center text-ink-2">{t("or")}</p>
          <Card className="space-y-3">
            <Field label={t("phone")}><Input type="tel" autoComplete="tel" className="latin" dir="ltr" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+923001234567" /></Field>
            {sent && <Field label={t("otp")}><Input inputMode="numeric" className="latin" value={otp} onChange={(e) => setOtp(e.target.value)} /></Field>}
            {sent ? <Button onClick={verifyOtp}>{t("verify")}</Button> : <Button variant="secondary" onClick={sendOtp}>{t("sendCode")}</Button>}
          </Card>
        </>
      ) : DEV_AUTH ? (
        <Card className="space-y-3">
          <Notice>{t("devTitle")}</Notice>
          <Field label={t("email")}><Input type="email" className="latin" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
          <Field label={t("devAs")}><Select value={role} onChange={(e) => setRole(e.target.value)}><option value="customer">customer</option><option value="ops">ops</option><option value="admin">admin</option></Select></Field>
          <Button onClick={devLogin} disabled={!email}>{t("signIn")}</Button>
        </Card>
      ) : (
        <Notice tone="bad">{t("notConfigured")}</Notice>
      )}
      {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}
    </div>
  );
}
