#!/usr/bin/env python3
"""
Image Folder Manager
---------------------
Local image management tool (using Tkinter + Pillow):

- Browse images in folders/subfolders (display subfolder names)
- Delete images / delete entire folders
- Move selected images or entire folders to another folder
  (destination dialog shows preview thumbnail of each folder)
- Navigate to previous / next folder (sequential traversal of folder tree)

Required dependencies:
    pip install pillow

Usage:
    python image_folder_manager.py [root_directory_path]

If no path is provided, a dialog will open for you to select the root folder.
"""

import os
import re
import sys
import platform
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinter.font as tkfont

try:
    from PIL import Image, ImageTk
except ImportError:
    print("Pillow is required: pip install pillow")
    sys.exit(1)

IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".tif"}
THUMB_SIZE = (140, 140)
DIALOG_THUMB_SIZE = (130, 130)
PAGE_SIZE = 48  # Number of items displayed per page (folders + images)
CELL_PAD = 12    # Padding between cells (padx + borderwidth)
CELL_EXTRA = 30  # Extra width for checkbox/text below thumbnail


def _detect_font_family():
    """Select appropriate font by OS, with Vietnamese support."""
    system = platform.system()
    if system == "Windows":
        return "Segoe UI"
    elif system == "Darwin":  # macOS
        return "Helvetica Neue"
    else:  # Linux
        return "Noto Sans Display"


FONT_FAMILY = _detect_font_family()


def is_image(filename):
    return os.path.splitext(filename)[1].lower() in IMG_EXTS


def _last_number_key(filename):
    """Extract the last number in the filename to use as sort key."""
    name = os.path.splitext(filename)[0]
    numbers = re.findall(r'\d+', name)
    if numbers:
        return int(numbers[-1])
    return -1  # Files without numbers are sorted first


def list_images(folder):
    try:
        files = [f for f in os.listdir(folder)
                 if is_image(f) and os.path.isfile(os.path.join(folder, f))]
    except OSError:
        files = []
    return sorted(files, key=_last_number_key)


def list_subfolders(folder):
    try:
        subs = [d for d in os.listdir(folder)
                if os.path.isdir(os.path.join(folder, d))]
    except OSError:
        subs = []
    return sorted(subs, key=_last_number_key)


def find_first_image(folder):
    """Find the first image in folder (direct files only, non-recursive)."""
    imgs = list_images(folder)
    if imgs:
        return os.path.join(folder, imgs[0])
    return None


def make_thumbnail(path, size, bg_color=(240, 240, 240)):
    """Create a fixed-size thumbnail, centered on bg_color background."""
    try:
        img = Image.open(path)
        img.thumbnail(size, Image.LANCZOS)
        # Create background canvas at requested size, paste image centered
        canvas = Image.new("RGB", size, bg_color)
        x = (size[0] - img.width) // 2
        y = (size[1] - img.height) // 2
        # Handle images with alpha channel
        if img.mode == "RGBA":
            canvas.paste(img, (x, y), img)
        else:
            canvas.paste(img, (x, y))
        return ImageTk.PhotoImage(canvas)
    except Exception:
        return None


