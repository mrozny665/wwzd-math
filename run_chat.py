import flet as ft
from ui.chat_store import ChatStore
from ui.chat_ui import ChatUI
from logic.chat_logic import ChatLogic


def main(page: ft.Page):
    store = ChatStore(clear_on_start=True)

    chat_logic = ChatLogic(store=store)

    try:
        if hasattr(chat_logic, "read_env"):
            chat_logic.read_env()
        if hasattr(chat_logic, "init_client"):
            chat_logic.init_client()
    except Exception as e:
        print("Warn: nie udało się zainicjalizować ChatLogic:", e)

    page.title = "WWZD MATH - Flet Chat"
    page.window_width = 1280
    page.window_height = 720

    ChatUI(page=page, chat_logic=chat_logic, store=store)


if __name__ == "__main__":
    ft.run(main, assets_dir="ui")