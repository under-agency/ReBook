from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import api_router

app = FastAPI(title="ReBook CRM", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.include_router(api_router, prefix="/api")

# Прод: раздаём собранный фронт (apps/web/dist), все не-/api пути — SPA-fallback
_dist = Path(__file__).resolve().parent.parent.parent / "web" / "dist"
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        file = _dist / full_path
        if full_path and file.is_file():
            return FileResponse(file)
        return FileResponse(_dist / "index.html")
