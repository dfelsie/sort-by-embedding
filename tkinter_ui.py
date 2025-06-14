import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox
import os
import threading
import queue
import requests
from PIL import Image, ImageTk

# --- Configuration ---
THUMBNAIL_SIZE = (128, 128)
SERVER_URL = "http://127.0.0.1:8000"
VALID_EXTENSIONS = ['.png','.jpg','.jpeg','.bmp','.gif','.webp']
PADDING = 5

class ImageSorterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Sorter")
        self.root.geometry("900x700")

        self.current_folder = ""
        self.image_paths = []

        # --- NEW: Data structures to manage canvas items intelligently ---
        self.photo_images = {} # Maps image_path -> PhotoImage object
        self.canvas_items = {} # Maps image_path -> canvas item ID

        self.setup_ui()
        self.queue = queue.Queue()
        self.check_queue()

    # --- UI Setup (unchanged) ---
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

    # --- MODIFIED: Now collects all images before sending to UI ---
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

        # Send the entire batch at once
        self.queue.put(("images_loaded", loaded_photo_images))

    # --- MODIFIED: Handles the batch of loaded images ---
    def on_images_loaded(self, loaded_photo_images):
        self.photo_images = loaded_photo_images
        self.redraw_grid() # Draw all images in one go
        self.status_var.set(f"All {len(self.image_paths)} images loaded.")

    # --- MODIFIED: Redraws the entire grid based on current state ---
    def redraw_grid(self):
        self.canvas.delete("all")
        self.canvas_items = {}

        if not self.photo_images: return

        canvas_width = self.canvas.winfo_width()
        cols = max(1, canvas_width // (THUMBNAIL_SIZE[0] + PADDING * 2))

        # Iterate through the current order of image_paths
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

    # --- MODIFIED: on_sort_complete is now much faster ---
    def on_sort_complete(self, sorted_paths):
        do_rename = messagebox.askyesno("Sort Complete", "Sort complete. Rename files on disk?")

        if do_rename:
            self.status_var.set("Renaming files...")
            try:
                # Renaming creates new paths, so we must reload
                self.image_paths = self.apply_renames(sorted_paths)
                self.load_and_render_thumbnails() # This is the one case where we must reload
            except Exception as e:
                self.queue.put(("error", f"Rename failed: {e}"))
                return
        else:
            # NO RELOAD NEEDED! Just update the order and redraw.
            self.image_paths = sorted_paths
            self.redraw_grid() # This is now instantaneous
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

    # --- Unchanged from here down ---
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

if __name__ == "__main__":
    root = tk.Tk()
    app = ImageSorterApp(root)
    root.mainloop()