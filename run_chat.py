# run_chat.py
import tkinter as tk
from ui.chat_store import ChatStore
from ui.chat_ui import ChatUI
from logic.chat_logic import ChatLogic

def main():
    # inicjalizacja logiki (jeżeli wymaga read_env / init_client)
    chat_logic = ChatLogic()
    try:
        if hasattr(chat_logic, "read_env"):
            chat_logic.read_env()
        if hasattr(chat_logic, "init_client"):
            chat_logic.init_client()
    except Exception as e:
        print("Warn: nie udało się zainicjalizować ChatLogic:", e)

    # store: czyścimy temp.json przy starcie
    store = ChatStore(clear_on_start=True)

    root = tk.Tk()
    app = ChatUI(root=root, chat_logic=chat_logic, store=store)
    root.after(120, lambda: app._deferred_update_wraps())
    root.mainloop()

if __name__ == "__main__":
    main()
