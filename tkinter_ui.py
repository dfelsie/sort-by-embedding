import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox
import os
import threading
import queue
import requests
import subprocess
import sys
from PIL import Image, ImageTk
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# --- Configuration ---
THUMBNAIL_SIZE = (128, 128)
SERVER_URL = "http://127.0.0.1:8000"
VALID_EXTENSIONS = ['.png','.jpg','.jpeg','.bmp','.gif','.webp']
PADDING = 5
MAX_WORKER_THREADS = 8  # Adjust based on your CPU cores

# --- Global variable to hold the server process ---
server_process = None

class ImageSorterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Sorter")
        self.root.geometry("900x700")

        self.current_folder = ""
        self.image_paths = []

        # --- Data structures to manage canvas items intelligently ---
        self.photo_images = {} # Maps image_path -> PhotoImage object
        self.canvas_items = {} # Maps image_path -> canvas item ID
        self.loading_cancelled = False

        self.setup_ui()
        self.queue = queue.Queue()
        self.check_queue()

        # Handle closing the window gracefully to terminate the server
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self):
        """ When the main window is closed, terminate the server and exit. """
        global server_process
        if server_process:
            print("[UI] Terminating server process...")
            server_process.terminate()
            server_process.wait()
        self.root.destroy()

    def setup_ui(self):
        controls_frame = ttk.Frame(self.root, padding="10")
        controls_frame.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(controls_frame, text="Choose Folder...", command=self.choose_folder).pack(side=tk.LEFT)
        self.folder_path_var = tk.StringVar(value="No folder chosen")
        ttk.Entry(controls_frame, textvariable=self.folder_path_var, state="readonly", width=60).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.sort_button = ttk.Button(controls_frame, text="Sort by Prompt...", command=self.start_sort_process, state="disabled")
        self.sort_button.pack(side=tk.LEFT)

        # Add progress bar
        self.progress_bar = ttk.Progressbar(self.root, orient="horizontal", length=100, mode="determinate")
        self.progress_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 5))

        self.status_var = tk.StringVar(value="Ready. Please choose a folder.")
        ttk.Label(self.root, textvariable=self.status_var, padding="5 0").pack(side=tk.BOTTOM, fill=tk.X)

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

        # Cancel any ongoing loading
        self.loading_cancelled = True
        time.sleep(0.1) # Give thread a moment to see the flag

        self.current_folder = folder_path
        self.folder_path_var.set(self.current_folder)
        self.image_paths = sorted([os.path.join(self.current_folder, f) for f in os.listdir(self.current_folder) if os.path.splitext(f)[1].lower() in VALID_EXTENSIONS])
        if self.image_paths:
            self.sort_button.config(state="disabled")
            self.load_and_render_thumbnails()
        else:
            self.sort_button.config(state="disabled")
            self.clear_thumbnails()
            messagebox.showinfo("No Images Found", "No supported image files were found.")

    def clear_thumbnails(self):
        self.canvas.delete("all")
        self.photo_images = {}
        self.canvas_items = {}
        self.progress_bar['value'] = 0

    def load_and_render_thumbnails(self):
        self.clear_thumbnails()
        self.loading_cancelled = False
        self.status_var.set(f"Loading {len(self.image_paths)} thumbnails...")
        self.progress_bar['value'] = 0
        threading.Thread(target=self.load_images_parallel, daemon=True).start()

    def process_single_image(self, path):
        if self.loading_cancelled:
            return None, None
        try:
            cache_dir = os.path.join(self.current_folder, ".thumbnails_cache")
            base_name = os.path.basename(path)
            cache_path = os.path.join(cache_dir, base_name + ".png")
            if os.path.exists(cache_path) and os.path.getmtime(cache_path) > os.path.getmtime(path):
                img = Image.open(cache_path)
            else:
                with Image.open(path) as original_img:
                    img = original_img.copy()
                    img.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                    img.save(cache_path, "PNG")
            return path, img
        except Exception as e:
            print(f"Error loading image {path}: {e}")
            return path, None

    def load_images_parallel(self):
        cache_dir = os.path.join(self.current_folder, ".thumbnails_cache")
        os.makedirs(cache_dir, exist_ok=True)
        total_images = len(self.image_paths)
        loaded_images = {}
        completed_count = 0
        with ThreadPoolExecutor(max_workers=MAX_WORKER_THREADS) as executor:
            future_to_path = {executor.submit(self.process_single_image, path): path for path in self.image_paths}
            for future in as_completed(future_to_path):
                if self.loading_cancelled: break
                path, img = future.result()
                completed_count += 1
                if img is not None:
                    loaded_images[path] = img
                if completed_count % 5 == 0 or completed_count == total_images:
                    progress = (completed_count / total_images) * 100
                    self.queue.put(("progress_update", {"progress": progress, "status": f"Processing images {completed_count}/{total_images}..."}))
        if not self.loading_cancelled:
            self.queue.put(("images_processed", loaded_images))

    def create_photo_images(self, pil_images):
        photo_images = {}
        total = len(pil_images)
        for i, (path, pil_img) in enumerate(pil_images.items()):
            if self.loading_cancelled: break
            try:
                photo_images[path] = ImageTk.PhotoImage(pil_img)
            except Exception as e:
                print(f"Error creating PhotoImage for {path}: {e}")
            if (i + 1) % 10 == 0 or (i + 1) == total:
                progress = ((i + 1) / total) * 100
                self.queue.put(("progress_update", {"progress": progress, "status": f"Preparing UI {i + 1}/{total}..."}))
        return photo_images

    def on_images_processed(self, pil_images):
        if self.loading_cancelled: return
        self.status_var.set("Preparing UI...")
        self.photo_images = self.create_photo_images(pil_images)
        if not self.loading_cancelled:
            self.redraw_grid()
            self.status_var.set(f"All {len(self.photo_images)} images loaded.")
            self.progress_bar['value'] = 100
            self.sort_button.config(state="normal")

    def on_progress_update(self, data):
        self.progress_bar['value'] = data["progress"]
        self.status_var.set(data["status"])

    def redraw_grid(self):
        self.canvas.delete("all")
        self.canvas_items = {}
        if not self.photo_images: return
        canvas_width = self.canvas.winfo_width()
        if canvas_width <= 1: canvas_width = 800
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
            self.progress_bar['value'] = 0
            try:
                self.image_paths = self.apply_renames(sorted_paths)
                self.load_and_render_thumbnails()
            except Exception as e:
                self.queue.put(("error", f"Rename failed: {e}")); return
        else:
            self.image_paths = sorted_paths
            self.redraw_grid()
            self.status_var.set("Sort complete (files not renamed).")
            self.progress_bar['value'] = 100
        self.sort_button.config(state="normal")

    def apply_renames(self, sorted_paths):
        renamed_paths = []; MAX_NAME_LEN = 100; total = len(sorted_paths)
        for i, old_path in enumerate(sorted_paths):
            if i % 10 == 0 or i == total - 1:
                progress = ((i + 1) / total) * 100
                self.progress_bar['value'] = progress
                self.status_var.set(f"Renaming files {i + 1}/{total}...")
                self.root.update_idletasks()
            dir_name, base_name = os.path.split(old_path)
            if len(base_name) > 2 and base_name[2] == '_' and base_name[:2].isdigit():
                base_name = base_name[3:]
            name_only, ext = os.path.splitext(base_name)
            if len(name_only) > MAX_NAME_LEN: name_only = name_only[:MAX_NAME_LEN]
            prefix = str(i + 1).zfill(2); new_base_name = f"{prefix}_{name_only}{ext}"
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
        self.progress_bar['value'] = 0
        threading.Thread(target=self.perform_sort_in_thread, args=(prompt_text,), daemon=True).start()

    def perform_sort_in_thread(self, prompt):
        payload = {"imagePaths": self.image_paths, "prompt": prompt}
        try:
            response = requests.post(f"{SERVER_URL}/sort-by-clip", json=payload, timeout=300)
            response.raise_for_status()
            sorted_paths = response.json().get("sortedPaths")
            if not isinstance(sorted_paths, list): raise ValueError("Server response invalid.")
            self.queue.put(("sort_complete", sorted_paths))
        except Exception as e:
            self.queue.put(("error", f"Sort failed: {e}"))

    def check_queue(self):
        try:
            message_type, data = self.queue.get_nowait()
            if message_type == "images_processed":
                self.on_images_processed(data)
            elif message_type == "progress_update":
                self.on_progress_update(data)
            elif message_type == "sort_complete":
                self.on_sort_complete(data)
            elif message_type == "error":
                messagebox.showerror("Error", data)
                self.status_var.set("An error occurred.")
                self.progress_bar['value'] = 0
                self.sort_button.config(state="normal")
        except queue.Empty:
            pass
        finally:
            self.root.after(10, self.check_queue) # Check queue more frequently for smoother progress bars

