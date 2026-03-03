"""FastAPI 应用入口."""

from fastapi import FastAPI

from vocab_qc.api.routers import export, qc, review

app = FastAPI(title="词汇质检系统 V2.0", version="0.1.0")

app.include_router(qc.router)
app.include_router(review.router)
app.include_router(export.router)


@app.get("/health")
def health():
    return {"status": "ok"}
