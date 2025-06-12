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
    model_name, pretrained = "ViT-B-32", "openai"
    model, _, preprocess = open_clip.create_model_and_transforms(
        model_name, pretrained=pretrained
    )
    model.eval()
    return model, preprocess

# --- Pydantic Models for API Requests/Responses ---

class GeminiSortRequest(BaseModel):
    imagePaths: List[str]
    prompt: str  # e.g., "Sort from hottest to coldest"

class ClipSortRequest(BaseModel):
    imagePaths: List[str]
    prompt: str  # e.g., "A picture of a sunny day"

class SortResponse(BaseModel):
    sortedPaths: List[str]  # Used by both endpoints

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
        GEMINI_MODEL = genai.GenerativeModel('gemini-2.0-flash')
        print("[server] Gemini model 'gemini-2.0-flash' configured.")
    except KeyError:
        print("[server] WARNING: GEMINI_API_KEY not found; /quick-sort will fail.")
    except Exception as e:
        print(f"[server] WARNING: Error configuring Gemini: {e}")

    # --- Load OpenCLIP ---
    print("[server] Loading OpenCLIP model...")
    DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    try:
        CLIP_MODEL, PREPROCESSOR = load_clip_model()
        CLIP_MODEL.to(DEVICE)
        print(f"[server] OpenCLIP model loaded on {DEVICE}.")
    except Exception as e:
        print(f"[server] WARNING: Error loading CLIP model: {e}")


# ==============================================================================
# 3. GEMINI-BASED SORTING ENDPOINT
# ==============================================================================

@app.post("/quick-sort", response_model=SortResponse)
async def sort_by_gemini(req: GeminiSortRequest):
    if GEMINI_MODEL is None:
        raise HTTPException(503, "Gemini service not available.")
    if not req.imagePaths:
        raise HTTPException(400, "No imagePaths provided.")
    if not req.prompt:
        raise HTTPException(400, "An empty prompt was provided.")

    num_images = len(req.imagePaths)
    sort_tool = {
        "function_declarations": [
            {
                "name": "return_sorted_indices",
                "description": "Returns the new order of images as a list of indices",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sorted": {
                            "type": "array",
                            "description": "List of original indices in new order",
                            "items": {"type": "integer"}
                        }
                    },
                    "required": ["sorted"]
                }
            }
        ]
    }

    # System + user instructions
    system_instruction = (
        f"You are an expert image analysis assistant. Sort the {num_images} provided images "
        f"according to the user's prompt. Return by calling `return_sorted_indices(sorted=[...])`."
    )
    user_prompt = f"Sort these {num_images} images by: '{req.prompt}'"

    prompt_parts = [system_instruction, user_prompt]
    # Attach images directly to prompt
    for path in req.imagePaths:
        try:
            prompt_parts.append(PIL.Image.open(path))
        except Exception as e:
            raise HTTPException(400, f"Could not open image at {path}: {e}")

    try:
        resp = GEMINI_MODEL.generate_content(
            prompt_parts,
            tools=sort_tool,
            tool_config={"function_calling_config": "ANY"}
        )
        func_call = resp.candidates[0].content.parts[0].function_call
        idxs = func_call.args.get("sorted", [])

        # Validate
        if len(idxs) != num_images or len(set(idxs)) != num_images:
            raise ValueError("Gemini returned invalid indices.")

        sorted_paths = [req.imagePaths[i] for i in idxs]

    except Exception as e:
        raise HTTPException(500, f"Gemini API error: {e}")

    return SortResponse(sortedPaths=sorted_paths)


# ==============================================================================
# 4. CLIP-BASED SORTING ENDPOINT
# ==============================================================================

# Embedding helpers
def get_text_embedding(model, text, device):
    tokenizer = open_clip.get_tokenizer("ViT-B-32")
    tokens = tokenizer(text).to(device)
    with torch.no_grad():
        emb = model.encode_text(tokens)
    emb = emb / emb.norm(dim=-1, keepdim=True)
    return emb.cpu()

def get_image_embeddings(model, preprocess, paths, device, batch_size=16):
    embs, out_paths = [], []
    for i in range(0, len(paths), batch_size):
        batch = paths[i : i + batch_size]
        imgs = []
        for p in batch:
            img = PIL.Image.open(p).convert("RGB")
            imgs.append(preprocess(img).unsqueeze(0))
            out_paths.append(p)
        tensor = torch.cat(imgs, dim=0).to(device)
        with torch.no_grad():
            img_emb = model.encode_image(tensor)
        img_emb = img_emb / img_emb.norm(dim=-1, keepdim=True)
        embs.append(img_emb.cpu())
    return out_paths, torch.cat(embs, dim=0)

def compute_scores(img_embs, text_emb_a, text_emb_b=None):
    if text_emb_b is None:
        return (img_embs @ text_emb_a.t()).squeeze(1)
    return (img_embs @ text_emb_a.t()).squeeze(1) - (img_embs @ text_emb_b.t()).squeeze(1)

@app.post("/sort-by-clip", response_model=SortResponse)
async def sort_by_clip(req: ClipSortRequest):
    if CLIP_MODEL is None:
        raise HTTPException(503, "CLIP service not available.")
    if not req.imagePaths:
        raise HTTPException(400, "No imagePaths provided.")
    if not req.prompt:
        raise HTTPException(400, "An empty prompt was provided.")

    # 1) Split on " to " for differential sort
    parts = req.prompt.lower().split(" to ")
    if len(parts) == 2:
        text_emb_a = get_text_embedding(CLIP_MODEL, parts[0], DEVICE).to(DEVICE)
        text_emb_b = get_text_embedding(CLIP_MODEL, parts[1], DEVICE).to(DEVICE)
    else:
        text_emb_a = get_text_embedding(CLIP_MODEL, req.prompt, DEVICE).to(DEVICE)
        text_emb_b = None

    # 2) Embed images
    abs_paths, img_embs = get_image_embeddings(
        CLIP_MODEL, PREPROCESSOR, req.imagePaths, DEVICE
    )

    # 3) Score & sort
    scores = compute_scores(img_embs, text_emb_a, text_emb_b)
    pairs = sorted(zip(abs_paths, scores.tolist()), key=lambda x: x[1], reverse=True)
    sorted_paths = [p for p, _ in pairs]

    return SortResponse(sortedPaths=sorted_paths)


# ==============================================================================
# 5. RUN THE SERVER
# ==============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("unified_sorter_server:app", host="127.0.0.1", port=8000, reload=True)