# --- New Launcher Logic ---

def create_splash_screen():
    """ Creates and returns a simple 'Loading...' Toplevel window. """
    splash_root = tk.Tk()
    splash_root.title("Loading")
    splash_root.geometry("300x100")
    splash_root.overrideredirect(True) # Frameless window
    screen_width = splash_root.winfo_screenwidth()
    screen_height = splash_root.winfo_screenheight()
    x_coord = int((screen_width / 2) - (300 / 2))
    y_coord = int((screen_height / 2) - (100 / 2))
    splash_root.geometry(f"+{x_coord}+{y_coord}")
    ttk.Label(splash_root, text="Loading AI Models...", font=("Helvetica", 14)).pack(expand=True, pady=20)
    splash_root.update()
    return splash_root

def launch_main_app(splash_root):
    """ Destroys the splash screen and creates the main application window. """
    splash_root.destroy()
    main_root = tk.Tk()
    app = ImageSorterApp(main_root)
    main_root.mainloop()

def monitor_server(process, splash_root):
    """ Reads the server's output and launches the app when ready. """
    for line in iter(process.stdout.readline, b''):
        line_str = line.decode('utf-8', errors='ignore')
        print(f"[Server Log] {line_str.strip()}")
        if "Uvicorn running on" in line_str:
            print("[Monitor] Server is ready! Scheduling main app launch.")
            splash_root.after(0, launch_main_app, splash_root)
            break

if __name__ == "__main__":
    splash = create_splash_screen()
    try:
        print("[Launcher] Starting Uvicorn server as a subprocess...")
        creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        server_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "unified_sorter_server:app", "--host", "127.0.0.1", "--port", "8000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=creation_flags
        )
        print(f"[Launcher] Server process started with PID: {server_process.pid}")
    except FileNotFoundError:
        messagebox.showerror("Error", "Could not find 'uvicorn'. Make sure it is installed.")
        splash.destroy()
        sys.exit(1)

    monitor_thread = threading.Thread(
        target=monitor_server,
        args=(server_process, splash),
        daemon=True
    )
    monitor_thread.start()
    splash.mainloop()