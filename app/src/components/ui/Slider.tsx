import { InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface Props extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  // value handled via standard input value/onChange
}

export function Slider({ className, ...rest }: Props) {
  return (
    <input
      type="range"
      className={cn(
        "w-full appearance-none bg-transparent",
        "[&::-webkit-slider-runnable-track]:h-1.5 [&::-webkit-slider-runnable-track]:rounded-full",
        "[&::-webkit-slider-runnable-track]:bg-border",
        "[&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:-mt-1.5",
        "[&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:rounded-full",
        "[&::-webkit-slider-thumb]:bg-accent [&::-webkit-slider-thumb]:cursor-pointer",
        "[&::-webkit-slider-thumb]:shadow-[0_0_0_2px_hsl(var(--bg))]",
        "focus-visible:outline-none",
        className
      )}
      {...rest}
    />
  );
}
