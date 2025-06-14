import sys
import os
import uvicorn

# --- The Crucial Path Fix ---
# This ensures that no matter where the bundled .exe unpacks itself,
# Python knows where to look for your other script files.
# It adds the directory containing this script to the Python search path.
try:
    # This is the standard way and works for both normal execution and bundled apps.
    script_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    # A fallback for some environments where __file__ is not defined.
    script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))

sys.path.insert(0, script_dir)
# --- End of Fix ---


# Now that the path is set, this import will work correctly.
from unified_sorter_server import app

if __name__ == "__main__":
    # The final Uvicorn configuration for a packaged app:
    # - Pass the imported 'app' object directly.
    # - Disable reload.
    # - Set log_config to None to prevent the 'isatty' error.
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info",
        log_config=None
    )