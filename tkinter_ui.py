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
PADDING = 5 # Pixels around each thumbnail

class ImageSorterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Sorter")
        self.root.geometry("900x700")

        self.current_folder = ""
        self.image_paths = []
        self.photo_images = [] # IMPORTANT: Must keep reference to avoid garbage collection

        self.setup_ui()
        self.queue = queue.Queue()
        self.check_queue()

    def setup_ui(self):
        # --- Top Controls Frame ---
        controls_frame = ttk.Frame(self.root, padding="10")
        controls_frame.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(controls_frame, text="Choose Folder...", command=self.choose_folder).pack(side=tk.LEFT)
        self.folder_path_var = tk.StringVar(value="No folder chosen")
        ttk.Entry(controls_frame, textvariable=self.folder_path_var, state="readonly", width=60).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.sort_button = ttk.Button(controls_frame, text="Sort by Prompt...", command=self.start_sort_process, state="disabled")
        self.sort_button.pack(side=tk.LEFT)

        # --- Status Bar ---
        self.status_var = tk.StringVar(value="")
        ttk.Label(self.root, textvariable=self.status_var, padding="5 2").pack(side=tk.BOTTOM, fill=tk.X)

        # --- Scrollable Thumbnail Grid ---
        canvas_frame = ttk.Frame(self.root)
        canvas_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.canvas = tk.Canvas(canvas_frame)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        self.thumbnail_frame = ttk.Frame(self.canvas)

        self.thumbnail_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.thumbnail_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.root.bind('<MouseWheel>', self._on_mousewheel)

        # --- NEW: Bind window resize event to redraw the grid ---
        self.canvas.bind('<Configure>', self.redraw_thumbnails_on_resize)
        self.last_width = 0

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def choose_folder(self):
        folder_path = filedialog.askdirectory()
        if not folder_path:
            return

        self.current_folder = folder_path
        self.folder_path_var.set(self.current_folder)

        self.image_paths = sorted([
            os.path.join(self.current_folder, f)
            for f in os.listdir(self.current_folder)
            if os.path.splitext(f)[1].lower() in VALID_EXTENSIONS
        ])

        if self.image_paths:
            self.sort_button.config(state="normal")
            self.render_thumbnails()
        else:
            self.sort_button.config(state="disabled")
            self.clear_thumbnails()
            messagebox.showinfo("No Images Found", "No supported image files were found in the selected directory.")

    def clear_thumbnails(self):
        for widget in self.thumbnail_frame.winfo_children():
            widget.destroy()
        self.photo_images = []

    def render_thumbnails(self):
        self.clear_thumbnails()
        self.status_var.set(f"Loading {len(self.image_paths)} thumbnails...")
        threading.Thread(target=self.load_images_in_thread, daemon=True).start()

    def load_images_in_thread(self):
        temp_photo_images = []
        for path in self.image_paths:
            try:
                with Image.open(path) as img:
                    img.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                    temp_photo_images.append(ImageTk.PhotoImage(img))
            except Exception as e:
                print(f"Error loading image {path}: {e}")
        self.queue.put(("images_loaded", temp_photo_images))

    # --- MODIFIED: This function now uses the grid layout ---
    def on_images_loaded(self, photo_images):
        self.photo_images = photo_images # Store references
        self.display_grid()
        self.status_var.set(f"{len(self.image_paths)} images loaded.")

    # --- NEW: Helper function to display images in a grid ---
    def display_grid(self):
        # Clear existing widgets before redrawing
        for widget in self.thumbnail_frame.winfo_children():
            widget.destroy()

        if not self.photo_images:
            return

        # Calculate how many columns can fit in the current canvas width
        canvas_width = self.canvas.winfo_width()
        if canvas_width < THUMBNAIL_SIZE[0]: # handle case where canvas is not yet drawn
            self.root.after(50, self.display_grid) # retry shortly
            return

        cols = max(1, canvas_width // (THUMBNAIL_SIZE[0] + PADDING * 2))

        # Place images into the grid
        for i, photo_image in enumerate(self.photo_images):
            row = i // cols
            col = i % cols

            label = ttk.Label(self.thumbnail_frame, image=photo_image)
            label.grid(row=row, column=col, padx=PADDING, pady=PADDING)

    # --- NEW: Function to handle window resizing ---
    def redraw_thumbnails_on_resize(self, event):
        # Only redraw if the width has actually changed, to avoid redundant redraws
        if self.last_width != event.width:
            self.last_width = event.width
            self.display_grid()

    def start_sort_process(self):
        prompt_text = simpledialog.askstring("Sort Prompt", "Enter sorting prompt (e.g., from light to dark):", parent=self.root)
        if not prompt_text:
            return

        self.sort_button.config(state="disabled")
        self.status_var.set("Sorting, please wait... This may take a moment.")

        threading.Thread(target=self.perform_sort_in_thread, args=(prompt_text,), daemon=True).start()

    def perform_sort_in_thread(self, prompt):
        payload = {"imagePaths": self.image_paths, "prompt": prompt}
        try:
            response = requests.post(f"{SERVER_URL}/sort-by-clip", json=payload, timeout=300)
            response.raise_for_status()
            sorted_paths = response.json().get("sortedPaths")
            if not isinstance(sorted_paths, list):
                raise ValueError("Server response did not contain a valid 'sortedPaths' list.")
            self.queue.put(("sort_complete", sorted_paths))
        except Exception as e:
            self.queue.put(("error", f"Sort failed: {e}"))

    def on_sort_complete(self, sorted_paths):
        do_rename = messagebox.askyesno("Sort Complete", "Sort complete. Rename files on disk?")

        if do_rename:
            self.status_var.set("Renaming files...")
            try:
                self.apply_renames(sorted_paths)
                self.status_var.set("Renaming complete.")
            except Exception as e:
                self.queue.put(("error", f"Rename failed: {e}"))
                return
        else:
            self.image_paths = sorted_paths
            self.status_var.set("Sort complete (files not renamed).")

        self.render_thumbnails()
        self.sort_button.config(state="normal")

    def apply_renames(self, sorted_paths):
        renamed_paths = []
        MAX_NAME_LEN = 100
        for i, old_full_path in enumerate(sorted_paths):
            dir_name = os.path.dirname(old_full_path)
            base_name = os.path.basename(old_full_path)

            if len(base_name) > 2 and base_name[2] == '_' and base_name[:2].isdigit():
                base_name = base_name[3:]

            name_only, ext = os.path.splitext(base_name)

            if len(name_only) > MAX_NAME_LEN:
                name_only = nameOnly[:MAX_NAME_LEN]

            prefix = str(i + 1).zfill(2)
            new_base_name = f"{prefix}_{name_only}{ext}"
            new_full_path = os.path.join(dir_name, new_base_name)

            if old_full_path != new_full_path:
                if not os.path.exists(new_full_path):
                    os.rename(old_full_path, new_full_path)

            renamed_paths.append(new_full_path)

        self.image_paths = renamed_paths

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