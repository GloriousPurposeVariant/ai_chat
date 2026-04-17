# -*- coding: utf-8 -*-
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(
    title="Reelo AI Chat Service",
    description="Odoo + AI orchestration layer for GW Products B2B marketplace",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "service": "Reelo AI Chat",
        "status": "running",
    }
