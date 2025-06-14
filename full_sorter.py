import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox
import os
import threading
import queue
import requests
import subprocess
import sys
from PIL import Image, ImageTk

# --- Configuration (Unchanged) ---
THUMBNAIL_SIZE = (128, 128)
SERVER_URL = "http://127.0.0.1:8000"
VALID_EXTENSIONS = ['.png','.jpg','.jpeg','.bmp','.gif','.webp']
PADDING = 5

# --- Global variable to hold the server process ---
server_process = None

class ImageSorterApp:
    # --- The main app class is largely unchanged ---
    def __init__(self, root):
        self.root = root
        self.root.title("Image Sorter")
        self.root.geometry("900x700")
        self.photo_images = {}
        self.canvas_items = {}
        self.current_folder = ""
        self.image_paths = []
        self.setup_ui()
        self.queue = queue.Queue()
        self.check_queue()
        # NEW: Handle closing the window gracefully
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self):
        """ When the main window is closed, terminate the server and exit. """
        global server_process
        if server_process:
            print("[UI] Terminating server process...")
            server_process.terminate()
            server_process.wait()
        self.root.destroy()

    # --- All other methods from the previous version are here and unchanged ---
    # (setup_ui, _on_mousewheel, choose_folder, clear_thumbnails, etc...)
    # [ For brevity, I've omitted the 150+ lines of unchanged code. ]
    # [ Just copy and paste them from the previous version into this space. ]
    # [ The only new method is on_closing() added above.                 ]
    def setup_ui(self):
        controls_frame = ttk.Frame(self.root, padding="10")
        controls_frame.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(controls_frame, text="Choose Folder...", command=self.choose_folder).pack(side=tk.LEFT)
        self.folder_path_var = tk.StringVar(value="No folder chosen")
        ttk.Entry(controls_frame, textvariable=self.folder_path_var, state="readonly", width=60).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.sort_button = ttk.Button(controls_frame, text="Sort by Prompt...", command=self.start_sort_process, state="disabled")
        self.sort_button.pack(side=tk.LEFT)
        self.status_var = tk.StringVar(value="")
        ttk.Label(self.root, textvariable=self.status_var, padding="5 2").pack(side=tk.BOTTOM, fill=tk.X)
        canvas_frame = ttk.Frame(self.root)
        canvas_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.canvas = tk.Canvas(canvas_frame)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.root.bind('<MouseWheel>', self._on_mousewheel)
        self.canvas.bind('<Configure>', self.on_resize)
        self.last_width = 0

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def choose_folder(self):
        folder_path = filedialog.askdirectory()
        if not folder_path: return
        self.current_folder = folder_path
        self.folder_path_var.set(self.current_folder)
        self.image_paths = sorted([os.path.join(self.current_folder, f) for f in os.listdir(self.current_folder) if os.path.splitext(f)[1].lower() in VALID_EXTENSIONS])
        if self.image_paths:
            self.sort_button.config(state="normal")
            self.load_and_render_thumbnails()
        else:
            self.sort_button.config(state="disabled"); self.clear_thumbnails()
            messagebox.showinfo("No Images Found", "No supported image files were found.")

    def clear_thumbnails(self):
        self.canvas.delete("all")
        self.photo_images = {}
        self.canvas_items = {}

    def load_and_render_thumbnails(self):
        self.clear_thumbnails()
        self.status_var.set(f"Loading {len(self.image_paths)} thumbnails...")
        threading.Thread(target=self.load_images_in_thread, daemon=True).start()

    def load_images_in_thread(self):
        cache_dir = os.path.join(self.current_folder, ".thumbnails_cache")
        os.makedirs(cache_dir, exist_ok=True)
        loaded_photo_images = {}
        for path in self.image_paths:
            try:
                base_name = os.path.basename(path)
                cache_path = os.path.join(cache_dir, base_name + ".png")
                if os.path.exists(cache_path) and os.path.getmtime(cache_path) > os.path.getmtime(path):
                    img = Image.open(cache_path)
                else:
                    with Image.open(path) as original_img:
                        img = original_img.copy()
                        img.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                        img.save(cache_path, "PNG")
                loaded_photo_images[path] = ImageTk.PhotoImage(img)
            except Exception as e:
                print(f"Error loading image {path}: {e}")
        self.queue.put(("images_loaded", loaded_photo_images))

    def on_images_loaded(self, loaded_photo_images):
        self.photo_images = loaded_photo_images
        self.redraw_grid()
        self.status_var.set(f"All {len(self.image_paths)} images loaded.")

    def redraw_grid(self):
        self.canvas.delete("all")
        self.canvas_items = {}
        if not self.photo_images: return
        canvas_width = self.canvas.winfo_width()
        cols = max(1, canvas_width // (THUMBNAIL_SIZE[0] + PADDING * 2))
        for i, path in enumerate(self.image_paths):
            if path in self.photo_images:
                row = i // cols
                col = i % cols
                x = col * (THUMBNAIL_SIZE[0] + PADDING * 2) + PADDING
                y = row * (THUMBNAIL_SIZE[1] + PADDING * 2) + PADDING
                item_id = self.canvas.create_image(x, y, image=self.photo_images[path], anchor='nw')
                self.canvas_items[path] = item_id
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def on_resize(self, event):
        if self.last_width != event.width:
            self.last_width = event.width
            self.redraw_grid()

    def on_sort_complete(self, sorted_paths):
        do_rename = messagebox.askyesno("Sort Complete", "Sort complete. Rename files on disk?")
        if do_rename:
            self.status_var.set("Renaming files...")
            try:
                self.image_paths = self.apply_renames(sorted_paths)
                self.load_and_render_thumbnails()
            except Exception as e:
                self.queue.put(("error", f"Rename failed: {e}")); return
        else:
            self.image_paths = sorted_paths
            self.redraw_grid()
            self.status_var.set("Sort complete (files not renamed).")
        self.sort_button.config(state="normal")

    def apply_renames(self, sorted_paths):
        renamed_paths = []
        MAX_NAME_LEN = 100
        for i, old_path in enumerate(sorted_paths):
            dir_name, base_name = os.path.split(old_path)
            if len(base_name) > 2 and base_name[2] == '_' and base_name[:2].isdigit():
                base_name = base_name[3:]
            name_only, ext = os.path.splitext(base_name)
            if len(name_only) > MAX_NAME_LEN:
                name_only = name_only[:MAX_NAME_LEN]
            prefix = str(i + 1).zfill(2)
            new_base_name = f"{prefix}_{name_only}{ext}"
            new_full_path = os.path.join(dir_name, new_base_name)
            if old_path != new_full_path and not os.path.exists(new_full_path):
                os.rename(old_path, new_full_path)
            renamed_paths.append(new_full_path)
        return renamed_paths

    def start_sort_process(self):
        prompt_text = simpledialog.askstring("Sort Prompt", "Enter sorting prompt:", parent=self.root)
        if not prompt_text: return
        self.sort_button.config(state="disabled")
        self.status_var.set("Sorting, please wait...")
        threading.Thread(target=self.perform_sort_in_thread, args=(prompt_text,), daemon=True).start()

    def perform_sort_in_thread(self, prompt):
        payload = {"imagePaths": self.image_paths, "prompt": prompt}
        try:
            response = requests.post(f"{SERVER_URL}/sort-by-clip", json=payload, timeout=300)
            response.raise_for_status()
            sorted_paths = response.json().get("sortedPaths")
            if not isinstance(sorted_paths, list):
                raise ValueError("Server response invalid.")
            self.queue.put(("sort_complete", sorted_paths))
        except Exception as e:
            self.queue.put(("error", f"Sort failed: {e}"))

    def check_queue(self):
        try:
            message_type, data = self.queue.get_nowait()
            if message_type == "images_loaded":
                self.on_images_loaded(data)
            elif message_type == "sort_complete":
                self.on_sort_complete(data)
            elif message_type == "error":
                messagebox.showerror("Error", data)
                self.status_var.set("An error occurred.")
                self.sort_button.config(state="normal")
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.check_queue)
# --- End of Unchanged App Class ---

