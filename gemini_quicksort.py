# gemini_quicksort.py

import os
import google.generativeai as genai
import PIL.Image

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Configure the client
try:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
except KeyError:
    raise RuntimeError("GEMINI_API_KEY not found in environment variables. Please check your .env file.")

# 1. Define a more flexible request schema using a single 'prompt'
class SortRequest(BaseModel):
    imagePaths: list[str]
    prompt: str  # e.g., "Sort from hottest to coldest" or "Arrange by amount of blue color"

class SortResponse(BaseModel):
    sortedPaths: list[str]

app = FastAPI()

# Instantiate the vision-capable model
model = genai.GenerativeModel('gemini-1.5-flash-latest')

@app.post("/quick-sort", response_model=SortResponse) # Renamed for clarity
async def sort_by_prompt(req: SortRequest):
    if not req.imagePaths:
        raise HTTPException(400, "No imagePaths provided")
    if not req.prompt:
        raise HTTPException(400, "An empty prompt was provided")

    num_images = len(req.imagePaths)

    # ... (Tool definition is the same)
    sort_tool = {
        "function_declarations": [
            {
                "name": "return_sorted_indices",
                "description": (
                    "Returns the new order of images as a list of indices "
                    "referencing the original image array."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sorted": {
                            "type": "array",
                            "description": "The list of original indices in their new sorted order.",
                            "items": {"type": "integer"}
                        }
                    },
                    "required": ["sorted"]
                }
            }
        ]
    }

    # --- THIS IS THE CORRECTED PART ---
    # Using an f-string to allow expressions inside the braces.
    system_instruction = (
        f"You are an expert image analysis assistant. Your task is to sort the user-provided "
        f"images according to their instructions. You must return the result by calling the "
        f"`return_sorted_indices` function.\n\n"
        f"**CRITICAL INSTRUCTION:** The 'sorted' array you return **MUST** contain the exact same number of items "
        f"as the number of images provided. You have been given {num_images} images, so you **MUST** return "
        f"exactly {num_images} unique integers in the 'sorted' array. Each index from 0 to {num_images - 1} "
        f"must appear exactly once."
    )
    # --- END OF FIX ---

    user_prompt = f"Please sort these {num_images} images based on the following criteria: '{req.prompt}'"
    prompt_parts = [system_instruction, user_prompt]
    for path in req.imagePaths:
        try:
            img = PIL.Image.open(path)
            prompt_parts.append(img)
        except FileNotFoundError:
            raise HTTPException(400, f"Image path not found: {path}")
        except Exception as e:
            raise HTTPException(500, f"Could not process image {path}: {e}")

    # Call the Gemini API and perform validation (code from here is unchanged)
    try:
        resp = model.generate_content(
            prompt_parts,
            tools=sort_tool,
            tool_config={"function_calling_config": "ANY"}
        )

        function_call = resp.candidates[0].content.parts[0].function_call
        if function_call.name != "return_sorted_indices":
            raise HTTPException(500, "Gemini did not return the expected function call.")

        fn_args = function_call.args
        idxs = fn_args.get("sorted", [])

        num_expected = len(req.imagePaths)
        num_received = len(idxs)
        num_unique_received = len(set(idxs))

        if num_received != num_expected:
            raise HTTPException(
                status_code=500,
                detail=f"Gemini returned {num_received} indices, but {num_expected} were expected. The model failed to follow length constraints."
            )

        if num_unique_received != num_expected:
            raise HTTPException(
                status_code=500,
                detail=f"Gemini returned duplicate indices. Expected {num_expected} unique indices, but received {num_unique_received}. The sort is invalid."
            )

        try:
            sorted_paths = [req.imagePaths[int(i)] for i in idxs]
        except ValueError:
            raise HTTPException(500, f"Gemini returned a non-numeric index. Received: {idxs}")
        except IndexError:
            raise HTTPException(500, f"Gemini returned an out-of-bounds index. Received: {idxs}")

    except (AttributeError, KeyError) as e:
        error_text = getattr(resp, 'text', str(e))
        raise HTTPException(500, f"Bad or unexpected response structure from Gemini: {error_text}")
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(500, f"An unexpected error occurred: {e}")

    return SortResponse(sortedPaths=sorted_paths)

if __name__ == "__main__":
    import uvicorn
    # Note: The endpoint is now `/sort-by-prompt`
    uvicorn.run("gemini_quicksort:app", host="127.0.0.1", port=8000, reload=True)