class MoveDialog(tk.Toplevel):
    """Destination folder selection dialog — uses lightweight Treeview, no bulk thumbnail loading."""

    def __init__(self, master, root_dir, exclude_paths, title="Chọn thư mục đích"):
        super().__init__(master)
        self.title(title)
        self.geometry("600x500")
        self.result = None
        self.root_dir = root_dir
        self.exclude_norm = {os.path.normpath(p) for p in exclude_paths}
        self._preview_ref = None  # Keep thumbnail preview reference

        ttk.Label(self, text="Chọn thư mục đích để di chuyển tới:",
                  font=(FONT_FAMILY, 11, "bold")).pack(anchor="w", padx=10, pady=(10, 5))

        # Search bar
        search_frame = ttk.Frame(self)
        search_frame.pack(fill="x", padx=10, pady=(0, 5))
        ttk.Label(search_frame, text="Lọc:").pack(side="left")
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._filter_tree())
        ttk.Entry(search_frame, textvariable=self._search_var).pack(side="left", fill="x", expand=True, padx=(5, 0))

        # Main frame: Treeview on left, preview on right
        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Treeview
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(side="left", fill="both", expand=True)
        self.tree = ttk.Treeview(tree_frame, show="tree", selectmode="browse")
        tree_vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_vsb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # Preview panel
        preview_frame = ttk.Frame(main_frame, width=180)
        preview_frame.pack(side="right", fill="y", padx=(10, 0))
        preview_frame.pack_propagate(False)
        ttk.Label(preview_frame, text="Xem trước:", font=(FONT_FAMILY, 9, "bold")).pack(anchor="w")
        # Use Canvas to display image at exact pixel size
        self._preview_canvas = tk.Canvas(
            preview_frame, width=DIALOG_THUMB_SIZE[0], height=DIALOG_THUMB_SIZE[1],
            bg="#e0e0e0", relief="sunken", borderwidth=1
        )
        self._preview_canvas.pack(pady=5)
        self._preview_text_id = self._preview_canvas.create_text(
            DIALOG_THUMB_SIZE[0] // 2, DIALOG_THUMB_SIZE[1] // 2,
            text="(chọn thư mục)", font=(FONT_FAMILY, 9), fill="#666"
        )
        self._preview_img_id = None
        self._selected_label = ttk.Label(preview_frame, text="", wraplength=160, justify="center")
        self._selected_label.pack(pady=(5, 0))

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=10, pady=8)
        ttk.Button(btn_frame, text="Chọn thư mục này", command=self._confirm).pack(side="left")
        ttk.Button(btn_frame, text="Hủy", command=self.destroy).pack(side="right")

        # Folder data
        self._all_folders = []  # [(full_path, relative_display_name)]
        self._build_folder_list()
        self._populate_tree()

        self.transient(master)
        self.grab_set()

    def _is_excluded(self, path):
        nf = os.path.normpath(path)
        for ex in self.exclude_norm:
            if nf == ex or nf.startswith(ex + os.sep):
                return True
        return False

    def _build_folder_list(self):
        """Build flat list of all folders (fast, no image loading)."""
        self._all_folders = []
        if not self._is_excluded(self.root_dir):
            self._all_folders.append((self.root_dir, "(thư mục gốc)"))
        for dirpath, dirnames, _ in os.walk(self.root_dir):
            dirnames.sort()
            for d in dirnames:
                full = os.path.join(dirpath, d)
                if not self._is_excluded(full):
                    rel = os.path.relpath(full, self.root_dir)
                    self._all_folders.append((full, rel))

    def _populate_tree(self, filter_text=""):
        """Populate Treeview with folder list (with filtering)."""
        self.tree.delete(*self.tree.get_children())
        ft = filter_text.lower().strip()
        for full_path, display_name in self._all_folders:
            if ft and ft not in display_name.lower():
                continue
            self.tree.insert("", "end", iid=full_path, text=f"{display_name}")

    def _filter_tree(self):
        self._populate_tree(self._search_var.get())

    def _on_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        folder = sel[0]
        rel = os.path.relpath(folder, self.root_dir)
        display = "(thư mục gốc)" if rel == "." else rel
        self._selected_label.config(text=display)

        # Clear old preview image
        if self._preview_img_id:
            self._preview_canvas.delete(self._preview_img_id)
            self._preview_img_id = None

        # Load preview for the selected folder
        thumb_path = find_first_image(folder)
        if thumb_path:
            thumb = make_thumbnail(thumb_path, DIALOG_THUMB_SIZE)
            if thumb:
                self._preview_ref = thumb
                # Hide text, show image
                self._preview_canvas.itemconfigure(self._preview_text_id, text="")
                self._preview_img_id = self._preview_canvas.create_image(
                    DIALOG_THUMB_SIZE[0] // 2, DIALOG_THUMB_SIZE[1] // 2,
                    image=thumb, anchor="center"
                )
                return
        self._preview_ref = None
        self._preview_canvas.itemconfigure(self._preview_text_id, text="(không có ảnh)")

    def _confirm(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Thông báo", "Vui lòng chọn một thư mục.", parent=self)
            return
        self.result = sel[0]
        self.destroy()


class ImageFolderManager(tk.Tk):
    def __init__(self, root_dir=None):
        super().__init__()
        self.title("Trình quản lý ảnh theo thư mục")
        self.geometry("1150x720")
        self.cancelled = False

        # Set default font with Vietnamese support for the entire app (per OS)
        default_font = tkfont.nametofont("TkDefaultFont")
        default_font.configure(family=FONT_FAMILY, size=10)
        self.option_add("*Font", default_font)

        # If no root dir provided, hide window and open folder chooser dialog
        # on this window (avoid creating a second Tk() which causes hangs).
        if not root_dir:
            self.withdraw()
            self.update_idletasks()
            chosen = filedialog.askdirectory(title="Chọn thư mục ảnh gốc", parent=self)
            if not chosen:
                self.cancelled = True
                self.destroy()
                return
            root_dir = chosen
            self.deiconify()

        self.root_dir = os.path.abspath(root_dir)
        self.current_dir = self.root_dir
        self.thumb_refs = []
        self.checkbox_vars = {}   # filepath -> BooleanVar
        self.image_labels = {}    # filepath -> label widget (highlight on selection)
        self.all_folders = []     # flat sorted list, used for prev/next navigation
        self._all_items = []      # All items list (subfolder paths + image paths)
        self._loaded_count = 0    # Number of items already displayed
        self._loading = False     # Guard flag to prevent load_folder <-> _on_tree_select loop

        self._build_ui()
        self._refresh_all_folders()
        self._populate_tree()
        self.load_folder(self.root_dir)

    # ---------------- Build UI ----------------
    def _build_ui(self):
        nav = ttk.Frame(self)
        nav.pack(fill="x", padx=8, pady=6)

        ttk.Button(nav, text="◀ Thư mục trước", command=self.go_prev).pack(side="left")
        ttk.Button(nav, text="Thư mục sau ▶", command=self.go_next).pack(side="left", padx=(5, 0))
        ttk.Button(nav, text="Lên thư mục cha", command=self.go_parent).pack(side="left", padx=(15, 0))
        ttk.Button(nav, text="Làm mới", command=self.refresh_current).pack(side="left", padx=(15, 0))

        self.path_label = ttk.Label(nav, text=self.current_dir, font=(FONT_FAMILY, 10, "bold"))
        self.path_label.pack(side="left", padx=15)

        ttk.Button(nav, text="Đổi thư mục gốc...", command=self.change_root).pack(side="right")

        main = ttk.Frame(self)
        main.pack(fill="both", expand=True, padx=8, pady=4)

        left = ttk.Frame(main, width=280)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        ttk.Label(left, text="Root Directories", font=(FONT_FAMILY, 10, "bold")).pack(anchor="w")
        self.tree = ttk.Treeview(left, show="tree")
        self.tree.pack(fill="both", expand=True, pady=4)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        right = ttk.Frame(main)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))

        toolbar = ttk.Frame(right)
        toolbar.pack(fill="x", pady=(0, 6))

        ttk.Button(toolbar, text="Chọn tất cả", command=self.select_all).pack(side="left")
        ttk.Button(toolbar, text="Bỏ chọn", command=self.deselect_all).pack(side="left", padx=(5, 0))
        ttk.Button(toolbar, text="Xóa ảnh",
                   command=self.delete_selected_images).pack(side="left", padx=(15, 0))
        ttk.Button(toolbar, text="Di chuyển ảnh",
                   command=self.move_selected_images).pack(side="left", padx=(5, 0))
        ttk.Button(toolbar, text="Xóa thư mục",
                   command=self.delete_current_folder).pack(side="left", padx=(15, 0))
        ttk.Button(toolbar, text="➡ Di chuyển thư mục",
                   command=self.move_current_folder).pack(side="left", padx=(5, 0))

        self.info_label = ttk.Label(right, text="")
        self.info_label.pack(anchor="w", pady=(0, 4))

        grid_container = ttk.Frame(right)
        grid_container.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(grid_container, borderwidth=0, background="#fafafa")
        vsb = ttk.Scrollbar(grid_container, orient="vertical", command=self.canvas.yview)
        self.grid_frame = ttk.Frame(self.canvas)
        self.grid_frame.bind(
            "<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # Mouse scroll (supports both Linux and Windows)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-3, "units"))
        self.canvas.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(3, "units"))

        # Track canvas resize to recalculate columns
        self._resize_after_id = None
        self._last_canvas_width = 0
        self.canvas.bind("<Configure>", self._on_canvas_resize)

    def _on_canvas_resize(self, event):
        """When canvas resizes, recalculate columns (debounce 200ms)."""
        new_width = event.width
        if abs(new_width - self._last_canvas_width) < 20:
            return  # Ignore small changes
        self._last_canvas_width = new_width
        if self._resize_after_id:
            self.after_cancel(self._resize_after_id)
        self._resize_after_id = self.after(200, self._render_grid)

    def _calc_columns(self):
        """Calculate number of columns fitting current canvas width."""
        canvas_width = self.canvas.winfo_width()
        if canvas_width < 100:  # Not yet rendered, use default value
            canvas_width = 800
        cell_width = THUMB_SIZE[0] + CELL_PAD * 2 + CELL_EXTRA
        cols = max(1, canvas_width // cell_width)
        return cols

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ---------------- Folder tree ----------------
    def _populate_tree(self):
        self.tree.delete(*self.tree.get_children())
        root_name = os.path.basename(self.root_dir) or self.root_dir
        root_id = self.tree.insert("", "end", iid=self.root_dir, text=root_name, open=True)
        self._insert_children(root_id, self.root_dir)

    def _insert_children(self, parent_id, folder):
        for sub in list_subfolders(folder):
            full = os.path.join(folder, sub)
            node = self.tree.insert(parent_id, "end", iid=full, text=sub, open=False)
            self._insert_children(node, full)

    def _on_tree_select(self, event):
        if self._loading:
            return
        sel = self.tree.selection()
        if sel and sel[0] != self.current_dir:
            self.load_folder(sel[0])

    def _refresh_all_folders(self):
        self.all_folders = [self.root_dir]
        for dirpath, dirnames, _ in os.walk(self.root_dir):
            dirnames.sort()
            for d in dirnames:
                self.all_folders.append(os.path.join(dirpath, d))
        self.all_folders.sort()

    # ---------------- Load / display images ----------------
    def load_folder(self, folder):
        if not os.path.isdir(folder):
            messagebox.showwarning("Lỗi", f"Thư mục không tồn tại:\n{folder}")
            return
        self._loading = True  # Block _on_tree_select from re-calling load_folder
        self.current_dir = folder
        self._loaded_count = 0  # Reset loaded item count
        self.path_label.config(text=folder)
        if self.tree.exists(folder):
            try:
                self.tree.selection_set(folder)
                self.tree.see(folder)
            except tk.TclError:
                pass
        self._render_grid()
        # Use after_idle to reset _loading AFTER all queued events are processed
        self.after_idle(self._finish_loading)

    def _finish_loading(self):
        """Reset _loading flag after all queued events are processed."""
        self._loading = False

    def refresh_current(self):
        self._refresh_all_folders()
        self._populate_tree()
        self.load_folder(self.current_dir)

    def _render_grid(self):
        """Re-render entire grid (on folder change or resize)."""
        for w in self.grid_frame.winfo_children():
            w.destroy()
        self.thumb_refs.clear()
        self.checkbox_vars.clear()
        self.image_labels.clear()
        self._loaded_count = 0

        subfolders = list_subfolders(self.current_dir)
        images = list_images(self.current_dir)

        # Build list of all items: subfolders first, then images
        self._all_items = []
        for sub in subfolders:
            self._all_items.append(("folder", os.path.join(self.current_dir, sub), sub))
        for fname in images:
            self._all_items.append(("image", os.path.join(self.current_dir, fname), fname))

        self.info_label.config(
            text=f"{len(subfolders)} thư mục con, {len(images)} ảnh trong: {self.current_dir}"
        )

        # Load the first batch
        self._load_more()

    def _load_more(self):
        """Load the next PAGE_SIZE items and append to grid (without clearing old ones)."""
        total_items = len(self._all_items)
        if self._loaded_count >= total_items:
            return

        start = self._loaded_count
        end = min(start + PAGE_SIZE, total_items)
        batch = self._all_items[start:end]

        cols = self._calc_columns()

        for i, (item_type, full_path, name) in enumerate(batch):
            global_idx = start + i
            row, col = divmod(global_idx, cols)

            if item_type == "folder":
                cell = ttk.Frame(self.grid_frame, relief="raised", borderwidth=1, padding=5)
                cell.grid(row=row, column=col, padx=6, pady=6, sticky="n")

                thumb_path = find_first_image(full_path)
                thumb_img = make_thumbnail(thumb_path, THUMB_SIZE) if thumb_path else None
                if thumb_img:
                    self.thumb_refs.append(thumb_img)
                    lbl = tk.Label(cell, image=thumb_img, cursor="hand2")
                else:
                    lbl = tk.Label(cell, text="(thư mục trống)", font=(FONT_FAMILY, 9, "bold"), width=18, height=7,
                                    relief="groove", cursor="hand2")
                lbl.pack()
                lbl.bind("<Button-1>", lambda e, f=full_path: self.load_folder(f))

                ttk.Label(cell, text=f"{name}", font=(FONT_FAMILY, 9, "bold")).pack(pady=(4, 0))

            else:  # image
                cell = ttk.Frame(self.grid_frame, relief="solid", borderwidth=1, padding=5)
                cell.grid(row=row, column=col, padx=6, pady=6, sticky="n")

                thumb_img = make_thumbnail(full_path, THUMB_SIZE)
                if thumb_img:
                    self.thumb_refs.append(thumb_img)
                    lbl = tk.Label(cell, image=thumb_img, cursor="hand2")
                else:
                    lbl = tk.Label(cell, text="(lỗi ảnh)", width=18, height=7, relief="groove")
                lbl.pack()
                lbl.bind("<Button-1>", lambda e, f=full_path: self._toggle_select(f))
                self.image_labels[full_path] = lbl

                var = tk.BooleanVar(value=False)
                self.checkbox_vars[full_path] = var
                chk = ttk.Checkbutton(cell, text=name, variable=var,
                                       command=lambda f=full_path: self._sync_checkbox(f))
                chk.pack()

        self._loaded_count = end

        # Update / hide the "Load more" button
        self._update_load_more_btn()

    def _update_load_more_btn(self):
        """Show or hide the Load More button depending on remaining items."""
        total = len(self._all_items)
        remaining = total - self._loaded_count

        # Remove old button if exists
        if hasattr(self, '_load_more_frame') and self._load_more_frame:
            self._load_more_frame.destroy()
            self._load_more_frame = None

        if remaining > 0:
            cols = self._calc_columns()
            next_row = (self._loaded_count + cols - 1) // cols
            self._load_more_frame = ttk.Frame(self.grid_frame)
            self._load_more_frame.grid(row=next_row, column=0, columnspan=cols,
                                        pady=10, sticky="ew")
            btn_text = f"Tải thêm ({remaining} còn lại)  ▼"
            ttk.Button(self._load_more_frame, text=btn_text,
                       command=self._load_more).pack()
            ttk.Label(self._load_more_frame,
                      text=f"Đang hiển {self._loaded_count}/{total}",
                      font=(FONT_FAMILY, 8)).pack(pady=(2, 0))
        else:
            self._load_more_frame = None

    def _toggle_select(self, filepath):
        var = self.checkbox_vars.get(filepath)
        if var:
            var.set(not var.get())
            self._sync_checkbox(filepath)

    def _sync_checkbox(self, filepath):
        var = self.checkbox_vars.get(filepath)
        lbl = self.image_labels.get(filepath)
        if var and lbl:
            lbl.config(bg="#a8d8ff" if var.get() else self.cget("bg"))

    def select_all(self):
        for f, var in self.checkbox_vars.items():
            var.set(True)
            self._sync_checkbox(f)

    def deselect_all(self):
        for f, var in self.checkbox_vars.items():
            var.set(False)
            self._sync_checkbox(f)

    def _get_selected_images(self):
        return [f for f, var in self.checkbox_vars.items() if var.get()]

    # ---------------- Previous / Next navigation ----------------
    def go_prev(self):
        self._refresh_all_folders()
        try:
            idx = self.all_folders.index(self.current_dir)
        except ValueError:
            idx = 0
        if idx > 0:
            self.load_folder(self.all_folders[idx - 1])
        else:
            messagebox.showinfo("Thông báo", "Đây là thư mục đầu tiên.")

    def go_next(self):
        self._refresh_all_folders()
        try:
            idx = self.all_folders.index(self.current_dir)
        except ValueError:
            idx = -1
        if 0 <= idx < len(self.all_folders) - 1:
            self.load_folder(self.all_folders[idx + 1])
        else:
            messagebox.showinfo("Thông báo", "Đây là thư mục cuối cùng.")

    def go_parent(self):
        if os.path.normpath(self.current_dir) == os.path.normpath(self.root_dir):
            messagebox.showinfo("Thông báo", "Đã ở thư mục gốc.")
            return
        parent = os.path.dirname(self.current_dir.rstrip(os.sep))
        if not parent or not os.path.isdir(parent):
            parent = self.root_dir
        self.load_folder(parent)

    # ---------------- Delete ----------------
    def delete_selected_images(self):
        selected = self._get_selected_images()
        if not selected:
            messagebox.showinfo("Thông báo", "Chưa chọn ảnh nào.")
            return
        if not messagebox.askyesno("Xác nhận xóa",
                                    f"Xóa vĩnh viễn {len(selected)} ảnh đã chọn?"):
            return
        errors = []
        for f in selected:
            try:
                os.remove(f)
            except OSError as e:
                errors.append(f"{f}: {e}")
        if errors:
            messagebox.showerror("Lỗi", "Một số tệp không xóa được:\n" + "\n".join(errors))
        self.refresh_current()

    def delete_current_folder(self):
        if os.path.normpath(self.current_dir) == os.path.normpath(self.root_dir):
            messagebox.showwarning("Không thể xóa", "Không thể xóa thư mục gốc.")
            return
        n_img = len(list_images(self.current_dir))
        n_sub = len(list_subfolders(self.current_dir))
        if not messagebox.askyesno(
            "Xác nhận xóa thư mục",
            f"Xóa toàn bộ thư mục:\n{self.current_dir}\n\n"
            f"({n_img} ảnh, {n_sub} thư mục con sẽ bị xóa vĩnh viễn)\n\nBạn có chắc chắn?"
        ):
            return
        parent = os.path.dirname(self.current_dir.rstrip(os.sep))
        try:
            shutil.rmtree(self.current_dir)
        except OSError as e:
            messagebox.showerror("Lỗi", f"Không thể xóa thư mục:\n{e}")
            return
        self._refresh_all_folders()
        self._populate_tree()
        self.load_folder(parent if os.path.isdir(parent) else self.root_dir)

    # ---------------- Move ----------------
    def move_selected_images(self):
        selected = self._get_selected_images()
        if not selected:
            messagebox.showinfo("Thông báo", "Chưa chọn ảnh nào.")
            return
        dlg = MoveDialog(self, self.root_dir, exclude_paths=[self.current_dir],
                          title=f"Di chuyển {len(selected)} ảnh tới...")
        self.wait_window(dlg)
        dest = dlg.result
        if not dest:
            return
        errors = []
        for f in selected:
            try:
                shutil.move(f, os.path.join(dest, os.path.basename(f)))
            except (shutil.Error, OSError) as e:
                errors.append(f"{f}: {e}")
        if errors:
            messagebox.showerror("Lỗi", "Một số tệp không di chuyển được:\n" + "\n".join(errors))
        self.refresh_current()

    def move_current_folder(self):
        if os.path.normpath(self.current_dir) == os.path.normpath(self.root_dir):
            messagebox.showwarning("Không thể di chuyển", "Không thể di chuyển thư mục gốc.")
            return
        dlg = MoveDialog(self, self.root_dir, exclude_paths=[self.current_dir],
                          title=f"Di chuyển thư mục '{os.path.basename(self.current_dir)}' tới...")
        self.wait_window(dlg)
        dest = dlg.result
        if not dest:
            return
        if os.path.normpath(dest) == os.path.normpath(os.path.dirname(self.current_dir)):
            messagebox.showinfo("Thông báo", "Thư mục đích trùng với thư mục cha hiện tại.")
            return
        target = os.path.join(dest, os.path.basename(self.current_dir))
        if os.path.exists(target):
            messagebox.showerror("Lỗi", f"Thư mục đích đã có thư mục cùng tên:\n{target}")
            return
        src = self.current_dir
        try:
            shutil.move(src, dest)
        except (shutil.Error, OSError) as e:
            messagebox.showerror("Lỗi", f"Không thể di chuyển thư mục:\n{e}")
            return
        self._refresh_all_folders()
        self._populate_tree()
        self.load_folder(dest)

    # ---------------- Other ----------------
    def change_root(self):
        new_root = filedialog.askdirectory(title="Chọn thư mục gốc mới")
        if new_root:
            self.root_dir = os.path.abspath(new_root)
            self.current_dir = self.root_dir
            self._refresh_all_folders()
            self._populate_tree()
            self.load_folder(self.root_dir)


def main():
    # Join all arguments with spaces to support paths with spaces
    root_dir = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
    if root_dir and not os.path.isdir(root_dir):
        print(f"Thư mục không tồn tại: {root_dir}")
        return

    app = ImageFolderManager(root_dir)
    if app.cancelled:
        print("Chưa chọn thư mục. Thoát chương trình.")
        return

    app.mainloop()


if __name__ == "__main__":
    main()