def create_splash_screen():
    """ Creates and returns a simple 'Loading...' Toplevel window. """
    splash_root = tk.Tk()
    splash_root.title("Loading")
    splash_root.geometry("300x100")
    splash_root.overrideredirect(True) # Frameless window
    # Center the splash screen
    screen_width = splash_root.winfo_screenwidth()
    screen_height = splash_root.winfo_screenheight()
    x = (screen_width / 2) - (300 / 2)
    y = (screen_height / 2) - (100 / 2)
    splash_root.geometry(f'+{int(x)}+{int(y)}')

    ttk.Label(splash_root, text="Loading AI Models...", font=("Helvetica", 14)).pack(expand=True)
    splash_root.update()
    return splash_root

def launch_main_app(splash_root):
    """ Destroys the splash screen and creates the main application window. """
    splash_root.destroy()
    main_root = tk.Tk()
    app = ImageSorterApp(main_root)
    main_root.mainloop()

def monitor_server(process, splash_root):
    """
    Reads the server's output line by line in a thread.
    When the ready signal is found, it schedules the main app to launch.
    """
    # Uvicorn logs to stderr by default
    for line in iter(process.stdout.readline, ''):
        line_str = line.decode('utf-8')
        print(f"[Server Log] {line_str.strip()}") # Print server logs to console
        # Check for the signal that the server is ready
        if "Uvicorn running on" in line_str:
            print("[Monitor] Server is ready! Scheduling main app launch.")
            # IMPORTANT: GUI operations must be scheduled on the main thread
            splash_root.after(0, launch_main_app, splash_root)
            break

if __name__ == "__main__":
    # 1. Show a splash screen IMMEDIATELY for good UX.
    splash = create_splash_screen()

    # 2. Start the Uvicorn server as a background subprocess.
    #    We use sys.executable to ensure it uses the same Python interpreter.
    #    We redirect stderr to stdout to capture all logs in one place.
    try:
        print("[Launcher] Starting Uvicorn server as a subprocess...")
        server_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "unified_sorter_server:app", "--host", "127.0.0.1", "--port", "8000", "--log-config", "logging.yaml"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, # Redirect stderr to stdout
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0 # Hide console on Windows
        )
        print(f"[Launcher] Server process started with PID: {server_process.pid}")
    except FileNotFoundError:
        messagebox.showerror("Error", "Could not find 'uvicorn'. Make sure it is installed in your environment.")
        splash.destroy()
        sys.exit(1)

    # 3. Start a background thread to monitor the server's output.
    monitor_thread = threading.Thread(
        target=monitor_server,
        args=(server_process, splash),
        daemon=True
    )
    monitor_thread.start()

    # 4. Run the splash screen's main loop.
    #    This keeps the splash screen visible until launch_main_app is called.
    splash.mainloop()