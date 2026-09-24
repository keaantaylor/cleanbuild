"use client";

import Link from "next/link";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import styles from "./Button.module.css";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

function cls(variant: Variant, size: Size, className?: string) {
  return [styles.button, styles[variant], size === "sm" ? styles.sm : "", className].filter(Boolean).join(" ");
}

export function Button({ variant = "primary", size = "md", loading, className, children, disabled, ...props }: ButtonProps) {
  return (
    <button className={cls(variant, size, className)} disabled={disabled || loading} aria-busy={loading || undefined} {...props}>
      {loading && <span className={styles.spinner} aria-hidden="true" />}
      {children}
    </button>
  );
}

export function ButtonLink({ href, variant = "secondary", size = "md", className, children }: {
  href: string; variant?: Variant; size?: Size; className?: string; children: ReactNode;
}) {
  return <Link href={href} className={cls(variant, size, className)}>{children}</Link>;
}
