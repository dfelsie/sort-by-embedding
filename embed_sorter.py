# embed_sorter.py

import sys
import os
import json
import torch
import open_clip  # pip install open_clip_torch
from PIL import Image
from pathlib import Path

def load_clip_model():
    # You can switch to a different CLIP variant if you want.
    model_name, pretrained = "ViT-B-32", "openai"
    model, _, preprocess = open_clip.create_model_and_transforms(model_name, pretrained=pretrained)
    model.eval()
    return model, preprocess

def get_text_embedding(model, text, device):
    tokenizer = open_clip.get_tokenizer("ViT-B-32")
    text_tokens = tokenizer(text).to(device)
    with torch.no_grad():
        text_emb = model.encode_text(text_tokens)
    text_emb = text_emb / text_emb.norm(dim=-1, keepdim=True)
    return text_emb.cpu()

def get_image_embeddings(model, preprocess, img_paths, device, batch_size=16):
    embs = []
    to_cpu = []
    for i in range(0, len(img_paths), batch_size):
        batch_paths = img_paths[i:i+batch_size]
        images = []
        for p in batch_paths:
            img = Image.open(p).convert("RGB")
            images.append(preprocess(img).unsqueeze(0))
        images = torch.cat(images, dim=0).to(device)
        with torch.no_grad():
            img_emb = model.encode_image(images)
        img_emb = img_emb / img_emb.norm(dim=-1, keepdim=True)
        embs.append(img_emb.cpu())
        to_cpu.extend(batch_paths)
    all_embs = torch.cat(embs, dim=0)  # shape: (N, D)
    return to_cpu, all_embs

def compute_scores(img_embs, text_emb, text_emb_b=None):
    # If text_emb_b is provided, we do (cos(img, A) – cos(img, B))
    # Otherwise, we do cos(img, text_emb).
    if text_emb_b is None:
        # single‐end prompt
        scores = (img_embs @ text_emb.t()).squeeze(1)  # (N,)
    else:
        scores = (img_embs @ text_emb.t()).squeeze(1) - (img_embs @ text_emb_b.t()).squeeze(1)
    return scores

def load_payload(arg):
    """
    If arg is a path to an existing file, read its contents (JSON) and parse it.
    Otherwise, parse arg directly as JSON.
    """
    if os.path.isfile(arg):
        with open(arg, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        return json.loads(arg)

def main():
    """
    Usage:
      python embed_sorter.py <payload_or_payload_filepath>
    Where <payload_or_payload_filepath> is either:
      - A JSON string: '{"folderPath":"...", "imagePaths":[...], "prompt":"hot to cold"}'
      - Or a path to a .json file containing that payload.
    Outputs:
      JSON-serialized array of sorted imagePaths, printed to stdout.
    """
    payload_arg = sys.argv[1]
    data = load_payload(payload_arg)

    image_paths = data["imagePaths"]
    prompt = data["prompt"].strip()

    # Device: GPU if available, else CPU
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, preprocess = load_clip_model()
    model.to(device)

    # Parse prompt: check if “to” is in text
    parts = prompt.lower().split(" to ")
    if len(parts) == 2:
        term_a, term_b = parts
        text_emb_a = get_text_embedding(model, term_a, device).to(device)
        text_emb_b = get_text_embedding(model, term_b, device).to(device)
    else:
        term_a = prompt
        text_emb_a = get_text_embedding(model, term_a, device).to(device)
        text_emb_b = None

    # Compute all image embeddings
    abs_paths, img_embs = get_image_embeddings(model, preprocess, image_paths, device)

    # Compute scores
    if text_emb_b is None:
        scores = compute_scores(img_embs, text_emb_a)
    else:
        scores = compute_scores(img_embs, text_emb_a, text_emb_b)

    # Pair each path with its score
    pairs = list(zip(abs_paths, scores.tolist()))
    # Sort descending (highest score first)
    pairs.sort(key=lambda x: x[1], reverse=True)
    sorted_paths = [p for p, _ in pairs]

    # Output JSON to stdout
    print(json.dumps(sorted_paths))

if __name__ == "__main__":
    main()
