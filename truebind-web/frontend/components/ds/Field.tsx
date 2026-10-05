"use client";

import { CaretDown, WarningCircle } from "@phosphor-icons/react";
import { cloneElement, forwardRef, isValidElement, useId } from "react";
import s from "./Field.module.css";

/** Label, control, help and an inline error in plain English under the field. */
export function Field({
  label,
  help,
  error,
  optional,
  children,
}: {
  label: React.ReactNode;
  help?: React.ReactNode;
  error?: React.ReactNode;
  optional?: boolean;
  children: React.ReactElement<{ id?: string; "aria-describedby"?: string; "aria-invalid"?: boolean }>;
}) {
  const id = useId();
  const helpId = help ? `${id}-help` : undefined;
  const errId = error ? `${id}-err` : undefined;
  const control = isValidElement(children)
    ? cloneElement(children, {
        id: children.props.id ?? id,
        "aria-describedby": [helpId, errId].filter(Boolean).join(" ") || undefined,
        "aria-invalid": error ? true : undefined,
      })
    : children;
  return (
    <div className={s.field}>
      <label className={s.label} htmlFor={children.props.id ?? id}>
        {label}
        {optional && <span className={s.optional}> (optional)</span>}
      </label>
      {control}
      {help && !error && <span id={helpId} className={s.help}>{help}</span>}
      {error && (
        <span id={errId} className={s.error}>
          <WarningCircle size={14} weight="bold" aria-hidden="true" />
          {error}
        </span>
      )}
    </div>
  );
}

type InputProps = React.InputHTMLAttributes<HTMLInputElement> & { mono?: boolean };

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input({ mono, className, ...rest }, ref) {
  return <input ref={ref} className={[s.control, mono && s.mono, className].filter(Boolean).join(" ")} {...rest} />;
});

export const Textarea = forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea(
  { className, ...rest },
  ref,
) {
  return <textarea ref={ref} className={[s.control, className].filter(Boolean).join(" ")} {...rest} />;
});

/** Native select: keyboard, screen readers and phones all work without help. */
export const Select = forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(function Select(
  { className, children, ...rest },
  ref,
) {
  return (
    <span className={s.selectWrap}>
      <select ref={ref} className={[s.control, className].filter(Boolean).join(" ")} {...rest}>
        {children}
      </select>
      <CaretDown size={14} aria-hidden="true" />
    </span>
  );
});

export function Checkbox({ label, ...rest }: { label: React.ReactNode } & Omit<React.InputHTMLAttributes<HTMLInputElement>, "type">) {
  return (
    <label className={s.check}>
      <input type="checkbox" {...rest} />
      {label}
    </label>
  );
}
