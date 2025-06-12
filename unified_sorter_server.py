# unified_sorter_server.py

import os
import torch
import open_clip
import google.generativeai as genai
import PIL.Image
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
from dotenv import load_dotenv

# ==============================================================================
# 1. SETUP & CONFIGURATION
# ==============================================================================

# Load environment variables from .env file
load_dotenv()

def load_clip_model():
    """
    Loads the specified CLIP variant and its preprocess transforms.
    Returns (model, preprocess).
    """
    model_name, pretrained = "ViT-B-32", "openai"
    model, _, preprocess = open_clip.create_model_and_transforms(
        model_name, pretrained=pretrained
    )
    return model, preprocess

# --- Pydantic Models for API Requests/Responses ---

class GeminiSortRequest(BaseModel):
    imagePaths: List[str]
    prompt: str

class ClipSortRequest(BaseModel):
    imagePaths: List[str]
    prompt: str

class SortResponse(BaseModel):
    sortedPaths: List[str]

# --- Global Placeholders for AI Models ---

GEMINI_MODEL = None
CLIP_MODEL = None
PREPROCESSOR = None
DEVICE = torch.device("cpu")

# --- Main FastAPI Application ---
app = FastAPI(title="Unified Image Sorting Service")


# ==============================================================================
# 2. STARTUP EVENT: LOAD ALL MODELS
# ==============================================================================

@app.on_event("startup")
async def startup_event():
    global GEMINI_MODEL, CLIP_MODEL, PREPROCESSOR, DEVICE

    # 1) Pick device
    DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[server] Using device: {DEVICE}")

    # --- Configure Gemini ---
    print("[server] Configuring Gemini...")
    try:
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        GEMINI_MODEL = genai.GenerativeModel('gemini-2.0-flash')
        print("[server] Gemini 'gemini-2.0-flash' configured.")
    except KeyError:
        print("[server] WARNING: GEMINI_API_KEY not set; /quick-sort disabled.")
    except Exception as e:
        print(f"[server] WARNING: Gemini init error: {e}")

    # --- Load OpenCLIP ---
    print("[server] Loading OpenCLIP model...")
    try:
        model, preprocess = load_clip_model()
        # Move model to device
        CLIP_MODEL = model.to(DEVICE).eval()
        PREPROCESSOR = preprocess
        print(f"[server] OpenCLIP loaded on {DEVICE}.")
    except Exception as e:
        CLIP_MODEL = None
        print(f"[server] WARNING: CLIP init error: {e}")


# ==============================================================================
# 3. GEMINI-BASED SORTING ENDPOINT
# ==============================================================================

@app.post("/quick-sort", response_model=SortResponse)
async def sort_by_gemini(req: GeminiSortRequest):
    if GEMINI_MODEL is None:
        raise HTTPException(503, "Gemini not available.")
    if not req.imagePaths:
        raise HTTPException(400, "No imagePaths provided.")
    if not req.prompt:
        raise HTTPException(400, "Empty prompt.")

    num_images = len(req.imagePaths)
    # Define the function schema
    sort_tool = {
        "function_declarations": [
            {
                "name": "return_sorted_indices",
                "description": "Returns new image order as list of indices",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sorted": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "New ordering indices"
                        }
                    },
                    "required": ["sorted"]
                }
            }
        ]
    }

    system_instruction = (
        f"You are an image sorting assistant. Sort {num_images} images "
        f"per the user's instruction and call return_sorted_indices(sorted=[...])."
    )
    user_prompt = f"Please sort these {num_images} images by: '{req.prompt}'."

    prompt_parts = [system_instruction, user_prompt]
    for path in req.imagePaths:
        try:
            prompt_parts.append(PIL.Image.open(path))
        except Exception as e:
            raise HTTPException(400, f"Cannot open {path}: {e}")

    try:
        resp = GEMINI_MODEL.generate_content(
            prompt_parts,
            tools=sort_tool,
            tool_config={"function_calling_config": "ANY"}
        )
        func_call = resp.candidates[0].content.parts[0].function_call
        idxs = func_call.args.get("sorted", [])
        if len(idxs) != num_images or len(set(idxs)) != num_images:
            raise ValueError("Invalid index list from Gemini.")
        sorted_paths = [req.imagePaths[i] for i in idxs]
    except Exception as e:
        raise HTTPException(500, f"Gemini error: {e}")

    return SortResponse(sortedPaths=sorted_paths)


# ==============================================================================
# 4. CLIP-BASED SORTING ENDPOINT
# ==============================================================================

# Embedding helpers
def get_text_embedding(text: str):
    tokenizer = open_clip.get_tokenizer("ViT-B-32")
    tokens = tokenizer([text]).to(DEVICE)
    with torch.no_grad():
        emb = CLIP_MODEL.encode_text(tokens)
    emb = emb / emb.norm(dim=-1, keepdim=True)
    return emb

def get_image_embeddings(paths: List[str], batch_size: int = 16):
    all_embs = []
    all_paths = []
    for i in range(0, len(paths), batch_size):
        batch = paths[i : i + batch_size]
        imgs = []
        for p in batch:
            img = PIL.Image.open(p).convert("RGB")
            imgs.append(PREPROCESSOR(img).unsqueeze(0))
            all_paths.append(p)
        tensor = torch.cat(imgs, dim=0).to(DEVICE)
        with torch.no_grad():
            emb = CLIP_MODEL.encode_image(tensor)
        emb = emb / emb.norm(dim=-1, keepdim=True)
        all_embs.append(emb)
    if not all_embs:
        # Return an empty tensor on DEVICE
        return [], torch.empty((0, CLIP_MODEL.visual.output_dim), device=DEVICE)
    return all_paths, torch.cat(all_embs, dim=0)  # DEVICE tensor

@app.post("/sort-by-clip", response_model=SortResponse)
async def sort_by_clip(req: ClipSortRequest):
    if CLIP_MODEL is None:
        raise HTTPException(503, "CLIP not available.")
    if not req.imagePaths:
        raise HTTPException(400, "No imagePaths provided.")
    if not req.prompt:
        raise HTTPException(400, "Empty prompt.")

    parts = req.prompt.lower().split(" to ")
    if len(parts) == 2:
        emb_a = get_text_embedding(parts[0]).to(DEVICE)
        emb_b = get_text_embedding(parts[1]).to(DEVICE)
    else:
        emb_a = get_text_embedding(req.prompt).to(DEVICE)
        emb_b = None

    abs_paths, img_embs = get_image_embeddings(req.imagePaths)
    if img_embs.nelement() == 0:
        return SortResponse(sortedPaths=[])

    with torch.no_grad():
        if emb_b is None:
            scores = (img_embs @ emb_a.t()).squeeze(1)
        else:
            scores = (img_embs @ emb_a.t()).squeeze(1) - (img_embs @ emb_b.t()).squeeze(1)

    pairs = sorted(zip(abs_paths, scores.tolist()), key=lambda x: x[1], reverse=True)
    sorted_paths = [p for p,_ in pairs]
    return SortResponse(sortedPaths=sorted_paths)


# ==============================================================================
# 5. RUN THE SERVER
# ==============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("unified_sorter_server:app", host="127.0.0.1", port=8000, reload=True)
