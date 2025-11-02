import tkinter

from logic.ChatLogic import ChatLogic


class GUI(tkinter.Tk):
    def __init__(self, chat_logic):
        super().__init__()
        self.chat_logic = chat_logic

        self.title("Mathematical extension")
        self.geometry("800x600")
        self.configure(background="#0F1116")

        header = tkinter.Frame(self, bg="#0b5cff", height=56)
        header.pack(fill="x", side="top")
        title = tkinter.Label(header, text="Mathematical extension", bg="#0b5cff", fg="white",
                              font=("Segoe UI", 14, "bold"))
        title.pack(padx=12, pady=12, anchor="w")

        container = tkinter.Frame(self, bg="#212224")
        container.pack(fill="both", expand=True, padx=12, pady=(8, 0))

        self.canvas = tkinter.Canvas(container, bg="#212224", highlightthickness=0)
        self.scrollbar = tkinter.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tkinter.Frame(self.canvas, bg="#2c2d2e")

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # bottom input frame
        bottom = tkinter.Frame(self, bg="#414345", pady=8)
        bottom.pack(fill="x", side="bottom")

        self.input_text = tkinter.Text(bottom, height=3, wrap="word", font=("Segoe UI", 11))
        self.input_text.pack(side="left", fill="x", expand=True, padx=(12, 8), pady=6)
        self.input_text.focus_set()

        send_btn = tkinter.Button(bottom, text="Send",
                                  command=self.on_send, width=10)
        send_btn.pack(side="right", padx=(0, 12), pady=6)

        # Bind Enter to send (Shift+Enter -> newline)
        self.input_text.bind("<Return>")

        # keep track of messages (optional)
        self.messages = []

    def on_send(self):
        text = self.input_text.get("1.0", "end").strip()
        if not text:
            return
        self.add_message('user', text)
        self.chat_logic.call_method(text)
        self.chat_logic.read_message()
        self.chat_logic.parse_json()
        message = self.chat_logic.handle_response()

        self.input_text.delete("1.0", "end")

        self.after(300, lambda: self.add_message('bot', f"{message}"))

    def add_message(self, sender, text):
        # create a bubble-like label
        wrap_length = 440
        pad_x = 8
        pad_y = 6

        row = tkinter.Frame(self.scrollable_frame, bg="#212224")
        row.pack(fill="x", expand=True, pady=(0, pad_y))

        if sender == 'user':
            bubble = tkinter.Label(row, text=text, justify="left",
                                   font=("Segoe UI", 10), bd=0, padx=12, pady=8,
                                   wraplength=wrap_length, bg="#0b93ff", fg="#212224")
            bubble.pack(side="right", anchor="e", padx=(80, pad_x))
        else:
            bubble = tkinter.Label(row, text=text, justify="left",
                                   font=("Segoe UI", 10), bd=0, padx=12, pady=8,
                                   wraplength=wrap_length, bg="#e9eefb", fg="#212224")
            bubble.pack(side="left", anchor="w", padx=(pad_x, 80))

        # after adding, scroll to bottom
        self.update_idletasks()
        self.canvas.yview_moveto(1.0)


if __name__ == '__main__':
    chatLogic = ChatLogic()
    chatLogic.read_env()
    chatLogic.init_client()
    app = GUI(chatLogic)
    app.mainloop()
