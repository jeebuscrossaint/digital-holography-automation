import { createContext, ReactNode, useContext, useState } from "react";
import { cn } from "@/lib/utils";

interface Ctx {
  value: string;
  onChange: (v: string) => void;
}
const TabsCtx = createContext<Ctx | null>(null);

export function Tabs({
  value,
  defaultValue,
  onValueChange,
  children,
  className,
}: {
  value?: string;
  defaultValue?: string;
  onValueChange?: (v: string) => void;
  children: ReactNode;
  className?: string;
}) {
  const [internal, setInternal] = useState<string>(defaultValue ?? "");
  const active = value ?? internal;
  const setActive = (v: string) => {
    if (value === undefined) setInternal(v);
    onValueChange?.(v);
  };
  return (
    <TabsCtx.Provider value={{ value: active, onChange: setActive }}>
      <div className={cn("flex flex-col h-full", className)}>{children}</div>
    </TabsCtx.Provider>
  );
}

export function TabsList({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "flex items-center gap-1 border-b border-border px-2",
        className
      )}
    >
      {children}
    </div>
  );
}

export function TabsTrigger({ value, children }: { value: string; children: ReactNode }) {
  const ctx = useContext(TabsCtx)!;
  const active = ctx.value === value;
  return (
    <button
      onClick={() => ctx.onChange(value)}
      className={cn(
        "relative px-4 h-10 text-sm transition-colors",
        active ? "text-ink" : "text-faint hover:text-soft",
        active &&
          "after:content-[''] after:absolute after:bottom-[-1px] after:left-2 after:right-2 after:h-[2px] after:bg-accent after:rounded-full"
      )}
    >
      {children}
    </button>
  );
}

export function TabsContent({ value, children, className }: { value: string; children: ReactNode; className?: string }) {
  const ctx = useContext(TabsCtx)!;
  if (ctx.value !== value) return null;
  return <div className={cn("flex-1 overflow-auto", className)}>{children}</div>;
}
