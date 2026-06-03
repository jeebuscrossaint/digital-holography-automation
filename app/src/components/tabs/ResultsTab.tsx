import { useEffect, useState } from "react";
import { Card, CardHeader, CardTitle, CardBody } from "../ui/Card";
import { Button } from "../ui/Button";
import { FolderOpen, RefreshCw } from "lucide-react";
import { rpc } from "@/lib/api";

interface Row {
  filename: string;
  fidelity: number;
  mode_powers: number[];
}

export function ResultsTab() {
  const [rows, setRows] = useState<Row[]>([]);

  const refresh = async () => {
    try {
      const r = await rpc<{ results: Row[] }>("results_get");
      setRows(r?.results ?? []);
    } catch { /* ignore */ }
  };

  useEffect(() => { refresh(); }, []);

  const open = async () => {
    try { await rpc<void>("results_open_folder"); } catch { /* ignore */ }
  };

  return (
    <div className="px-6 py-5 space-y-4">
      <div className="flex items-center gap-2">
        <Button variant="outline" onClick={open}>
          <FolderOpen className="h-4 w-4" /> Open data folder
        </Button>
        <Button variant="outline" onClick={refresh}>
          <RefreshCw className="h-4 w-4" /> Refresh
        </Button>
      </div>

      <Card>
        <CardHeader><CardTitle>Processed holograms</CardTitle></CardHeader>
        <CardBody>
          {rows.length === 0 ? (
            <div className="py-12 text-center text-faint text-sm">
              No processed results yet. Run an experiment first.
            </div>
          ) : (
            <div className="overflow-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-faint font-mono text-[10px] uppercase tracking-wider">
                    <th className="py-2 pr-4">Hologram</th>
                    <th className="py-2 pr-4 text-right">Fidelity</th>
                    <th className="py-2 pr-4">Mode powers (LP01 → LP06)</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i} className="border-t border-border/60">
                      <td className="py-2 pr-4">{r.filename}</td>
                      <td className="py-2 pr-4 text-right tabular-nums">{r.fidelity.toFixed(4)}</td>
                      <td className="py-2 pr-4 font-mono text-xs tabular-nums">
                        {r.mode_powers.slice(0, 6).map((p) => `${(p * 100).toFixed(1)}%`).join("  ")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
