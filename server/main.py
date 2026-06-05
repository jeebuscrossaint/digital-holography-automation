"""HTTP server for the digital-holography control app.

Exposes the SAME handlers as the stdio sidecar over HTTP, so the React UI runs
in any browser — point it at a headless Windows NUC over Tailscale and control
the rig from your laptop/phone. The experiment runs in a background thread on
the server, so it keeps going after you close the browser or disconnect RDP.

Run:
    uv run uvicorn server.main:app --host 0.0.0.0 --port 8000
Then open  http://<nuc-hostname-or-tailscale-name>:8000  in a browser.
"""
import importlib.util
import threading
import traceback
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

ROOT = Path(__file__).resolve().parent.parent

# Reuse the existing sidecar handlers + STATE. Load by file path so it doesn't
# clash with the repo's other main.py files. Importing it runs the sidecar's
# path setup (hardware/, lib/) and builds STATE — but NOT its stdio loop
# (that's guarded by __main__).
_spec = importlib.util.spec_from_file_location(
    "holo_sidecar", str(ROOT / "sidecar" / "main.py"))
sidecar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sidecar)

app = FastAPI(title="Digital Holography")

# The hardware handlers were written for sequential execution (the stdio sidecar
# processed one request at a time). Serialize them so overlapping HTTP requests
# (the UI polls status/frame/experiment-state concurrently) can't trample shared
# driver state.
_rpc_lock = threading.Lock()


def _dispatch(method: str, params: dict):
    handler = sidecar.HANDLERS.get(method)
    if handler is None:
        raise KeyError(f"unknown method: {method}")
    with _rpc_lock:
        return handler(params or {})


@app.post("/rpc")
async def rpc(req: Request):
    """Mirror the frontend's rpc() contract: {method, params} -> {ok, result}."""
    try:
        body = await req.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid JSON body"},
                            status_code=400)
    method = body.get("method")
    params = body.get("params") or {}
    try:
        # Handlers block on hardware I/O — run off the event loop.
        result = await run_in_threadpool(_dispatch, method, params)
        return {"ok": True, "result": result}
    except KeyError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=404)
    except Exception as e:
        return {"ok": False, "error": str(e), "trace": traceback.format_exc()}


@app.get("/healthz")
def healthz():
    return {"ok": True, "status": sidecar.STATE.hardware_status()}


# Serve the built React UI (app/dist). Mounted LAST so /rpc and /healthz win.
_DIST = ROOT / "app" / "dist"
if _DIST.exists():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="ui")
else:
    @app.get("/")
    def _no_ui():
        return {"ok": False,
                "error": "UI not built. Run `npm run build` in app/ first."}
