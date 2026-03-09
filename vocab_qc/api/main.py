"""FastAPI 应用入口."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from vocab_qc.core.config import settings
from vocab_qc.api.routers import admin, auth, batch, export, import_, qc, review, stats, words

app = FastAPI(title="词汇质检系统 V2.0", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(stats.router)
app.include_router(words.router)
app.include_router(import_.router)
app.include_router(qc.router)
app.include_router(review.router)
app.include_router(batch.router)
app.include_router(export.router)


@app.get("/health")
def health():
    return {"status": "ok"}
