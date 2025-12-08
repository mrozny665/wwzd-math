# ui/chat_ui.py
import threading
import tkinter as tk
from tkinter import ttk, font
from datetime import datetime
import json
import re
import os
from typing import Any
from PIL import Image, ImageTk  # WAŻNE: Wymaga pip install pillow

from ui.chat_store import ChatStore
from logic.ChatLogic import ChatLogic

BG_MAIN = "#28282A"
CARD_BG = "#3D3D40"
TEXT_COLOR = "#C3C3C5"
TEXT_COLOR_FADED = "#9C9C9F"
BG_HIDDEN_PANEL = "#222224"
ACCENT = "#849FF5"

WINDOW_W = 1280
WINDOW_H = 720
MIN_BUBBLE = 200
BUBBLE_RATIO = 0.6

class ChatUI:
    def __init__(self, root: tk.Tk, chat_logic: ChatLogic, store: ChatStore):
        self.root = root
        self.chat_logic = chat_logic
        self.store = store
        self._message_widgets = []
        
        # LISTA DO PRZECHOWYWANIA REFERENCJI OBRAZKÓW
        # Bez tego Python usuwa obrazki z pamięci (Garbage Collector) i znikają z ekranu
        self._image_refs = [] 
        
        self._setup_root()
        self._create_fonts()
        self._create_layout()
        self._create_header()
        self._create_messages_area()
        self._create_send_bar()
        self.refresh_from_store()

    def _render_markdown_to_text(self, text_widget: tk.Text, md: str, max_height=30):
        """
        Prosty renderer Markdown -> Text. Na końcu ustawia widget na disabled
        i dopasowuje height do liczby linii (maksymalnie max_height).
        Zwraca ustawioną wysokość (int).
        """
        import re

        text_widget.configure(state="normal")
        text_widget.delete("1.0", "end")

        # wydziel bloki kodu
        code_blocks = []

        def _replace_code_block(match):
            code = match.group(1)
            placeholder = f"@@CODEBLOCK{len(code_blocks)}@@"
            code_blocks.append(code)
            return placeholder

        md2 = re.sub(r"```(?:\w*\n)?(.*?)```", _replace_code_block, md, flags=re.S)

        # linie i nagłówki
        for line in md2.splitlines():
            header = re.match(r"^(#{1,6})\s+(.*)$", line)
            if header:
                text_widget.insert("end", header.group(2) + "\n")
                tag = f"h{len(header.group(1))}"
                # tagowanie później (nie potrzebujemy dokładnych indeksów tu)
                text_widget.tag_add(tag, "end-2l linestart", "end-1l lineend")
                continue
            text_widget.insert("end", line + "\n")

        # przygotuj dalej na inline-formaty
        content = text_widget.get("1.0", "end-1c")
        text_widget.delete("1.0", "end")

        # inline code
        content = re.sub(r"`([^`]+)`", lambda m: f"@@INLINECODE{m.group(1)}@@", content)
        # bold
        content = re.sub(r"\*\*(.+?)\*\*", lambda m: f"@@BOLD{m.group(1)}@@", content)
        # italic
        content = re.sub(r"(?<!@)\*(.+?)\*(?!@)|(?<!@)_(.+?)_(?!@)",
                         lambda m: f"@@ITALIC{(m.group(1) or m.group(2))}@@", content)
        # links -> "label (url)" (proste)
        content = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", content)

        # przywróć bloki kodu
        for i, code in enumerate(code_blocks):
            content = content.replace(f"@@CODEBLOCK{i}@@", f"\n@@CODEBLOCK_RAW_{i}@@\n")

        # wstaw i taguj
        for part in re.split(r"(@@.+?@@)", content):
            if not part:
                continue
            if part.startswith("@@BOLD") and part.endswith("@@"):
                inner = part[len("@@BOLD"):-2]
                start = text_widget.index("end-1c")
                text_widget.insert("end", inner)
                end = text_widget.index("end-1c")
                text_widget.tag_add("bold", start, end)
            elif part.startswith("@@ITALIC") and part.endswith("@@"):
                inner = part[len("@@ITALIC"):-2]
                start = text_widget.index("end-1c")
                text_widget.insert("end", inner)
                end = text_widget.index("end-1c")
                text_widget.tag_add("italic", start, end)
            elif part.startswith("@@INLINECODE") and part.endswith("@@"):
                inner = part[len("@@INLINECODE"):-2]
                start = text_widget.index("end-1c")
                text_widget.insert("end", inner)
                end = text_widget.index("end-1c")
                text_widget.tag_add("inlinecode", start, end)
                text_widget.insert("end", part[len("@@INLINECODE"):-2], "inlinecode")
            elif part.startswith("@@CODEBLOCK_RAW_") and part.endswith("@@"):
                idx = int(part[len("@@CODEBLOCK_RAW_"):-2])
                code = code_blocks[idx]
                text_widget.insert("end", "\n")
                start = text_widget.index("end-1c")
                text_widget.insert("end", code.rstrip("\n") + "\n")
                end = text_widget.index("end-1c")
                text_widget.tag_add("codeblock", start, end)
            else:
                text_widget.insert("end", part)

        # tagi stylów (nie przerywamy jeśli fontów brakuje)
        try:
            text_widget.tag_configure("bold", font=("Roboto", 10, "bold"))
            text_widget.tag_configure("italic", font=("Roboto", 10, "italic"))
            text_widget.tag_configure("inlinecode", font=("Courier", 10))
            text_widget.tag_configure("codeblock", font=("Courier", 9), background="#1f1f1f", foreground="#e6e6e6",
                                      lmargin1=10, lmargin2=10)
            text_widget.tag_configure("h1", font=("Roboto", 16, "bold"))
            text_widget.tag_configure("h2", font=("Roboto", 14, "bold"))
            text_widget.tag_configure("h3", font=("Roboto", 12, "bold"))
        except Exception:
            pass

        # zablokuj edycję
        text_widget.configure(state="disabled")

        # policz rzeczywistą liczbę linii (po wrapowaniu)
        # indeks 'end-1c' ma format "linia.kol", bierzemy numer linii
        end_index = text_widget.index("end-1c")
        try:
            line_count = int(end_index.split('.')[0])
        except Exception:
            line_count = 1

        # ogranicz wysokość, aby chat nie zajmował całego okna
        height = max(1, min(max_height, line_count))
        text_widget.configure(height=height)

        return height

    def _setup_root(self):
        self.root.title("WWZD MATH - Minimal Chat")
        self.root.geometry(f"{WINDOW_W}x{WINDOW_H}")
        self.root.minsize(600, 400)
        self.root.configure(bg=BG_MAIN)
        self.root.bind("<Configure>", lambda e: self.root.after(10, self._deferred_update_wraps))

    def _create_fonts(self):
        self.font_header = font.Font(family="Roboto", size=22, weight="bold")

    def _create_layout(self):
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

    def _create_header(self):
        header = tk.Frame(self.root, bg=BG_MAIN)
        header.grid(row=0, column=0, sticky="n", padx=50, pady=(12, 6))
        header.grid_columnconfigure(0, weight=1)
        lbl = tk.Label(header, text="ROZMOWA", bg=BG_MAIN, fg="white", font=self.font_header)
        lbl.grid(row=0, column=0, sticky="w", padx=(0, 20))

    def _create_messages_area(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure( "WWZD.Vertical.TScrollbar", gripcount=0, troughcolor=BG_MAIN,
                         background=CARD_BG, darkcolor=BG_MAIN, lightcolor=BG_MAIN, bordercolor=BG_MAIN, arrowcolor=BG_MAIN, width=5 )
        style.map( "WWZD.Vertical.TScrollbar",
                   background=[ ("active", CARD_BG), ("pressed", BG_MAIN), ("disabled", BG_MAIN) ],
                   arrowcolor=[ ("active", BG_MAIN), ("pressed", BG_MAIN), ("disabled", BG_MAIN) ] )

        self.messages_container = tk.Frame(self.root, bg=BG_MAIN)
        self.messages_container.grid(row=1, column=0, sticky="nswe", padx=10, pady=(0, 8))
        self.messages_container.grid_rowconfigure(0, weight=1)
        self.messages_container.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(self.messages_container, bg=BG_MAIN, highlightthickness=0, bd=0)
        self.vsb = ttk.Scrollbar(self.messages_container, orient="vertical", command=self.canvas.yview,
                                 style="WWZD.Vertical.TScrollbar")
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.grid(row=0, column=0, sticky="nswe")
        self.vsb.grid(row=0, column=1, sticky="ns")

        self.msgs_frame = tk.Frame(self.canvas, bg=BG_MAIN)
        self.msgs_window = self.canvas.create_window((0, 0), window=self.msgs_frame, anchor="nw")

        self.msgs_frame.bind("<Configure>", self._on_msgs_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_msgs_frame_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.canvas.itemconfig(self.msgs_window, width=self.canvas.winfo_width())

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.msgs_window, width=event.width)
        self._update_wraps(event.width)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _create_send_bar(self):
        send_bar = tk.Frame(self.root, bg=BG_MAIN)
        send_bar.grid(row=2, column=0, sticky="we", padx=10, pady=10)
        send_bar.grid_columnconfigure(0, weight=1)

        send_container = tk.Frame(send_bar, bg=CARD_BG, bd=0)
        send_container.grid(row=0, column=0, sticky="we")
        send_container.grid_columnconfigure(0, weight=1)
        send_container.grid_columnconfigure(1, weight=0)
        send_container.grid_propagate(False)
        send_container.configure(height=55)

        self.text_area = tk.Text(send_container, height=2, wrap="word", bg=CARD_BG, fg="white", bd=0,
                                 padx=15, pady=15, highlightthickness=0, insertbackground="white")
        self.text_area.grid(row=0, column=0, sticky="we")

        send_btn = tk.Button(send_container, text="➤", bg=CARD_BG, fg=ACCENT, relief="flat", borderwidth=0,
                             activebackground=CARD_BG, activeforeground=ACCENT, font=("Roboto", 20, "bold"),
                             cursor="hand2", command=self._on_send)
        send_btn.grid(row=0, column=1, sticky="e", padx=(0, 16))
        self.text_area.bind("<KeyPress>", self._on_text_keypress)

    def _on_text_keypress(self, event):
        if event.keysym == "Return" and not (event.state & 0x0001):
            self._on_send()
            return "break"

    def _on_send(self):
        content = self.text_area.get("1.0", "end").strip()
        if not content:
            return

        try:
            self.store.append_message("user", content, outgoing=True)
        except Exception as e:
            print("Warn: append outgoing:", e)

        self.text_area.delete("1.0", "end")
        self.refresh_from_store()

        threading.Thread(target=self._call_logic_and_display, args=(content,), daemon=True).start()

    def _call_logic_and_display(self, user_input: str):
        try:
            logic = self.chat_logic
            if logic is None:
                self.root.after(0, lambda: self._show_internal_message("(Brak ChatLogic)"))
                return

            if hasattr(logic, "call_method"):
                try:
                    logic.call_method(user_input)
                except TypeError:
                    logic.call_method()

            if hasattr(logic, "read_message"):
                logic.read_message()
            if hasattr(logic, "parse_json"):
                logic.parse_json()

            response_obj = None
            response_text = None
            if hasattr(logic, "handle_response"):
                try:
                    response_obj = logic.handle_response()
                except Exception:
                    response_obj = None

            # 3. Wyciągnięcie danych
            response_text = "(Brak odpowiedzi)"
            image_path = None
            
            if response_obj is not None:
                response_text = getattr(response_obj, "message", str(response_obj))
                # Tutaj pobieramy ścieżkę z obiektu ChatResult
                image_path = getattr(response_obj, "image_path", None)
            elif logic.last_message:
                response_text = logic.last_message
            
            # 4. Pakowanie do extra dla ChatStore
            extra = {}
            if response_obj is not None:
                raw = getattr(response_obj, "raw_json", None)
                if raw: extra["raw_json"] = raw
                # WAŻNE: Zapisujemy image_path do historii
                if image_path: extra["image_path"] = image_path

            # 5. Zapis w bazie i odświeżenie UI
            self.store.append_message("bot", str(response_text), outgoing=False, extra=extra)
            self.root.after(0, lambda: self.refresh_from_store())

        except Exception as e:
            self.root.after(0, lambda: self._show_internal_message(f"(Błąd ChatLogic): {e}"))

    def refresh_from_store(self):
        msgs = self.store.load_all()

        for w in self.msgs_frame.winfo_children():
            w.destroy()
        self._message_widgets.clear()
        
        # WAŻNE: Czyścimy referencje obrazków przy każdym odświeżeniu
        self._image_refs.clear()

        for rec in msgs:
            role = rec.get("role", "bot")
            text = rec.get("text", "")
            if role == "user":
                self._create_user_widget(text, rec)
            else:
                self._create_bot_widget(text, rec)

        self._deferred_update_wraps()
        self.canvas.yview_moveto(1.0)

    def _create_user_widget(self, text: str, rec: dict):
        wrapper = tk.Frame(self.msgs_frame, bg=BG_MAIN)
        wrapper.pack(fill="x", pady=6, padx=12)
        bubble = tk.Frame(wrapper, bg=CARD_BG, padx=12, pady=10)
        bubble.pack(side="right", anchor="e")

        txt = tk.Text(bubble, bg=CARD_BG, fg="white", bd=0, wrap="word", height=1, padx=6, pady=4,
                      highlightthickness=0)
        txt.pack(fill="x")
        try:
            self._render_markdown_to_text(txt, text, max_height=30)
        except Exception:
            txt.configure(state="normal")
            txt.delete("1.0", "end")
            txt.insert("1.0", text)
            txt.configure(state="disabled")

        self._message_widgets.append((wrapper, rec))

    def _create_bot_widget(self, text: str, rec: dict):
        wrapper = tk.Frame(self.msgs_frame, bg=BG_MAIN)
        wrapper.pack(fill="x", pady=6, padx=12)

        bubble = tk.Frame(wrapper, bg=BG_MAIN)
        bubble.pack(fill="x", anchor="w")

        # 1. Tekst
        txt = tk.Text(bubble, bg=BG_MAIN, fg=TEXT_COLOR, bd=0, wrap="word", height=1, padx=6, pady=4,
                      highlightthickness=0, insertbackground="white")
        txt.pack(fill="x", anchor="w", padx=(12, 0))

        try:
            h = self._render_markdown_to_text(txt, text) 
            txt.configure(height=h)
        except Exception as e:
            txt.configure(state="normal")
            txt.delete("1.0", "end")
            txt.insert("1.0", text)
            txt.configure(state="disabled")
            print("Warn: markdown render failed:", e)

        # 2. Obrazek (jeśli istnieje w extra)
        extra = rec.get("extra", {})
        img_path = extra.get("image_path")
        
        if img_path:
            self._render_image(bubble, img_path)

        # 3. Przyciski (JSON)
        buttons_row = tk.Frame(wrapper, bg=BG_MAIN)
        buttons_row.pack(fill="x", padx=12, pady=(6, 0))
        
        json_frame = tk.Frame(wrapper, bg=BG_HIDDEN_PANEL)
        jtext = tk.Text(json_frame, height=10, bg=BG_HIDDEN_PANEL, fg=TEXT_COLOR_FADED, bd=0, padx=8, pady=8)
        try: pretty = json.dumps(rec, indent=2, ensure_ascii=False)
        except: pretty = str(rec)
        jtext.insert("1.0", pretty)
        jtext.configure(state="disabled")
        jtext.pack(fill="x")

        def _toggle_json():
            if json_frame.winfo_ismapped(): json_frame.pack_forget()
            else: json_frame.pack(fill="x", padx=12, pady=6); self.canvas.yview_moveto(1.0)

        b = tk.Button(buttons_row, text="JSON", command=_toggle_json, bg=BG_MAIN, fg=TEXT_COLOR, relief="flat", activebackground=BG_MAIN)
        b.pack(side="left")

        self._message_widgets.append((wrapper, rec))

    # --- RYSOWANIE OBRAZKA ---
    def _render_image(self, parent, path):
        if not os.path.exists(path):
            err = tk.Label(parent, text=f"[Plik nie istnieje: {path}]", bg=BG_MAIN, fg="red")
            err.pack(anchor="w", padx=12)
            return

        try:
            # Ładowanie przez PIL
            pil_img = Image.open(path)
            
            # Skalowanie, jeśli za szeroki
            max_w = 600
            w, h = pil_img.size
            if w > max_w:
                ratio = max_w / w
                new_size = (int(w * ratio), int(h * ratio))
                pil_img = pil_img.resize(new_size, Image.Resampling.LANCZOS)
            
            # Konwersja na format Tkinter
            tk_img = ImageTk.PhotoImage(pil_img)
            
            # WAŻNE: Dodanie do listy referencji
            self._image_refs.append(tk_img) 

            # Wyświetlenie w Label
            lbl = tk.Label(parent, image=tk_img, bg=BG_MAIN, bd=0)
            lbl.pack(anchor="w", padx=(12, 0), pady=10)
            
        except Exception as e:
            err = tk.Label(parent, text=f"[Błąd obrazka: {e}]", bg=BG_MAIN, fg="red")
            err.pack(anchor="w", padx=12)

    def _update_wraps(self, width):
        pad = 40
        usable = max(0, width - pad)
        max_bubble = max(MIN_BUBBLE, int(usable * BUBBLE_RATIO))
        for wrapper, rec in self._message_widgets:
            for child in wrapper.winfo_children():
                if isinstance(child, tk.Frame):
                    for inner in child.winfo_children():
                        if isinstance(inner, tk.Label):
                            try:
                                inner.configure(wraplength=max_bubble)
                            except Exception:
                                pass

    def _deferred_update_wraps(self):
        try:
            w = self.canvas.winfo_width()
            if w > 10: 
                self.canvas.itemconfig(self.msgs_window, width=w)
                self._update_wraps(w)
        except Exception:
            pass

    def _show_internal_message(self, text):
        self.store.append_message("bot", text, False, {"internal": True})
        self.refresh_from_store()