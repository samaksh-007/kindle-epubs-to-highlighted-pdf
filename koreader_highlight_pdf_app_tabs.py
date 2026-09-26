from __future__ import annotations

import queue
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pymupdf


APP_TITLE = "Highlights to PDF / EPUB"
BOOK_EXTENSIONS = {".epub", ".azw3", ".mobi", ".azw", ".prc", ".kfx"}
KINDLE_CONVERTIBLE_EXTENSIONS = BOOK_EXTENSIONS
TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
TEXT_RE = re.compile(r'\["text"\]\s*=\s*"((?:\\.|[^"\\])*)"', re.S)


def find_calibre() -> str | None:
    candidates = [
        shutil.which("ebook-convert"),
        r"C:\Program Files\Calibre2\ebook-convert.exe",
        r"C:\Program Files (x86)\Calibre2\ebook-convert.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return None


def find_annotations(folder: Path) -> Path | None:
    candidates = list(folder.glob("*.annotations.lua")) + list(folder.glob("*.lua"))
    candidates = list(dict.fromkeys(candidates))
    if not candidates:
        return None
    candidates.sort(key=lambda p: ("annotations" in p.name.lower(), p.stat().st_size), reverse=True)
    return candidates[0]


def lua_texts(path: Path) -> list[str]:
    raw = path.read_bytes().decode("utf-8", errors="replace")
    values = []
    for encoded in TEXT_RE.findall(raw):
        value = re.sub(r"\\\r?\n\s*", " ", encoded)
        value = value.replace(r"\\", "\\").replace(r'\"', '"')
        values.append(value)
    return values


def clippings_texts(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    values = []
    for block in re.split(r"={10,}", raw):
        lines = [line.rstrip() for line in block.splitlines()]
        marker = next((i for i, line in enumerate(lines) if "Your Highlight" in line), None)
        if marker is None:
            continue
        content = "\n".join(lines[marker + 1 :]).strip()
        if content:
            values.append(content)
    return values


def extract_highlights(source: Path) -> list[str]:
    if source.is_dir():
        annotation = find_annotations(source)
        return lua_texts(annotation) if annotation else []
    return clippings_texts(source)


def tokens(text: str) -> list[str]:
    return [x.lower() for x in TOKEN_RE.findall(text)]


def words_and_refs(page_words, page_number: int):
    page_tokens = []
    refs = []
    for word in page_words:
        rect = pymupdf.Rect(word[:4])
        for part in tokens(word[4]):
            page_tokens.append(part)
            refs.append((page_number, rect))
    return page_tokens, refs


def line_quads(rects):
    groups = []
    for rect in rects:
        placed = None
        for group in groups:
            if abs(group[0].y0 - rect.y0) < 3.0:
                placed = group
                break
        if placed is None:
            groups.append([rect])
        else:
            placed.append(rect)
    quads = []
    for group in groups:
        x0 = min(r.x0 for r in group)
        y0 = min(r.y0 for r in group)
        x1 = max(r.x1 for r in group)
        y1 = max(r.y1 for r in group)
        quads.append(pymupdf.Quad(ul=(x0, y0), ur=(x1, y0), ll=(x0, y1), lr=(x1, y1)))
    return quads


def locate_sequence(all_tokens, wanted):
    size = len(wanted)
    for start in range(0, len(all_tokens) - size + 1):
        if all_tokens[start : start + size] == wanted:
            return start, start + size
    return None


def find_highlight_match(all_tokens, wanted):
    exact = locate_sequence(all_tokens, wanted)
    if exact:
        return exact, False
    # Kindle and PDF text can differ in punctuation, line wrapping, or a small
    # number of decoded words. Match reliable edges and highlight the region
    # between them when a complete exact match is unavailable.
    if len(wanted) < 8:
        return None, False
    prefix = None
    suffix = None
    for length in range(min(18, len(wanted)), 6, -1):
        if prefix is None:
            prefix = locate_sequence(all_tokens, wanted[:length])
        if suffix is None:
            found = locate_sequence(all_tokens, wanted[-length:])
            if found:
                suffix = found
        if prefix and suffix:
            break
    if prefix and suffix and suffix[0] >= prefix[0] and suffix[1] - prefix[0] <= max(150, len(wanted) * 3):
        return (prefix[0], suffix[1]), True
    if prefix:
        return prefix, True
    if suffix:
        return suffix, True
    return None, False


def create_highlight_pdf(base_pdf: Path, highlights: list[str], output_pdf: Path) -> tuple[int, int, int]:
    doc = pymupdf.open(base_pdf)
    all_tokens = []
    all_refs = []
    for page_number, page in enumerate(doc):
        page_tokens, refs = words_and_refs(page.get_text("words"), page_number)
        all_tokens.extend(page_tokens)
        all_refs.extend(refs)

    found = 0
    approximate = 0
    for text in highlights:
        wanted = tokens(text)
        match, is_approximate = find_highlight_match(all_tokens, wanted)
        if not match:
            continue
        located = all_refs[match[0] : match[1]]
        by_page = {}
        for page_number, rect in located:
            by_page.setdefault(page_number, []).append(rect)
        for page_number, rects in by_page.items():
            page = doc[page_number]
            annot = page.add_highlight_annot(line_quads(rects))
            annot.set_colors(stroke=(1.0, 0.86, 0.05))
            annot.set_opacity(0.48)
            annot.update()
        found += 1
        approximate += int(is_approximate)

    doc.set_metadata({
        "title": "Highlights",
        "subject": f"{found} highlights applied",
        "creator": APP_TITLE,
    })
    doc.save(output_pdf, garbage=4, deflate=True)
    doc.close()
    return len(highlights), found, approximate


def run_calibre(calibre: Path, book: Path, output: Path, pdf_mode: bool):
    command = [str(calibre), str(book), str(output)]
    if pdf_mode:
        command += [
            "--paper-size", "letter",
            "--pdf-page-margin-top", "54",
            "--pdf-page-margin-bottom", "54",
            "--pdf-page-margin-left", "54",
            "--pdf-page-margin-right", "54",
            "--base-font-size", "12",
            "--preserve-cover-aspect-ratio",
        ]
    return subprocess.run(command, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)


class BookTab(ttk.Frame):
    def __init__(self, parent, app, mode: str):
        super().__init__(parent, padding=20)
        self.app = app
        self.mode = mode
        self.book_var = tk.StringVar()
        self.source_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.calibre_var = tk.StringVar(value=find_calibre() or "")
        self.output_type = tk.StringVar(value="Highlighted PDF")
        self.status_var = tk.StringVar()
        self.progress_var = tk.DoubleVar(value=0)
        self._build()

    def _build(self):
        title = "KOReader books" if self.mode == "koreader" else "Normal Kindle books"
        description = (
            "Select an EPUB and its matching .sdr folder."
            if self.mode == "koreader"
            else "Select a Kindle book and My Clippings.txt, or convert a DRM-free Kindle file to EPUB."
        )
        ttk.Label(self, text=title, font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(self, text=description, foreground="#555555", wraplength=680).pack(anchor="w", pady=(3, 16))
        self._row("Book file", self.book_var, self._choose_book, "Choose book")
        if self.mode == "koreader":
            self._row("Highlights source", self.source_var, self._choose_sdr, "Choose .sdr")
        else:
            self._row("Highlights source", self.source_var, self._choose_clippings, "My Clippings.txt")
            out = ttk.Frame(self)
            out.pack(fill="x", pady=5)
            ttk.Label(out, text="Output type", width=21).pack(side="left")
            ttk.Combobox(
                out,
                textvariable=self.output_type,
                state="readonly",
                values=("Highlighted PDF", "Converted EPUB"),
                width=22,
            ).pack(side="left")
            self.output_type.trace_add("write", self._output_type_changed)
        self._row("Save as", self.output_var, self._choose_output, "Choose location")
        self._row("Calibre converter", self.calibre_var, self._choose_calibre, "Find converter")
        ttk.Separator(self).pack(fill="x", pady=18)
        self.button = ttk.Button(self, text="Create highlighted PDF" if self.mode == "koreader" else "Create output", command=self._start)
        self.button.pack(anchor="w")
        ttk.Progressbar(self, variable=self.progress_var, maximum=100).pack(fill="x", pady=(16, 8))
        ttk.Label(self, textvariable=self.status_var, wraplength=680).pack(anchor="w")
        if self.mode == "kindle":
            ttk.Label(
                self,
                text="KFX conversion is best-effort: DRM-protected KFX files or incomplete KFX companion files cannot be converted.",
                foreground="#666666",
                wraplength=680,
            ).pack(anchor="w", pady=(20, 0))

    def _row(self, label, variable, command, button_text):
        row = ttk.Frame(self)
        row.pack(fill="x", pady=5)
        ttk.Label(row, text=label, width=21).pack(side="left")
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(row, text=button_text, command=command).pack(side="right")

    def _choose_book(self):
        if self.mode == "koreader":
            types = [("EPUB books", "*.epub"), ("All files", "*.*")]
        else:
            types = [("Kindle/EPUB books", "*.epub *.azw3 *.mobi *.azw *.prc *.kfx"), ("All files", "*.*")]
        path = filedialog.askopenfilename(filetypes=types)
        if path:
            self.book_var.set(path)
            source = Path(path)
            suffix = ".epub" if self.mode == "kindle" and self.output_type.get() == "Converted EPUB" else ".pdf"
            self.output_var.set(str(source.with_name(source.stem + " - Highlights" + suffix)))

    def _choose_sdr(self):
        path = filedialog.askdirectory(title="Select the book's .sdr folder")
        if path:
            self.source_var.set(path)

    def _choose_clippings(self):
        path = filedialog.askopenfilename(
            title="Select My Clippings.txt from the Kindle",
            filetypes=[("Kindle clippings", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self.source_var.set(path)

    def _choose_output(self):
        extension = ".epub" if self.mode == "kindle" and self.output_type.get() == "Converted EPUB" else ".pdf"
        path = filedialog.asksaveasfilename(
            title="Save output",
            defaultextension=extension,
            filetypes=[("EPUB files", "*.epub"), ("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if path:
            self.output_var.set(path)

    def _choose_calibre(self):
        path = filedialog.askopenfilename(
            title="Select ebook-convert.exe",
            filetypes=[("Calibre converter", "ebook-convert.exe"), ("All files", "*.*")],
        )
        if path:
            self.calibre_var.set(path)

    def _output_type_changed(self, *_):
        book = Path(self.book_var.get().strip())
        if not book:
            return
        suffix = ".epub" if self.output_type.get() == "Converted EPUB" else ".pdf"
        self.output_var.set(str(book.with_name(book.stem + " - Highlights" + suffix)))

    def _start(self):
        book = Path(self.book_var.get().strip())
        source = Path(self.source_var.get().strip())
        output = Path(self.output_var.get().strip())
        calibre = Path(self.calibre_var.get().strip())
        output_type = "epub" if self.mode == "kindle" and self.output_type.get() == "Converted EPUB" else "pdf"

        allowed = {".epub"} if self.mode == "koreader" else KINDLE_CONVERTIBLE_EXTENSIONS
        if not book.is_file() or book.suffix.lower() not in allowed:
            messagebox.showerror(APP_TITLE, "Please choose a supported book file.")
            return
        if not calibre.is_file():
            messagebox.showerror(APP_TITLE, "Calibre's ebook-convert.exe was not found. Install Calibre or choose it manually.")
            return
        if output_type == "pdf":
            if self.mode == "koreader" and not source.is_dir():
                messagebox.showerror(APP_TITLE, "Please choose the matching .sdr folder.")
                return
            if self.mode == "kindle" and not source.is_file():
                messagebox.showerror(APP_TITLE, "Please choose My Clippings.txt.")
                return
            highlights = extract_highlights(source)
            if not highlights:
                messagebox.showerror(APP_TITLE, "No highlights were found in the selected source.")
                return
        else:
            highlights = []
        if output.suffix.lower() != (".epub" if output_type == "epub" else ".pdf"):
            output = output.with_suffix(".epub" if output_type == "epub" else ".pdf")
            self.output_var.set(str(output))
        output.parent.mkdir(parents=True, exist_ok=True)
        self.button.configure(state="disabled")
        self.progress_var.set(5)
        self.status_var.set("Converting the book...")
        threading.Thread(target=self._worker, args=(book, highlights, output, calibre, output_type), daemon=True).start()

    def _worker(self, book, highlights, output, calibre, output_type):
        try:
            if output_type == "epub":
                result = run_calibre(calibre, book, output, pdf_mode=False)
                if result.returncode != 0 or not output.exists():
                    detail = result.stderr.strip() or result.stdout.strip() or "Calibre could not convert this book."
                    raise RuntimeError(detail[-1400:])
                self.app.events.put(("done", 1, 1, str(output), "EPUB"))
                return
            with tempfile.TemporaryDirectory(prefix="kindle_highlights_") as temp:
                base_pdf = Path(temp) / "book.pdf"
                result = run_calibre(calibre, book, base_pdf, pdf_mode=True)
                if result.returncode != 0 or not base_pdf.exists():
                    detail = result.stderr.strip() or result.stdout.strip() or "Calibre could not convert this book. It may be DRM-protected or unsupported."
                    raise RuntimeError(detail[-1400:])
                self.app.events.put(("progress", 65, "Book converted. Placing highlights..."))
                total, found, approximate = create_highlight_pdf(base_pdf, highlights, output)
                self.app.events.put(("done", total, found, str(output), "PDF", approximate))
        except Exception as exc:
            self.app.events.put(("error", str(exc)))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("780x590")
        self.minsize(700, 520)
        self.events = queue.Queue()
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text=APP_TITLE, font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=8, pady=(4, 10))
        self.tabs = ttk.Notebook(outer)
        self.tabs.pack(fill="both", expand=True)
        self.tabs.add(BookTab(self.tabs, self, "koreader"), text="KOReader")
        self.tabs.add(BookTab(self.tabs, self, "kindle"), text="Kindle files")
        self.after(100, self._poll_events)

    def _poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                current = self.tabs.nametowidget(self.tabs.select())
                if event[0] == "progress":
                    _, progress, message = event
                    current.progress_var.set(progress)
                    current.status_var.set(message)
                elif event[0] == "done":
                    _, total, found, output, kind, *rest = event
                    approximate = rest[0] if rest else 0
                    current.progress_var.set(100)
                    current.status_var.set(f"Finished. Saved to {output}")
                    current.button.configure(state="normal")
                    message = f"Done!\n\nSaved {kind} to:\n{output}"
                    if kind == "PDF":
                        message = f"Done!\n\n{found} of {total} highlights were added.\n\nSaved to:\n{output}"
                        if approximate:
                            message = f"Done!\n\n{found} of {total} highlights were added.\n{approximate} used approximate text matching.\n\nSaved to:\n{output}"
                    messagebox.showinfo(APP_TITLE, message)
                elif event[0] == "error":
                    current.progress_var.set(0)
                    current.status_var.set("Something went wrong. See the error message.")
                    current.button.configure(state="normal")
                    messagebox.showerror(APP_TITLE, event[1])
        except queue.Empty:
            pass
        self.after(100, self._poll_events)


if __name__ == "__main__":
    App().mainloop()
