import { InputHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/utils";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...rest }, ref) => (
    <input
      ref={ref}
      className={cn(
        "h-9 w-full rounded-md border border-border bg-panel px-3 py-1.5",
        "text-sm font-mono text-ink placeholder:text-faint",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60",
        "disabled:opacity-50 disabled:pointer-events-none",
        className
      )}
      {...rest}
    />
  )
);
Input.displayName = "Input";
