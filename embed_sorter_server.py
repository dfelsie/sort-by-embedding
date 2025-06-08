# embed_sorter_server.py

import os
import json
import torch
import open_clip
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
from PIL import Image

# 1) Add LLM + VLM imports
from transformers import Blip2Processor, Blip2ForConditionalGeneration
from llama_cpp import Llama
from contextlib import asynccontextmanager

# ---------- Request/Response Schemas ----------

class ConceptSortRequest(BaseModel):
    imagePaths: List[str]
    dimension: str
    orderStart: str
    orderEnd: str

class ConceptSortResponse(BaseModel):
    sortedPaths: List[str]

# ---------- Lifespan for startup/shutdown ----------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup code ---
    print("[lifespan] Loading models...")

    # Load VLM
    app.state.vlm_processor = Blip2Processor.from_pretrained("Salesforce/blip2-opt-2.7b")
    app.state.vlm = Blip2ForConditionalGeneration.from_pretrained(
        "Salesforce/blip2-opt-2.7b"
    ).to("cuda")

    # Load LLM
    app.state.llm = Llama(
        #model_path="models/llama3-8k.gguf",
        model_path="C:\\Users\\DLF\\Documents\\newCode\\jobs2\\sort-by-embedding\\models\\llama3-8.k.gguf",
        n_ctx=2048,
        n_threads=4
    )

    # Choose device
    app.state.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("[lifespan] Models loaded and ready.")

    yield

    # --- Shutdown code (if you need to clean up) ---
    print("[lifespan] Shutting down. Clearing models from memory.")
    # You could do cleanup here if desired:
    # del app.state.vlm, app.state.vlm_processor, app.state.llm

# ---------- Create app with lifespan ----------

app = FastAPI(lifespan=lifespan, title="EmbedSorterService")

# ---------- Helper functions using app.state ----------

def generate_tags(image_paths: List[str]) -> List[str]:
    tags = []
    vlm = app.state.vlm
    processor = app.state.vlm_processor
    device = app.state.device

    for p in image_paths:
        img = Image.open(p).convert("RGB")
        inputs = processor(images=img, return_tensors="pt").to(device)
        prompt = "Describe the main subject of this image in one to three words."
        outputs = vlm.generate(**inputs, max_new_tokens=10, do_sample=False)
        tag = processor.decode(outputs[0], skip_special_tokens=True).strip()
        tags.append(tag)
    return tags

def sort_tags_by_dimension(tags: List[str], dimension: str, start: str, end: str) -> List[str]:
    llm = app.state.llm
    items = ", ".join(tags)
    llm_prompt = f"""
You are a sorting expert.
Sort the following items based on the dimension of {dimension}.
List them from {start} to {end}.
Respond ONLY with the sorted, comma-separated list.
Items: {items}
"""
    resp = llm(prompt=llm_prompt, max_tokens=256, stop=["\\n"])
    sorted_tags = [t.strip() for t in resp["choices"][0]["text"].split(",")]
    return sorted_tags

# ---------- Endpoint ----------

@app.post("/concept-sort", response_model=ConceptSortResponse)
async def concept_sort(req: ConceptSortRequest):
    if not req.imagePaths:
        raise HTTPException(400, "No imagePaths provided")

    tags = generate_tags(req.imagePaths)
    sorted_tags = sort_tags_by_dimension(tags, req.dimension, req.orderStart, req.orderEnd)

    tag_to_paths = {}
    for path, tag in zip(req.imagePaths, tags):
        tag_to_paths.setdefault(tag, []).append(path)

    sorted_paths = []
    for tag in sorted_tags:
        sorted_paths.extend(tag_to_paths.get(tag, []))

    return ConceptSortResponse(sortedPaths=sorted_paths)

# ---------- Run with Uvicorn ----------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("embed_sorter_server:app", host="127.0.0.1", port=8000, log_level="info")
