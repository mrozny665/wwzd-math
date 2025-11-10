# ui/chat_ui.py
import threading
import tkinter as tk
from tkinter import ttk, font
from datetime import datetime
import json
import re
from typing import Any

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

            if response_obj is not None:
                if hasattr(response_obj, "message"):
                    response_text = getattr(response_obj, "message")
                else:
                    response_text = str(response_obj)

            if not response_text:
                if hasattr(logic, "last_message") and getattr(logic, "last_message") not in (None, ""):
                    response_text = getattr(logic, "last_message")
                elif hasattr(logic, "response") and getattr(logic, "response") not in (None, ""):
                    response_text = getattr(logic, "response")

            if not response_text:
                response_text = "(Brak odpowiedzi z ChatLogic)"

            extra = {}
            if response_obj is not None:
                raw = getattr(response_obj, "raw_json", None)
                content_str = getattr(response_obj, "content", None)
                content_raw = getattr(response_obj, "content_raw", None)
                if raw is not None:
                    extra["raw_json"] = raw
                if content_str is not None:
                    extra["content"] = content_str
                if content_raw is not None:
                    extra["content_raw"] = content_raw

            try:
                self.store.append_message("bot", str(response_text), outgoing=False, extra=extra or None)
            except Exception as e:
                print("Warn: append incoming:", e)

            self.root.after(0, lambda: self.refresh_from_store())

        except Exception as e:
            self.root.after(0, lambda: self._show_internal_message(f"(Błąd ChatLogic): {e}"))

    def refresh_from_store(self):
        msgs = self.store.load_all()

        for w in self.msgs_frame.winfo_children():
            w.destroy()
        self._message_widgets.clear()

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

        txt = tk.Text(bubble, bg=BG_MAIN, fg=TEXT_COLOR, bd=0, wrap="word", height=1, padx=6, pady=4,
                      highlightthickness=0, insertbackground="white")
        txt.pack(fill="x", anchor="w", padx=(12, 0))

        try:
            self._render_markdown_to_text(txt, text, max_height=30)
        except Exception as e:
            txt.configure(state="normal")
            txt.delete("1.0", "end")
            txt.insert("1.0", text)
            txt.configure(state="disabled")
            print("Warn: markdown render failed:", e)

        buttons_row = tk.Frame(wrapper, bg=BG_MAIN)
        buttons_row.pack(fill="x", padx=12, pady=(6, 0))

        btn_style_kwargs = {
            "bg": BG_MAIN, "fg": TEXT_COLOR, "activebackground": BG_MAIN,
            "activeforeground": TEXT_COLOR, "relief": "flat", "bd": 0, "cursor": "hand2",
            "disabledforeground": TEXT_COLOR_FADED
        }

        def _make_button(parent, text_btn, cmd):
            b = tk.Button(parent, text=text_btn, command=cmd, **btn_style_kwargs)
            b.configure(highlightthickness=1, highlightbackground=CARD_BG, highlightcolor=CARD_BG, padx=8, pady=4)
            b.pack(side="left", padx=(0, 8))
            return b

        # pokaż pełen JSON całego rekordu
        json_details_frame = tk.Frame(wrapper, bg=BG_HIDDEN_PANEL)
        json_text = tk.Text(json_details_frame, height=20, bg=BG_HIDDEN_PANEL, fg=TEXT_COLOR_FADED,
                            bd=0, padx=8, pady=8, wrap="word")
        try:
            pretty = json.dumps(rec, indent=2, ensure_ascii=False)
        except Exception:
            pretty = str(rec)
        json_text.insert("1.0", pretty)
        json_text.configure(state="disabled")
        json_text.pack(fill="x")

        def _toggle_json():
            if json_details_frame.winfo_ismapped():
                json_details_frame.pack_forget()
            else:
                json_details_frame.pack(fill="x", padx=12, pady=(6, 0))
                self.canvas.yview_moveto(1.0)

        _make_button(buttons_row, "Pokaż JSON", _toggle_json)

        info_frame = tk.Frame(wrapper, bg=BG_HIDDEN_PANEL)
        def _toggle_info():
            if info_frame.winfo_ismapped():
                info_frame.pack_forget()
            else:
                for c in info_frame.winfo_children():
                    c.destroy()
                self._build_info_block(info_frame, rec)
                info_frame.pack(fill="x", padx=12, pady=(6, 0))
                self.canvas.yview_moveto(1.0)

        _make_button(buttons_row, "Informacje", _toggle_info)
        self._message_widgets.append((wrapper, rec))

    def _build_info_block(self, frame: tk.Frame, rec: dict):
        extra = rec.get("extra", {})
        raw = extra.get("raw_json", {})
        usage = raw.get("usage", {})
        reasoning = None
        try:
            choices = raw.get("choices")
            if choices and isinstance(choices, list) and len(choices) > 0:
                first = choices[0]
                msg = first.get("message") or {}
                reasoning = msg.get("reasoning")
        except Exception:
            pass

        def add_line(label, value):
            row = tk.Frame(frame, bg=BG_HIDDEN_PANEL)
            row.pack(fill="x", padx=8, pady=2, anchor="w")
            tk.Label(row, text=f"{label}:", bg=BG_HIDDEN_PANEL, fg=TEXT_COLOR_FADED).pack(side="left")
            tk.Label(row, text=value, bg=BG_HIDDEN_PANEL, fg=TEXT_COLOR, wraplength=self._compute_wraplength(), justify="left").pack(side="left", padx=(6, 0))

        if rec.get("timestamp"):
            add_line("Czas", rec.get("timestamp"))
        if rec.get("id"):
            add_line("Identyfikator", rec.get("id"))
        add_line("Rola", rec.get("role"))
        add_line("Wychodząca", rec.get("outgoing"))

        if extra.get("content_raw"):
            add_line("Zawartość surowa", str(extra.get("content_raw")))

        if usage:
            usage_pretty = (
                f"  Tokeny promptu: {usage.get('prompt_tokens', 0)}\n"
                f"  Tokeny odpowiedzi: {usage.get('completion_tokens', 0)}\n"
                f"  Suma tokenów: {usage.get('total_tokens', 0)}"
            )
            add_line("Zużycie tokenów", usage_pretty)

        if reasoning:
            add_line("Uzasadnienie modelu", reasoning)

    def _compute_wraplength(self):
        try:
            w = self.canvas.winfo_width()
            if w and w > 20:
                pad = 40
                usable = max(0, w - pad)
                return max(MIN_BUBBLE, int(usable * BUBBLE_RATIO))
        except Exception:
            pass
        return max(MIN_BUBBLE, int(WINDOW_W * BUBBLE_RATIO))

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
                self._update_wraps(w)
                self.canvas.itemconfig(self.msgs_window, width=w)
        except Exception:
            pass

    def _show_internal_message(self, text: str):
        try:
            self.store.append_message("bot", text, outgoing=False, extra={"internal": True})
        except Exception:
            pass
        self.refresh_from_store()