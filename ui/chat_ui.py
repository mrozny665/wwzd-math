import time
from datetime import datetime
import flet as ft
import threading
import json
import os
# Importy Twoich klas
from ui.chat_store import ChatStore
from logic.chat_logic import ChatLogic

# Stałe kolorystyczne
BG_MAIN = "#28282A"
CARD_BG = "#3D3D40"
TEXT_COLOR = "#C3C3C5"
TEXT_COLOR_FADED = "#9C9C9F"
BG_HIDDEN_PANEL = "#222224"
ACCENT = "#849FF5"


class ChatUI:
    def __init__(self, page: ft.Page, chat_logic: ChatLogic, store: ChatStore):
        self.page = page
        self.chat_logic = chat_logic
        self.store = store

        # Konfiguracja strony
        self.page.bgcolor = BG_MAIN
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.padding = 0

        # Kontener na wiadomości
        self.chat_view = ft.ListView(
            expand=True,
            spacing=15,
            padding=20,
            auto_scroll=True
        )

        # Pole tekstowe
        self.input_field = ft.TextField(
            hint_text="Napisz wiadomość...",
            fill_color=CARD_BG,
            color="white",
            border_radius=15,
            border_color=ft.Colors.TRANSPARENT,
            expand=True,
            multiline=True,
            min_lines=1,
            max_lines=5,
            on_submit=lambda _: self._on_send(),
        )

        self._build_layout()
        self.refresh_from_store()

    def _build_layout(self):
        # Nagłówek
        header = ft.Container(
            content=ft.Text("ROZMOWA", size=24, weight="bold", color="white"),
            padding=ft.padding.only(left=25, top=15, bottom=15),
            bgcolor=BG_MAIN,
        )

        # Pasek wysyłania
        send_bar = ft.Container(
            content=ft.Row([
                self.input_field,
                ft.IconButton(
                    icon=ft.Icons.SEND_ROUNDED,
                    icon_color=ACCENT,
                    icon_size=30,
                    on_click=lambda _: self._on_send()
                )
            ], tight=True),
            padding=20,
        )

        # Dodanie wszystkiego do strony
        self.page.add(
            header,
            ft.Divider(height=1, color=CARD_BG),
            self.chat_view,
            send_bar
        )

    def _create_thought_block(self, thought_text: str):
        if not thought_text:
            return ft.Container()

        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.AUTO_AWESOME, size=15, color=ACCENT),
                    ft.Text("Działania:", size=11, weight=ft.FontWeight.BOLD, color=ACCENT),
                ]),
                ft.Text(thought_text, size=11, italic=True, color=TEXT_COLOR_FADED),
            ], spacing=5),
            bgcolor=ft.Colors.with_opacity(0.05, ACCENT),
            padding=12,
            border_radius=10,
            border=ft.border.all(1, ft.Colors.with_opacity(0.1, ACCENT)),
            margin=ft.margin.only(bottom=10)
        )

    def _create_bubble(self, role, text, extra, full_rec):
        is_user = role == "user"

        # Pobieranie pola 'thought' bezpośrednio z rekordu (zgodnie z nowym ChatStore)
        thought_data = full_rec.get("thought")

        # 1. Pobieranie surowych danych z JSONa do statystyk
        raw_data = extra.get("raw_json", {})

        # WYCIĄGANIE WYJAŚNIENIA (Reasoning) z JSONa (jako backup dla starszych logów)
        choices = raw_data.get("choices", [{}])
        first_choice = choices[0] if choices else {}
        msg_obj = first_choice.get("message", {})
        explanation = msg_obj.get("reasoning") or thought_data or "Brak dodatkowego wyjaśnienia"

        # STATYSTYKI TOKENÓW
        usage = raw_data.get("usage", {})
        p_tokens = usage.get("prompt_tokens", 0)
        c_tokens = usage.get("completion_tokens", 0)
        t_tokens = usage.get("total_tokens", 0)

        # CZAS I MODEL
        model_name = raw_data.get("model", "Nieznany")
        gen_time = raw_data.get("time", 0)

        # Formatowanie godziny wysłania
        ts_raw = full_rec.get("timestamp", "")
        try:
            timestamp = ts_raw.split("T")[1].split(".")[0] if "T" in ts_raw else ts_raw
        except:
            timestamp = datetime.now().strftime("%H:%M:%S")

        # 2. Budowa listy kontrolek (dodajemy 'thought' na początku treści bota)
        content_controls = []

        if not is_user and thought_data:
            content_controls.append(self._create_thought_block(thought_data))

        # Treść Markdown
        md_content = ft.Markdown(
            text,
            selectable=True,
            extension_set=ft.MarkdownExtensionSet.GITHUB_FLAVORED,
            code_theme="atom-one-dark",
            md_style_sheet=ft.MarkdownStyleSheet(
                blockquote_text_style=ft.TextStyle(color=TEXT_COLOR_FADED, italic=True),
                blockquote_padding=ft.padding.all(10),
                blockquote_decoration=ft.BoxDecoration(
                    bgcolor=BG_HIDDEN_PANEL,
                    border=ft.border.only(left=ft.BorderSide(3, ACCENT)),
                    border_radius=ft.border_radius.only(top_right=5, bottom_right=5),
                ),
            ),
        )
        content_controls.append(md_content)

        # 3. Obrazek (wykres)
        img_path = extra.get("image_path")
        if img_path:
            full_img_path = os.path.abspath(img_path)
            if os.path.exists(full_img_path):
                content_controls.append(
                    ft.Image(src=full_img_path, border_radius=10, width=500, fit="contain")
                )

        content = ft.Column(content_controls, tight=True, spacing=10)

        # 4. Panele INFO i JSON (zaktualizowane o reasoning)
        info_grid = ft.Column([
            ft.Text("STATYSTYKI SYSTEMOWE", size=12, weight=ft.FontWeight.BOLD, color=ACCENT),
            ft.Row([
                ft.Icon(ft.Icons.SPEED, size=16, color=TEXT_COLOR_FADED),
                ft.Text(f"Model: {model_name} | Czas: {gen_time:.2f}s", size=12, color=TEXT_COLOR),
            ]),
            ft.Row([
                ft.Icon(ft.Icons.TOKEN, size=16, color=TEXT_COLOR_FADED),
                ft.Text(f"Tokeny: {t_tokens} (In: {p_tokens} / Out: {c_tokens})", size=12, color=TEXT_COLOR),
            ]),
            ft.Row([
                ft.Icon(ft.Icons.SCHEDULE, size=16, color=TEXT_COLOR_FADED),
                ft.Text(f"Wysłano: {timestamp}", size=12, color=TEXT_COLOR),
            ]),
            ft.Divider(height=1, color=CARD_BG),
            ft.Text("LOGIKA (REASONING):", size=11, weight=ft.FontWeight.BOLD, color=TEXT_COLOR_FADED),
            ft.Text(explanation, size=11, italic=True, color=TEXT_COLOR_FADED),
        ], spacing=8)

        info_panel = ft.Container(
            content=info_grid, bgcolor=BG_HIDDEN_PANEL, padding=15,
            border_radius=8, visible=False, border=ft.border.all(1, CARD_BG)
        )

        json_panel = ft.Container(
            content=ft.Text(json.dumps(full_rec, indent=2, ensure_ascii=False),
                            size=11, font_family="monospace", color=TEXT_COLOR_FADED),
            bgcolor=BG_HIDDEN_PANEL, padding=10, border_radius=5, visible=False
        )

        # 5. Funkcje przycisków
        def toggle_info(e):
            info_panel.visible = not info_panel.visible
            json_panel.visible = False
            self.page.update()

        def toggle_json(e):
            json_panel.visible = not json_panel.visible
            info_panel.visible = False
            self.page.update()

        if not is_user:
            content.controls.append(
                ft.Row([
                    ft.TextButton("INFORMACJE", icon=ft.Icons.INFO_OUTLINE, on_click=toggle_info, icon_color=ACCENT),
                    ft.TextButton("JSON", icon=ft.Icons.CODE, on_click=toggle_json, icon_color=TEXT_COLOR_FADED),
                ], spacing=10)
            )
            content.controls.append(info_panel)
            content.controls.append(json_panel)

        return ft.Row(
            [ft.Container(
                content=content,
                bgcolor=CARD_BG if is_user else ft.Colors.TRANSPARENT,
                padding=15, border_radius=15, width=600 if is_user else 800,
            )],
            alignment=ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START
        )

    def refresh_from_store(self):
        self.chat_view.controls.clear()
        for rec in self.store.load_all():
            self.chat_view.controls.append(
                self._create_bubble(rec.get("role"), rec.get("text"), rec.get("extra", {}), rec)
            )
        # Odświeżamy widok kontrolek
        self.chat_view.update()

        if self.page:
            self.page.update()
            self.page.run_task(self.chat_view.scroll_to, offset=-1, duration=0)

    def _on_send(self):

        val = self.input_field.value.strip()
        if not val: return

        self.store.append_message("user", val, outgoing=True)
        self.input_field.value = ""
        self.refresh_from_store()

        threading.Thread(target=self._logic_worker, args=(val,), daemon=True).start()

        """
        KOD DO TESTOWANAI NA SUCHO
        user_text = self.input_field.value.strip()
        if not user_text:
            return

        self.store.append_message(role="user", text=user_text, outgoing=True)
        self.input_field.value = ""
        self.refresh_from_store()

        def simulate_bot():
            time.sleep(1)  # Udajemy, że model myśli

            # TEST 1: Standardowa odpowiedź z procesem myślowym
            self.store.append_message(
                role="bot",
                text="Wynik Twojego równania to x = 5.",
                thought="Użytkownik podał równanie liniowe. Wykorzystuję EquationSolver. Normalizuję wyrażenie... Rozwiązuję: 2x - 10 = 0.",
                extra={"raw_json": {"model": "Model-Testowy", "time": 0.5}}
            )
            self.refresh_from_store()

            time.sleep(1.5)

            # TEST 2: Odpowiedź z wykresem i opisem działań pośrednich
            self.store.append_message(
                role="bot",
                text="Oto wykres funkcji sinus.",
                thought="Przekierowuję dane do PlotLogic. Generuję punkty dla zakresu -10 do 10. Zapisuję obraz do ui/images/plot_test.png.",
                extra={
                    "image_path": "ui/images/plot_13a77d7310af4678993e946472aac9c3.png",
                    "raw_json": {"usage": {"total_tokens": 150}, "model": "Plot-Master"}
                }
            )
            self.refresh_from_store()

        # Uruchamiamy symulację w osobnym wątku, żeby nie zamrozić UI
        threading.Thread(target=simulate_bot, daemon=True).start()
        """

    def _logic_worker(self, user_input):
        msg_id = None
        try:
            logic = self.chat_logic

            # KROK 1: NATYCHMIAST dodajemy dymek statusu
            # To pojawi się w UI w momencie, gdy w konsoli zobaczysz start logiki
            temp_rec = self.store.append_message(
                role="bot",
                text="Oczekiwanie na odpowiedź...",
                thought="Łączenie z API i analiza zapytania..."
            )
            msg_id = temp_rec["id"]
            self.refresh_from_store()  # Wymuszamy odświeżenie UI, by pokazać ten dymek

            # KROK 2: Teraz wykonujemy ciężką pracę (tu pojawia się DEBUG w konsoli)
            if hasattr(logic, "call_method"):
                logic.call_method(user_input)

            # (Opcjonalnie) Możesz tu dodać aktualizację statusu po odebraniu API
            self.store.update_message(msg_id, thought="Odebrano dane, przetwarzam wynik...")
            self.refresh_from_store()

            if hasattr(logic, "read_message"): logic.read_message()
            if hasattr(logic, "parse_json"): logic.parse_json()

            res = logic.handle_response() if hasattr(logic, "handle_response") else None

            # KROK 3: WYCIĄGANIE DANYCH KOŃCOWYCH
            txt = getattr(res, "message", "Brak odpowiedzi")
            img = getattr(res, "image_path", None)
            raw_json = getattr(res, "raw_json", {})

            # Pobieramy prawdziwe myślenie z API (reasoning)
            thought_final = None
            try:
                thought_final = raw_json['choices'][0]['message'].get('reasoning')
            except:
                pass

            if not thought_final:
                thought_final = "Obliczenia zakończone pomyślnie."

            extra = {"raw_json": raw_json}
            if img: extra["image_path"] = img

            # KROK 4: AKTUALIZACJA - zamieniamy "Oczekiwanie..." na gotowy tekst
            self.store.update_message(
                message_id=msg_id,
                text=str(txt),
                thought=thought_final,
                extra=extra
            )
            self.refresh_from_store()

        except Exception as e:
            if msg_id:
                self.store.update_message(msg_id, text=f"Błąd: {e}", thought="Wystąpił problem.")
            else:
                self.store.append_message("bot", f"Błąd systemowy: {e}", False, {"internal": True})
            self.refresh_from_store()