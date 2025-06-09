# gemini_quicksort.py

import os
import json
import google.generativeai as genai
import PIL.Image  # <-- Import Pillow

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables from .env (must come before any os.environ[...] reads)
load_dotenv()

# Configure the client
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

class SortRequest(BaseModel):
    imagePaths: list[str]
    dimension: str
    orderStart: str
    orderEnd: str

class SortResponse(BaseModel):
    sortedPaths: list[str]

app = FastAPI()

# 1. Instantiate the vision-capable model
# Using 'gemini-pro-vision' which is the standard model name.
model = genai.GenerativeModel('gemini-pro-vision')

@app.post("/quick-sort", response_model=SortResponse)
async def quick_sort(req: SortRequest):
    if not req.imagePaths:
        raise HTTPException(400, "No images provided")

    # 2. Define the function tool that Gemini can call
    sort_tool = {
        "function_declarations": [
            {
                "name": "sort_indices",
                "description": (
                    "Sorts a list of items and returns the sorted indices "
                    "based on the original imagePaths array."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sorted": {
                            "type": "array",
                            "items": {"type": "integer"}
                        }
                    },
                    "required": ["sorted"]
                }
            }
        ]
    }

    # 3. Build a single prompt with text and images combined
    prompt_parts = [
        f"Sort these {len(req.imagePaths)} images by {req.dimension}, "
        f"from {req.orderStart} to {req.orderEnd}. Then, call the 'sort_indices' function "
        "with the result."
    ]
    # Append each image to the prompt parts
    for path in req.imagePaths:
        try:
            img = PIL.Image.open(path)
            prompt_parts.append(img)
        except FileNotFoundError:
            raise HTTPException(400, f"Image path not found: {path}")
        except Exception as e:
            raise HTTPException(500, f"Could not process image {path}: {e}")

    # 4. Call the Gemini API using the correct SDK method
    try:
        resp = model.generate_content(
            prompt_parts,
            tools=sort_tool,
            tool_config={"function_calling_config": "ANY"} # Force the model to call a function
        )
    except Exception as e:
        raise HTTPException(500, f"An error occurred with the Gemini API: {e}")

    # 5. Parse the function call from the response
    try:
        function_call = resp.candidates[0].content.parts[0].function_call
        if function_call.name != "sort_indices":
            raise HTTPException(500, "Gemini did not return the expected function call.")

        # The SDK automatically parses arguments into a dict-like object
        fn_args = function_call.args
        idxs = fn_args["sorted"]

        # Map back to paths
        sorted_paths = [req.imagePaths[i] for i in idxs]
    except (IndexError, AttributeError, KeyError):
        # This catches errors if the response format is unexpected
        raise HTTPException(500, f"Bad or unexpected response from Gemini: {resp.text}")
    except IndexError:
        # This catches if an index from Gemini is out of bounds
        raise HTTPException(500, "Bad indices returned from Gemini")

    return SortResponse(sortedPaths=sorted_paths)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("gemini_quicksort:app", host="127.0.0.1", port=8000, reload=True)