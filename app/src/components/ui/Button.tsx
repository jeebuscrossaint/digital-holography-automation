import { ButtonHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/utils";

type Variant = "default" | "primary" | "ghost" | "danger" | "outline";
type Size = "sm" | "md" | "lg" | "icon";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

const variants: Record<Variant, string> = {
  default: "bg-elevated text-ink border border-border hover:bg-panel",
  primary: "bg-accent text-white hover:brightness-110 active:brightness-95",
  ghost:   "text-soft hover:text-ink hover:bg-panel",
  danger:  "bg-bad/10 text-bad border border-bad/40 hover:bg-bad/20",
  outline: "bg-transparent text-ink border border-border hover:bg-panel",
};
const sizes: Record<Size, string> = {
  sm:   "h-8  px-3   text-xs",
  md:   "h-9  px-4   text-sm",
  lg:   "h-11 px-6   text-sm",
  icon: "h-9 w-9 p-0",
};

export const Button = forwardRef<HTMLButtonElement, Props>(
  ({ className, variant = "default", size = "md", ...rest }, ref) => (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-md font-medium",
        "transition-colors disabled:pointer-events-none disabled:opacity-50",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60",
        variants[variant], sizes[size], className
      )}
      {...rest}
    />
  )
);
Button.displayName = "Button";
