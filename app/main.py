import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import assistant, auth, products

# Without this, Python only prints WARNING and above, so our logger.info lines
# (e.g. the assistant's per-question summary) would be silently dropped.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI()

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
