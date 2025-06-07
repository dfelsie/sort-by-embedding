# embed_sorter_server.py

import os
import json
import torch
import open_clip
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
from PIL import Image

# ---------- 1) Define request/response schemas ----------

class SortRequest(BaseModel):
    folderPath: str
    imagePaths: List[str]
    prompt: str

class SortResponse(BaseModel):
    sortedPaths: List[str]

# ---------- 2) FastAPI app ----------

app = FastAPI(title="EmbedSorterService")

# ---------- 3) Your load_clip_model() exactly as you have it ----------

def load_clip_model():
    # You can switch to a different CLIP variant if you want.
    # Here we pick ViT-B-32 with the OpenAI weights.
    model_name, pretrained = "ViT-B-32", "openai"
    model, _, preprocess = open_clip.create_model_and_transforms(
        model_name, pretrained=pretrained
    )
    model.eval()
    return model, preprocess

# Global placeholders for model + preprocess + device
CLIP_MODEL = None
PREPROCESSOR = None
DEVICE = None

# ---------- 4) Startup: load the model once ----------

@app.on_event("startup")
async def startup_event():
    global CLIP_MODEL, PREPROCESSOR, DEVICE
    DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    CLIP_MODEL,  PREPROCESSOR = load_clip_model()
    CLIP_MODEL.to(DEVICE)
    print(f"[server] Loaded CLIP model on {DEVICE}")

# ---------- 5) Embedding helpers ----------

def get_text_embedding(model, text, device):
    tokenizer = open_clip.get_tokenizer("ViT-B-32")
    text_tokens = tokenizer(text).to(device)
    with torch.no_grad():
        text_emb = model.encode_text(text_tokens)
    text_emb = text_emb / text_emb.norm(dim=-1, keepdim=True)
    return text_emb.cpu()

def get_image_embeddings(model, preprocess, img_paths, device, batch_size=16):
    embs = []
    paths_out = []
    for i in range(0, len(img_paths), batch_size):
        batch = img_paths[i : i + batch_size]
        tensors = []
        for p in batch:
            img = Image.open(p).convert("RGB")
            tensors.append(preprocess(img).unsqueeze(0))
        batch_tensor = torch.cat(tensors, dim=0).to(device)
        with torch.no_grad():
            img_emb = model.encode_image(batch_tensor)
        img_emb = img_emb / img_emb.norm(dim=-1, keepdim=True)
        embs.append(img_emb.cpu())
        paths_out.extend(batch)
    all_embs = torch.cat(embs, dim=0)
    return paths_out, all_embs

def compute_scores(img_embs, text_emb, text_emb_b=None):
    if text_emb_b is None:
        scores = (img_embs @ text_emb.t()).squeeze(1)
    else:
        scores = (img_embs @ text_emb.t()).squeeze(1) - (img_embs @ text_emb_b.t()).squeeze(1)
    return scores

# ---------- 6) The /sort endpoint ----------

@app.post("/sort", response_model=SortResponse)
async def sort_by_prompt(req: SortRequest):
    if not req.imagePaths:
        raise HTTPException(status_code=400, detail="No imagePaths provided.")

    # 1) Embed the prompt
    parts = req.prompt.lower().split(" to ")
    if len(parts) == 2:
        a, b = parts
        text_emb_a = get_text_embedding(CLIP_MODEL, a, DEVICE).to(DEVICE)
        text_emb_b = get_text_embedding(CLIP_MODEL, b, DEVICE).to(DEVICE)
    else:
        text_emb_a = get_text_embedding(CLIP_MODEL, req.prompt, DEVICE).to(DEVICE)
        text_emb_b = None

    # 2) Embed the images
    abs_paths, img_embs = get_image_embeddings(
        CLIP_MODEL, PREPROCESSOR, req.imagePaths, DEVICE
    )

    # 3) Compute scores and sort
    scores = compute_scores(img_embs, text_emb_a, text_emb_b)
    pairs = list(zip(abs_paths, scores.tolist()))
    pairs.sort(key=lambda x: x[1], reverse=True)
    sorted_paths = [p for p, _ in pairs]

    return SortResponse(sortedPaths=sorted_paths)

# ---------- 7) Run with uvicorn if invoked directly ----------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("embed_sorter_server:app", host="127.0.0.1", port=8000, log_level="info")
