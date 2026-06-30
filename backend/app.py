import os
import uvicorn

# Hugging Face Spaces entry point — mirrors main.py
from main import app  # noqa: F401 — import the FastAPI app

if __name__ == "__main__":
    port = int(os.getenv("PORT", 7860))  # HF Spaces default port
    uvicorn.run("app:app", host="0.0.0.0", port=port)
