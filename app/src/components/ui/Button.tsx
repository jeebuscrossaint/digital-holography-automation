import { ButtonHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/utils";

type Variant = "default" | "primary" | "ghost" | "danger" | "outline";
type Size = "sm" | "md" | "lg" | "icon";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

/* macOS HIG buttons: 6px radius, subtle gradient fills, primary uses
   the system accent. Default button has a soft fill rather than a
   visible border (HIG dropped hard borders years ago). */

const variants: Record<Variant, string> = {
  default:
    "bg-ink/[0.06] text-ink hover:bg-ink/[0.10] active:bg-ink/[0.15] " +
    "shadow-[0_0_0_0.5px_hsl(var(--ink)/0.08),0_1px_0_hsl(var(--ink)/0.04)]",
  primary:
    "bg-accent text-white hover:brightness-[1.06] active:brightness-95 " +
    "shadow-[0_0_0_0.5px_hsl(var(--accent)/0.7),0_1px_2px_hsl(var(--accent)/0.25)]",
  ghost:
    "text-soft hover:text-ink hover:bg-ink/[0.05]",
  danger:
    "bg-bad/10 text-bad hover:bg-bad/15 " +
    "shadow-[0_0_0_0.5px_hsl(var(--bad)/0.4)]",
  outline:
    "bg-transparent text-ink hover:bg-ink/[0.06] " +
    "shadow-[0_0_0_0.5px_hsl(var(--ink)/0.12)]",
};
const sizes: Record<Size, string> = {
  sm:   "h-[22px] px-2.5 text-[11.5px] rounded-[5px]",
  md:   "h-[26px] px-3   text-[12.5px] rounded-[6px]",
  lg:   "h-[32px] px-4   text-[13px]   rounded-[7px]",
  icon: "h-[26px] w-[26px] p-0 rounded-[6px]",
};

export const Button = forwardRef<HTMLButtonElement, Props>(
  ({ className, variant = "default", size = "md", ...rest }, ref) => (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center gap-1.5 font-medium",
        "transition-[background,transform,filter] duration-75",
        "disabled:pointer-events-none disabled:opacity-40",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50",
        variants[variant], sizes[size], className
      )}
      {...rest}
    />
  )
);
Button.displayName = "Button";
