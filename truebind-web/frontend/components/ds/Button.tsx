"use client";

import Link from "next/link";
import { forwardRef } from "react";
import s from "./Button.module.css";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "outline" | "outlineQuiet";
export type ButtonSize = 28 | 32 | 36 | 40 | 48;

interface Common {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Square button holding only an icon; needs an aria-label. */
  iconOnly?: boolean;
  className?: string;
  children?: React.ReactNode;
}

function cls({ variant = "secondary", size = 32, iconOnly, className }: Common, loading = false) {
  return [s.button, s[variant], s[`s${size}`], iconOnly && s.iconOnly, loading && s.loading, className]
    .filter(Boolean)
    .join(" ");
}

/** Class names for an element that must look like a button but isn't one of ours (e.g. a third-party trigger). */
export function buttonClass(opts: { variant?: ButtonVariant; size?: ButtonSize; className?: string } = {}) {
  return cls(opts);
}

type ButtonProps = Common & React.ButtonHTMLAttributes<HTMLButtonElement> & { loading?: boolean };

/** One primary per view. Loading keeps the button's width and blocks repeat clicks. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant, size, iconOnly, className, loading = false, children, disabled, type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cls({ variant, size, iconOnly, className }, loading)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      <span className={s.label}>{children}</span>
      {loading && <span className={s.spinner} aria-hidden="true" />}
    </button>
  );
});

type LinkProps = Common & Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & { href: string };

/** A link that looks like a button. External and hash links use a plain anchor. */
export function ButtonLink({ variant, size, iconOnly, className, href, children, ...rest }: LinkProps) {
  const c = cls({ variant, size, iconOnly, className });
  if (/^(https?:|mailto:|#)/.test(href)) {
    return <a href={href} className={c} {...rest}>{children}</a>;
  }
  return <Link href={href} className={c} {...rest}>{children}</Link>;
}
