import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.transport_security import TransportSecuritySettings

from app.mcp_server import mcp
from app.routers import assistant, auth, products

# Without this, Python only prints WARNING and above, so our logger.info lines
# (e.g. the assistant's per-question summary) would be silently dropped.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# Built at module level: mcp.session_manager only exists after this call.
# DNS-rebinding protection (localhost-only by default) is off because Cloud Run's
# proxy already controls the Host header — the MCP SDK docs call this case out.
mcp_app = mcp.streamable_http_app(
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # A mounted app's own lifespan never runs, so the host app must start the
    # MCP session manager — otherwise every /mcp request fails.
    async with mcp.session_manager.run():
        yield


app = FastAPI(lifespan=lifespan)

app.include_router(auth.router)
app.include_router(products.router)
app.include_router(assistant.router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "https://marketplace-frontend-770988956423.us-central1.run.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Marketplace API is alive"}


# MUST stay last: this mount matches every path, so routes declared after it
# would never be reached. The MCP endpoint ends up at /mcp.
app.mount("/", mcp_app)
