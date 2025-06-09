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

# --- Pydantic Models for API Requests/Responses ---

class GeminiSortRequest(BaseModel):
    imagePaths: list[str]
    prompt: str  # e.g., "Sort from hottest to coldest"

class ClipSortRequest(BaseModel):
    imagePaths: List[str]
    prompt: str  # e.g., "A picture of a sunny day"

class SortResponse(BaseModel):
    sortedPaths: List[str] # Both endpoints will use this response model

# --- Global Placeholders for AI Models ---

GEMINI_MODEL = None
CLIP_MODEL = None
PREPROCESSOR = None
DEVICE = None

# --- Main FastAPI Application ---
app = FastAPI(title="Unified Image Sorting Service")


# ==============================================================================
# 2. STARTUP EVENT: LOAD ALL MODELS
# ==============================================================================

@app.on_event("startup")
async def startup_event():
    """Loads both Gemini and CLIP models when the server starts."""
    global GEMINI_MODEL, CLIP_MODEL, PREPROCESSOR, DEVICE

    # --- Configure Gemini ---
    print("[server] Configuring Gemini...")
    try:
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        GEMINI_MODEL = genai.GenerativeModel('gemini-1.5-flash-latest')
        print("[server] Gemini model 'gemini-1.5-flash-latest' configured.")
    except KeyError:
        print("[server] WARNING: GEMINI_API_KEY not found. The /sort-by-gemini endpoint will fail.")
    except Exception as e:
        print(f"[server] WARNING: An error occurred during Gemini configuration: {e}")


    # --- Load OpenCLIP ---
    print("[server] Loading OpenCLIP model...")
    try:
        DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
        model_name, pretrained = "ViT-B-32", "openai"
        CLIP_MODEL, _, PREPROCESSOR = open_clip.create_model_and_transforms(
            model_name, pretrained=pretrained
        )
        CLIP_MODEL.to(DEVICE)
        CLIP_MODEL.eval()
        print(f"[server] OpenCLIP model '{model_name}' loaded on {DEVICE}.")
    except Exception as e:
        print(f"[server] WARNING: An error occurred while loading the CLIP model: {e}")


# ==============================================================================
# 3. GEMINI-BASED SORTING ENDPOINT
# ==============================================================================

@app.post("/quick-sort", response_model=SortResponse)
async def sort_by_gemini(req: GeminiSortRequest):
    if GEMINI_MODEL is None:
        raise HTTPException(503, "Gemini service is not available. Check server configuration.")
    if not req.imagePaths:
        raise HTTPException(400, "No imagePaths provided")
    if not req.prompt:
        raise HTTPException(400, "An empty prompt was provided")

    num_images = len(req.imagePaths)
    sort_tool = { "function_declarations": [{"name": "return_sorted_indices","description": "Returns the new order of images as a list of indices","parameters": {"type": "object","properties": {"sorted": {"type": "array","description": "The list of original indices in their new sorted order.","items": {"type": "integer"}}},"required": ["sorted"]}}]}

    system_instruction = (
        f"You are an expert image analysis assistant. Your task is to sort the user-provided "
        f"images according to their instructions. You must return the result by calling the "
        f"`return_sorted_indices` function.\n\n"
        f"**CRITICAL INSTRUCTION:** The 'sorted' array you return **MUST** contain the exact same number of items "
        f"as the number of images provided. You have been given {num_images} images, so you **MUST** return "
        f"exactly {num_images} unique integers in the 'sorted' array. Each index from 0 to {num_images - 1} "
        f"must appear exactly once."
    )
    user_prompt = f"Please sort these {num_images} images based on the following criteria: '{req.prompt}'"
    prompt_parts = [system_instruction, user_prompt]

    for path in req.imagePaths:
        try:
            prompt_parts.append(PIL.Image.open(path))
        except Exception as e:
            raise HTTPException(400, f"Could not process image at {path}: {e}")

    try:
        resp = GEMINI_MODEL.generate_content(
            prompt_parts, tools=sort_tool, tool_config={"function_calling_config": "ANY"}
        )
        function_call = resp.candidates[0].content.parts[0].function_call
        idxs = function_call.args.get("sorted", [])

        # Validation
        if len(idxs) != num_images or len(set(idxs)) != num_images:
            raise ValueError(f"Model returned an invalid index list. Expected {num_images} unique items.")

        sorted_paths = [req.imagePaths[int(i)] for i in idxs]

    except Exception as e:
        raise HTTPException(500, f"An error occurred with the Gemini API or processing: {e}")

    return SortResponse(sortedPaths=sorted_paths)


# ==============================================================================
# 4. CLIP-BASED SORTING ENDPOINT
# ==============================================================================

# --- CLIP Helper Functions ---
def get_clip_text_embedding(text, device):
    tokenizer = open_clip.get_tokenizer("ViT-B-32")
    with torch.no_grad():
        text_emb = CLIP_MODEL.encode_text(tokenizer([text]).to(device))
    text_emb /= text_emb.norm(dim=-1, keepdim=True)
    return text_emb.cpu() #<-- FIX: Ensure it's moved to the CPU

def get_clip_image_embeddings(img_paths, device, batch_size=16):
    embs = []
    for i in range(0, len(img_paths), batch_size):
        batch_paths = img_paths[i: i + batch_size]
        try:
            tensors = [PREPROCESSOR(PIL.Image.open(p).convert("RGB")).unsqueeze(0) for p in batch_paths]
            batch_tensor = torch.cat(tensors).to(device)
            with torch.no_grad():
                img_emb = CLIP_MODEL.encode_image(batch_tensor)
            img_emb /= img_emb.norm(dim=-1, keepdim=True)
            embs.append(img_emb.cpu())
        except Exception as e:
            print(f"Warning: Failed to process a batch starting with {batch_paths[0]}. Error: {e}")
    return torch.cat(embs) if embs else torch.Tensor([])

# --- CLIP Endpoint ---
@app.post("/sort-by-clip", response_model=SortResponse)
async def sort_by_clip(req: ClipSortRequest):
    if CLIP_MODEL is None:
        raise HTTPException(503, "CLIP service is not available. Check server configuration.")
    if not req.imagePaths:
        raise HTTPException(400, "No imagePaths provided.")
    if not req.prompt:
        raise HTTPException(400, "An empty prompt was provided.")

    try:
        # 1. Embed the prompt text
        text_emb = get_clip_text_embedding(req.prompt, DEVICE)

        # 2. Embed all images
        img_embs = get_clip_image_embeddings(req.imagePaths, DEVICE)
        if img_embs.nelement() == 0:
            return SortResponse(sortedPaths=[])

        # 3. Compute cosine similarity scores and sort
        scores = (img_embs @ text_emb.T).squeeze()
        pairs = sorted(zip(req.imagePaths, scores.tolist()), key=lambda x: x[1], reverse=True)
        sorted_paths = [p for p, _ in pairs]

    except Exception as e:
        raise HTTPException(500, f"An error occurred during CLIP processing: {e}")

    return SortResponse(sortedPaths=sorted_paths)


# ==============================================================================
# 5. RUN THE SERVER
# ==============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("unified_sorter_server:app", host="127.0.0.1", port=8000, reload=True)