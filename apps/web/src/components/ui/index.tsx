import { forwardRef, type ButtonHTMLAttributes, type HTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/format";

type Variant = "primary" | "secondary" | "ghost" | "danger";
const variants: Record<Variant, string> = {
  primary: "bg-brand text-brand-ink hover:opacity-90",
  secondary: "bg-surface text-ink border border-line hover:bg-surface-2",
  ghost: "text-ink hover:bg-surface-2",
  danger: "bg-bad text-white hover:opacity-90",
};

export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "md" | "lg" | "sm" }>(
  function Button({ className, variant = "primary", size = "md", ...props }, ref) {
    const sizes = { sm: "min-h-9 px-3 text-sm", md: "min-h-11 px-4", lg: "min-h-13 px-6 text-lg" };
    return (
      <button ref={ref} className={cn("inline-flex items-center justify-center gap-2 rounded-xl font-medium transition disabled:opacity-50 disabled:cursor-not-allowed", variants[variant], sizes[size], className)} {...props} />
    );
  },
);

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-2xl border border-line bg-surface p-4 sm:p-5", className)} {...props} />;
}

export function Badge({ tone = "neutral", className, children }: { tone?: "neutral" | "good" | "warn" | "bad" | "brand"; className?: string; children: ReactNode }) {
  const tones = { neutral: "bg-surface-2 text-ink-2", good: "bg-good-soft text-good", warn: "bg-warn-soft text-warn", bad: "bg-bad-soft text-bad", brand: "bg-brand-soft text-brand" };
  return <span className={cn("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-sm font-medium", tones[tone], className)}>{children}</span>;
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...props }, ref) {
  return <input ref={ref} className={cn("min-h-11 w-full rounded-xl border border-line bg-surface px-3 text-ink placeholder:text-ink-2", className)} {...props} />;
});

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...props }, ref) {
  return <textarea ref={ref} className={cn("w-full rounded-xl border border-line bg-surface p-3 text-ink placeholder:text-ink-2", className)} {...props} />;
});

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn("min-h-11 w-full rounded-xl border border-line bg-surface px-3 text-ink", className)} {...props} />;
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block space-y-1">
      <span className="text-sm font-medium text-ink-2">{label}</span>
      {children}
      {hint ? <span className="block text-sm text-ink-2">{hint}</span> : null}
    </label>
  );
}

export function Notice({ tone = "warn", children }: { tone?: "warn" | "bad" | "good" | "brand"; children: ReactNode }) {
  const tones = { warn: "bg-warn-soft text-warn", bad: "bg-bad-soft text-bad", good: "bg-good-soft text-good", brand: "bg-brand-soft text-brand" };
  return <div role="note" className={cn("rounded-xl px-3 py-2 text-[0.95em]", tones[tone])}>{children}</div>;
}
