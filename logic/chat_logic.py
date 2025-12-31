# ChatLogic.py
import openai
from environs import Env
import json
import re
from typing import Any, Optional, Callable
from logic.calculus_engine import CalculusEngine
from logic.equation_solver import EquationSolver
from logic.plot_logic import PlotLogic
import ast

class ChatResult:
    """Reprezentuje wynik jednej interakcji z modelem."""
    def __init__(self, message, raw_json=None, content=None, action=None,
                 expression=None, result=None, error=None, success=True, image_path=None):
        self.message = message
        self.raw_json = raw_json
        self.content = content
        self.action = action
        self.expression = expression
        self.result = result
        self.error = error
        self.success = success
        self.image_path = image_path

    def __repr__(self):
        return f"<ChatResult success={self.success} action={self.action} img={self.image_path}>"


class ChatLogic:
    def __init__(self, store=None):
        self.store = store
        self.message: Optional[Any] = None
        self.data: Optional[Any] = None
        self.response: Optional[Any] = None  # obiekt/str zwrócony przez API po wywołaniu
        self.content: Optional[str] = None    # wypakowany tekst (string) z odpowiedzi
        self.client = None
        self.env = None
        # domyślny model można nadpisać env albo setterem
        self.default_model: str = "or-gpt-oss-120b"
        # czy próbować streamować odpowiedź (jeśli provider wspiera)
        self.enable_streaming: bool = True
        self.history = []
        self.last_raw_completion = None
        self._system_added = False
        # callback: gdzie UI/logika może podpiąć aktualizacje statusu
        self.on_progress: Optional[Callable[[str], None]] = None
        self.calculus_engine = CalculusEngine()
        self.equation_solver = EquationSolver()
        self.plot_logic = PlotLogic(store=self.store)

    def read_env(self):
        self.env = Env()
        self.env.read_env()
        try:
            self.default_model = self.env.str("OPENAI_MODEL", self.default_model)
        except Exception:
            pass

    def set_default_model(self, model: str) -> None:
        """Ustawia domyślny model używany do wywołań API."""
        if isinstance(model, str) and model.strip():
            self.default_model = model.strip()

    def safe_eval_math(self, expression: str, variables=None):
        try:
            expr = self.equation_solver._normalize_expression(expression)
            parsed = ast.parse(expr, mode="eval")
            val = self.plot_logic._eval_ast(parsed, variables)
            return {"result": val}
        except Exception as e:
            return {"error": str(e)}

    def set_streaming(self, enabled: bool) -> None:
        self.enable_streaming = bool(enabled)

    def _coerce_action_input(self, container: Any) -> dict:
        """Zwraca dict z action_input lub fallbackiem na klucz expression."""
        if not isinstance(container, dict):
            return {}
        ai = container.get("action_input")
        if isinstance(ai, dict):
            return ai
        if isinstance(ai, (str, int, float)):
            return {"expression": str(ai)}
        fallback_keys = (
            "expression", "expr", "equation",
            "variable", "var", "order", "nth",
            "at", "point", "value", "evaluate_at", "bounds", "limits",
            "lower", "upper", "from", "to", "a", "b", "min", "max"
        )
        fallback = {}
        for key in fallback_keys:
            if key in container and container[key] is not None:
                fallback[key] = container[key]
        return fallback

    def _handle_math_action(self, expr: str):
        expr_display = "" if expr is None else str(expr)
        message = f"📞 Model wykrył działanie: {expr_display}\n"
        math_res = self.safe_eval_math(expr)
        if "result" in math_res:
            result_value = math_res["result"]
            message += f"🧮 Wynik obliczenia: {expr_display} = {result_value}"
            return message, result_value, None, True
        error_value = math_res.get("error", "Nieznany błąd")
        message += f"⚠️ Błąd podczas obliczania: {error_value}"
        return message, None, error_value, False

    def _handle_derivative_action(self, payload: dict, expr: str):
        # znormalizuj expression w payloadzie (np. 2x -> 2*x)
        if isinstance(payload, dict) and payload.get("expression"):
            payload = dict(payload)
            payload["expression"] = self.equation_solver._normalize_expression(str(payload["expression"]))
            expr = payload["expression"]
        expr_display = "" if expr is None else str(expr)
        message = f"📞 Model poprosił o pochodną: {expr_display}\n"
        diff_res = self.calculus_engine.differentiate(payload)
        if "error" in diff_res:
            error_value = diff_res["error"]
            message += f"⚠️ {error_value}"
            return message, None, error_value, False
        derivative_txt = diff_res.get("derivative")
        message += f"🧮 Wynik obliczenia: {derivative_txt}"
        if diff_res.get("value_at") is not None and diff_res.get("at") is not None:
            message += f"\n📏 W punkcie {diff_res['at']}: {diff_res['value_at']}"
        if diff_res.get("value_error"):
            message += f"\n⚠️ {diff_res['value_error']}"
        return message, diff_res, None, True

    def _handle_integral_action(self, payload: dict, expr: str):
        # znormalizuj expression w payloadzie (np. 2x -> 2*x)
        if isinstance(payload, dict) and payload.get("expression"):
            payload = dict(payload)
            payload["expression"] = self.equation_solver._normalize_expression(str(payload["expression"]))
            expr = payload["expression"]
        expr_display = "" if expr is None else str(expr)
        message = f"📞 Model poprosił o całkę: {expr_display}\n"
        integral_res = self.calculus_engine.integrate(payload)
        if "error" in integral_res:
            error_value = integral_res["error"]
            message += f"⚠️ {error_value}"
            return message, None, error_value, False
        variable = integral_res.get("variable", "x")
        integral_result = integral_res.get("integral_result")
        if integral_res.get("type") == "definite" and integral_res.get("value") is not None:
            lower = integral_res.get("lower")
            upper = integral_res.get("upper")
            value = integral_res.get("value")
            message += (
                f"∫[{lower}, {upper}] {expr_display} d{variable} = {value}\n"
                f"Wynik całki: {integral_result}"
            )
        else:
            message += f"🧮 Wynik całki: ∫ {expr_display} d{variable} = {integral_result} + C"
        if integral_res.get("value_error"):
            message += f"\n⚠️ {integral_res['value_error']}"
        return message, integral_res, None, True

    def _handle_default_response(self):
        if isinstance(self.content, str):
            return self.content
        if isinstance(self.content, (dict, list)):
            try:
                return json.dumps(self.content, ensure_ascii=False)
            except Exception:
                return str(self.content)
        try:
            return str(self.response)
        except Exception:
            return "(brak odpowiedzi)"

    def _emit_progress(self, thought: str) -> None:
        """Emituje status/thought do UI (jeśli podpięto callback)."""
        cb = getattr(self, "on_progress", None)
        if cb and callable(cb):
            try:
                cb(thought)
            except Exception:
                # postęp nie może zabić logiki
                pass

    # ---- Inicjalizacja klienta ----
    def init_client(self):
        self.client = openai.OpenAI(
            api_key=self.env.str("OPENAI_API_KEY"),
            base_url="https://services.clarin-pl.eu/api/v1/oapi/"
        )

    # ---- wysyłka zapytania do modelu ----
    def call_method(self, user_message: str, *, use_store_history: bool = True, model: Optional[str] = None, stream: Optional[bool] = None):
        """Wywołuje model.

        - `model`: pozwala użyć innego modelu dla pojedynczego wywołania
        - `stream`: jeśli True, próbuje streamować odpowiedź i emitować na bieżąco fragmenty
        - `use_store_history`: jeśli True, buduje kontekst z historii czatu
        """
        self._emit_progress("Buduję historię rozmowy...")

        if use_store_history:
            self.history = self.build_messages_from_store()
            # W call_method dopisujemy jeszcze ostatnią wiadomość użytkownika,
            # bo w UI jest już zapisana, ale nie chcemy ryzykować, że wątek wyścigu ją pominie.
            self.history.append({"role": "user", "content": user_message})
            self._system_added = True
        else:
            if not self._system_added:
                self.history.append({"role": "system", "content": self._system_prompt()})
                self._system_added = True
            self.history.append({"role": "user", "content": user_message})

        chosen_model = (model or self.default_model).strip()
        use_stream = self.enable_streaming if stream is None else bool(stream)

        try:
            if use_stream:
                self._emit_progress(f"Wysyłam zapytanie do API (stream, model={chosen_model})...")
                collected_text_parts: list[str] = []

                try:
                    stream_resp = self.client.chat.completions.create(
                        model=chosen_model,
                        messages=self.history,
                        temperature=0,
                        stream=True,
                    )

                    # Stream zwraca iterowalne eventy. Wydobywamy delta.content i emitujemy do UI.
                    for event in stream_resp:
                        try:
                            choice0 = getattr(event, "choices", [None])[0]
                            delta = getattr(choice0, "delta", None) if choice0 is not None else None
                            piece = getattr(delta, "content", None) if delta is not None else None
                            if isinstance(piece, str) and piece:
                                collected_text_parts.append(piece)
                                # pokazujemy 'na żywo' w polu thought
                                self._emit_progress("".join(collected_text_parts)[-1500:])
                        except Exception:
                            continue

                    final_text = "".join(collected_text_parts).strip()
                    # Ustawiamy minimalny obiekt odpowiedzi w formacie zgodnym z resztą pipeline.
                    self.response = {
                        "choices": [{"message": {"role": "assistant", "content": final_text}}],
                        "model": chosen_model,
                    }
                    self.last_raw_completion = self.response
                    self._emit_progress("Odebrałem odpowiedź (stream) — kończę...")
                    return

                except Exception as stream_err:
                    # fallback do non-stream
                    self._emit_progress(f"Streaming niedostępny ({stream_err}). Przechodzę na tryb zwykły...")

            # fallback: normalny request
            self._emit_progress(f"Wysyłam zapytanie do API (model={chosen_model})...")
            self.response = self.client.chat.completions.create(
                model=chosen_model,
                messages=self.history,
                temperature=0
            )
            self.last_raw_completion = self.response

            self._emit_progress("Odebrałem odpowiedź, aktualizuję historię...")
            try:
                resp_msg = self.response.choices[0].message
                content = getattr(resp_msg, "content", None)
                if isinstance(content, str):
                    self.history.append({"role": "assistant", "content": content})
            except Exception:
                pass

            print("DEBUG: API response received (saved to last_raw_completion).")
        except Exception as e:
            print("ERROR calling model:", e)
            self.response = None
            self.last_raw_completion = None

    # ---- odczytanie treści wiadomości (tekst) ----
    def read_message(self):
        self._emit_progress("Parsuję odpowiedź (read_message)...")
        """
        Wydobywa message i content z self.response (jeśli możliwe),
        w bezpieczny sposób ustawiając self.message i self.content.
        """
        self.message = None
        self.content = None
        self.data = None

        if not self.response:
            return

        try:
            maybe_choice = None
            try:
                maybe_choice = self.response.choices[0]
            except Exception:
                # spróbuj strukturę dict-like
                if isinstance(self.response, dict):
                    chs = self.response.get("choices")
                    if isinstance(chs, list) and len(chs) > 0:
                        maybe_choice = chs[0]

            if maybe_choice is None:
                self.message = getattr(self.response, "message", None) or self.response
            else:
                self.message = getattr(maybe_choice, "message", None) or maybe_choice.get("message", None)

            if isinstance(self.message, dict):
                cont = self.message.get("content") if "content" in self.message else None
                self.content = cont.strip() if isinstance(cont, str) else cont
            else:
                cont = getattr(self.message, "content", None) if self.message is not None else None
                if isinstance(cont, str):
                    self.content = cont.strip()
                else:
                    self.content = cont

        except Exception as e:
            print("WARN read_message failed:", e)
            self.message = None
            self.content = None

    # ---- parsowanie content jako JSON (jeśli model zwrócił JSON) ----
    def _extract_json_fragment(self, s: str) -> Optional[str]:
        """
        Szuka pierwszego fragmentu tekstu, który wygląda jak JSON ({...} lub [...]).
        Zwraca substring lub None.
        """
        if not isinstance(s, str):
            return None
        s_strip = s.strip()
        if (s_strip.startswith("{") and s_strip.endswith("}")) or (s_strip.startswith("[") and s_strip.endswith("]")):
            return s_strip
        stack = []
        start = None
        for i, ch in enumerate(s):
            if ch == "{" or ch == "[":
                if start is None:
                    start = i
                stack.append(ch)
            elif ch == "}" or ch == "]":
                if stack:
                    stack.pop()
                    if not stack and start is not None:
                        return s[start:i+1]
        return None

    def parse_json(self):
        self._emit_progress("Sprawdzam czy odpowiedź to JSON (parse_json)...")
        """
        Próbuje sparsować self.content do self.data:
          - jeśli content to dict -> ustaw self.data = content
          - jeśli content to string zawierający JSON -> parsuj
          - jako fallback: spróbuj zamienić pojedyncze apostrofy na cudzysłowy
        """
        self.data = None
        cont = self.content
        if cont is None:
            return

        if isinstance(cont, (dict, list)):
            self.data = cont
            return

        if not isinstance(cont, str):
            # nieznany format
            return

        frag = self._extract_json_fragment(cont)
        if frag:
            try:
                self.data = json.loads(frag)
                return
            except Exception:
                pass

        try:
            self.data = json.loads(cont)
            return
        except json.JSONDecodeError:
            pass

        if re.match(r"^\{'.*'\}$", cont.strip()):
            try:
                fixed = cont.replace("'", '"')
                self.data = json.loads(fixed)
                return
            except Exception:
                pass

        self.data = None

    # ---- obsługa i logika odpowiedzi ----
    def handle_response(self) -> ChatResult:
        self._emit_progress("Wykonuję akcję / składam odpowiedź (handle_response)...")
        """Centralna obsługa odpowiedzi i komend JSON od modelu."""
        message_text = ""
        action = None
        expr = None
        result_value = None
        error_value = None
        success = True
        image_path = None

        data_dict = self.data if isinstance(self.data, dict) else None

        # Dispatcher akcji JSON
        if data_dict and isinstance(data_dict.get("action"), str):
            raw_action = data_dict.get("action")
            # normalizacja tylko na potrzeby porównań
            normalized_action = raw_action.lower().replace("_", "")
            ai = self._coerce_action_input(data_dict)
            action = raw_action

            # Wyciągnięcie podstawowych pól
            expr = None
            if isinstance(ai, dict):
                expr = ai.get("expression") or ai.get("equation")

            # --- OBLICZENIA ---
            if normalized_action in ("evaluatemath", "evaluate"):
                expr_str = "" if expr is None else str(expr)
                msg, result_value, error_value, success = self._handle_math_action(expr_str)
                expr = expr_str
                message_text += msg

            # --- POCHODNA ---
            elif normalized_action in ("differentiate", "derivative"):
                expr_str = "" if expr is None else str(expr)
                msg, result_value, error_value, success = self._handle_derivative_action(ai, expr_str)
                expr = expr_str
                message_text += msg

            # --- CAŁKA ---
            elif normalized_action in ("integrate", "integral"):
                expr_str = "" if expr is None else str(expr)
                msg, result_value, error_value, success = self._handle_integral_action(ai, expr_str)
                expr = expr_str
                message_text += msg

            # --- RÓWNANIE ---
            elif normalized_action == "solveequation":
                equation = None
                if isinstance(ai, dict):
                    equation = ai.get("equation") or ai.get("expression")
                if equation is None:
                    equation = data_dict.get("equation") or data_dict.get("expression") or ""
                equation_str = str(equation)
                expr = equation_str
                message_text += f"📞 Model przesłał równanie: {equation_str}\n"
                sol = self.equation_solver.solve_equation(equation_str, var_name="x")
                if sol.get("success"):
                    sval = sol.get("solution")
                    result_value = sval
                    message_text += f"🔎 Rozwiązanie: {sval}"
                    success = True
                else:
                    # --- NOWE: wyłapywanie błędów i próba autoratywnego retry/ask_user ---
                    error_value = sol.get("error")

                    # retry: czasem wystarczy poprawić zapis (np. 'sin x' -> 'sin(x)', itp.)
                    def _retry_solve(patched_input: Optional[str] = None):
                        eq_try = patched_input.strip() if isinstance(patched_input, str) and patched_input.strip() else equation_str
                        sol2 = self.equation_solver.solve_equation(eq_try, var_name="x")
                        if sol2.get("success"):
                            return {"equation": eq_try, "solution": sol2.get("solution")}
                        raise ValueError(sol2.get("error") or "Nieznany błąd")

                    flow = self.handle_calculation_error_with_retry(
                        error_value,
                        stage="solve_equation",
                        retry_callable=_retry_solve,
                        extra_context={
                            "equation": equation_str,
                            "note": "Jeśli równanie zawiera funkcje typu sin/cos/log, system może tego nie obsługiwać.",
                        },
                    )

                    if flow.get("status") == "ok":
                        result_payload = flow.get("result") or {}
                        result_value = result_payload.get("solution")
                        fixed_eq = result_payload.get("equation", equation_str)
                        if fixed_eq != equation_str:
                            message_text += f"✅ Poprawiłem zapis i spróbowałem ponownie: {fixed_eq}\n"
                        message_text += f"🔎 Rozwiązanie: {result_value}"
                        success = True
                    elif flow.get("status") == "unsupported":
                        message_text += f"⚠️ {flow.get('unsupported_message') or error_value}"
                        success = False
                    else:
                        # ask_user / failed
                        q = flow.get("user_question")
                        if q:
                            message_text += f"⚠️ Nie mogę tego policzyć automatycznie. {q}"
                        else:
                            message_text += f"⚠️ Błąd rozwiązania: {error_value}"
                        success = False

            # --- WYKRES FUNKCJI ---
            elif normalized_action == "plotfunction":
                # parametry zakresu X
                x_min = -10.0
                x_max = 10.0
                if isinstance(ai, dict):
                    expr = ai.get("expression", expr)
                    try:
                        if "min" in ai:
                            x_min = float(ai.get("min"))
                        if "max" in ai:
                            x_max = float(ai.get("max"))
                    except Exception:
                        x_min, x_max = -10.0, 10.0

                if expr is None:
                    expr = data_dict.get("expression", "x")

                if expr:
                    expr_str = str(expr)
                    expr = expr_str
                    message_text += f"📉 Generuję wykres funkcji: f(x) = {expr_str}"
                    path = self.plot_logic._generate_plot_image(expr_str, x_min, x_max)
                    if path:
                        image_path = path
                        message_text += "\n(Wykres wygenerowany)"
                    else:
                        message_text += "\n⚠️ Błąd generowania wykresu."
                        success = False

            # Jeśli akcja była rozpoznana, ale nie ustawiono wiadomości (edge case)
            if not message_text and action is not None:
                message_text = self._handle_default_response()

        else:
            # Brak akcji JSON – zwykła odpowiedź tekstowa
            message_text = self._handle_default_response()

        raw_for_store = None
        if self.last_raw_completion is not None:
            raw_for_store = self.last_raw_completion
        elif self.data is not None:
            raw_for_store = self.data
        else:
            raw_for_store = self.response

        cr = ChatResult(
            message=message_text,
            raw_json=raw_for_store,
            content=self.content,
            action=action,
            expression=expr,
            result=result_value,
            error=error_value,
            success=success,
            image_path=image_path
        )
        return cr

    def _system_prompt(self) -> str:
        return (
            "Jesteś inteligentnym asystentem konwersacyjnym. "
            "Kiedy użytkownik prosi o obliczenia, równania, pochodne, całki lub wykresy, NIE odpowiadaj opisowo, "
            "tylko zwracaj wyłącznie JSON w jednym z poniższych formatów.\n\n"
            "FORMATY KOMEND SPECJALNYCH (używaj ich tylko do zadań matematycznych):\n"
            "1. Obliczenia (np. 2+2):\n"
            "   {\\\"action\\\": \\\"evaluate_math\\\", \\\"action_input\\\": {\\\"expression\\\": \\\"...\\\"}}\n\n"
            "2. Rozwiązanie równania (np. 2x^2+3x-5=0):\n"
            "   {\\\"action\\\": \\\"solve_equation\\\", \\\"action_input\\\": {\\\"equation\\\": \\\"...\\\"}}\n\n"
            "3. Pochodna (z opcjonalnym obliczeniem w punkcie):\n"
            "   {\\\"action\\\": \\\"differentiate\\\", \\\"action_input\\\": {"
            "\\\"expression\\\": \\\"...\\\", \\\"variable\\\": \\\"x\\\", \\\"order\\\": 1, \\\"at\\\": null}}\n\n"
            "4. Całka (nieoznaczona lub oznaczona):\n"
            "   {\\\"action\\\": \\\"integrate\\\", \\\"action_input\\\": {"
            "\\\"expression\\\": \\\"...\\\", \\\"variable\\\": \\\"x\\\", \\\"bounds\\\": [dolna, górna]}}\n\n"
            "5. Wykres funkcji (np. 'narysuj x^2'):\n"
            "   {\\\"action\\\": \\\"plot_function\\\", \\\"action_input\\\": {"
            "\\\"expression\\\": \\\"...\\\", \\\"min\\\": -10, \\\"max\\\": 10}}\n\n"
            "Jeśli pytanie użytkownika NIE wymaga powyższych działań, odpowiadaj normalnie po polsku, bez JSON."
        )

    def build_messages_from_store(self) -> list[dict[str, str]]:
        """Buduje listę messages (system+historia) na podstawie aktualnego pliku czatu.

        Pomija rysunki/obrazy. Dodatkowo stara się zachować istotny kontekst obliczeń
        (np. wynik), nawet jeśli UI zapisuje go jako metadane.
        """
        messages: list[dict[str, str]] = [{"role": "system", "content": self._system_prompt()}]

        if not self.store:
            return messages

        try:
            records = self.store.load_all()
        except Exception:
            records = []

        for rec in records:
            role = rec.get("role")
            text = rec.get("text")
            if not isinstance(text, str) or not text.strip():
                continue

            if role == "bot" and text.strip() == "...":
                continue

            extra = rec.get("extra") if isinstance(rec.get("extra"), dict) else {}
            if extra.get("internal") is True:
                continue

            api_role = "assistant" if role in ("bot", "assistant") else "user"

            content = text

            try:
                maybe_action = extra.get("action") or extra.get("action_name")
                maybe_result = extra.get("result")
                if api_role == "assistant" and (maybe_action or maybe_result) and isinstance(content, str):
                    # jeśli content nie zawiera jeszcze wyniku, dopnijmy
                    if maybe_result is not None and "Wynik" not in content and "wynik" not in content:
                        content = f"{content}\n\n[Wynik]\n{maybe_result}"
            except Exception:
                pass

            messages.append({"role": api_role, "content": content})

        return messages

    def request_user_clarification(self, topic: str, *, details: Optional[str] = None, model: Optional[str] = None) -> ChatResult:
        """Prosi bota o wygenerowanie pytania do użytkownika (gdy brakuje danych)."""
        prompt = (
            "Potrzebuję, żebyś dopytał użytkownika o brakujące informacje. "
            "Zadaj 1-3 konkretne pytania, krótko i po polsku.\n\n"
            f"Temat: {topic}"
        )
        if details:
            prompt += f"\nSzczegóły: {details}"
        return self.ask_bot(prompt, model=model)

    def ask_bot(self, prompt: str, *, context: Optional[str] = None, model: Optional[str] = None) -> ChatResult:
        """Zadaje pytanie botowi z pełną historią czatu.

        `context` pozwala dopiąć dodatkowy kontekst (np. logi).
        `model` pozwala wskazać inny model dla tego wywołania.
        """
        composed = prompt
        if context:
            composed = f"{prompt}\n\n[Dodatkowy kontekst]\n{context}"

        self.call_method(composed, use_store_history=True, model=model)
        self.read_message()
        self.parse_json()
        return self.handle_response()

    def _retry_or_clarify_policy_prompt(self, *, error_text: str, stage: str, attempt: int, max_attempts: int) -> str:
        """Prompt dla bota: ma zdecydować czy system powinien spróbować ponownie, czy dopytanie użytkownika.

        Kontrakt odpowiedzi: dokładnie JEDEN obiekt JSON, bez markdown i bez komentarzy.

        Uwaga: przy decision=retry bot MOŻE zaproponować lekką poprawkę wejścia w polu patched_input.
        """
        schema = (
            "{\n"
            "  \"decision\": \"retry\" | \"ask_user\" | \"unsupported\",\n"
            "  \"patched_input\": string | null,\n"
            "  \"retry_instruction\": string | null,\n"
            "  \"user_question\": string | null,\n"
            "  \"unsupported_message\": string | null\n"
            "}"
        )

        return (
            "Jesteś kontrolerem przepływu w aplikacji matematycznej. "
            "Dostałeś błąd z obliczeń. Twoim zadaniem jest zdecydować, czy system ma spróbować wykonać obliczenie jeszcze raz (retry), "
            "czy powinien dopytać użytkownika o doprecyzowanie (ask_user), albo czy to działanie jest nieobsługiwane (unsupported).\n\n"
            "ZASADY:\n"
            f"- To jest próba {attempt} z {max_attempts}.\n"
            "- Jeśli błąd wygląda na literówkę / zły format / brak danych od użytkownika -> wybierz ask_user.\n"
            "- Jeśli to wygląda na drobną pomyłkę/format, który da się poprawić po stronie systemu -> wybierz retry.\n"
            "- Jeśli system nie obsługuje takiego typu zadania -> wybierz unsupported.\n"
            f"- Jeśli attempt == {max_attempts}, NIE wybieraj retry (zawsze ask_user albo unsupported).\n\n"
            "FORMAT ODPOWIEDZI (MUSI być dokładnie jeden obiekt JSON):\n"
            f"{schema}\n\n"
            "Zasady pól:\n"
            "- decision: zawsze wymagane\n"
            "- patched_input: tylko gdy decision=retry (w innym przypadku null)\n"
            "- retry_instruction: tylko gdy decision=retry (w innym przypadku null)\n"
            "- user_question: tylko gdy decision=ask_user (w innym przypadku null)\n"
            "- unsupported_message: tylko gdy decision=unsupported (w innym przypadku null)\n\n"
            "Odpowiedz WYŁĄCZNIE JSON (bez komentarzy, bez markdown).\n\n"
            "Ustal priorytety działań w następującej kolejności: 1. retry, 2. ask_user, 3. unsupported.\n\n"
            f"[Etap]\n{stage}\n\n"
            f"[Błąd]\n{error_text}\n"
        )

    def _validate_decision_dict(self, d: dict, *, attempt: int, max_attempts: int) -> dict:
        """Waliduje/normalizuje dict decyzji z bota. Zwraca poprawiony dict lub pusty dict."""
        if not isinstance(d, dict):
            return {}

        decision = str(d.get("decision", "")).strip().lower()
        if decision not in {"retry", "ask_user", "unsupported"}:
            return {}

        # twarda zasada: na ostatniej próbie retry jest zakazane
        if attempt >= max_attempts and decision == "retry":
            decision = "ask_user"

        out = {
            "decision": decision,
            "patched_input": d.get("patched_input"),
            "retry_instruction": d.get("retry_instruction"),
            "user_question": d.get("user_question"),
            "unsupported_message": d.get("unsupported_message"),
        }

        # wyczyść pola niepasujące do decyzji
        if decision != "retry":
            out["patched_input"] = None
            out["retry_instruction"] = None
        if decision != "ask_user":
            out["user_question"] = None
        if decision != "unsupported":
            out["unsupported_message"] = None

        # sanity typów
        if out["patched_input"] is not None and not isinstance(out["patched_input"], str):
            out["patched_input"] = str(out["patched_input"])
        if out["retry_instruction"] is not None and not isinstance(out["retry_instruction"], str):
            out["retry_instruction"] = str(out["retry_instruction"])

        if decision == "ask_user" and (not isinstance(out["user_question"], str) or not out["user_question"].strip()):
            out["user_question"] = None
        if decision == "unsupported" and (not isinstance(out["unsupported_message"], str) or not out["unsupported_message"].strip()):
            out["unsupported_message"] = None
        if decision == "retry" and (not isinstance(out["retry_instruction"], str) or not out["retry_instruction"].strip()):
            out["retry_instruction"] = "Spróbuj ponownie po drobnej normalizacji wejścia."

        return out

    def _extract_decision_json(self, text: Any) -> dict:
        """Bezpiecznie wyciąga JSON-dict z odpowiedzi modelu dla decyzji retry/ask_user/unsupported."""
        if isinstance(text, dict):
            return text
        if not isinstance(text, str):
            return {}

        frag = self._extract_json_fragment(text)
        if not frag:
            frag = text.strip()

        try:
            val = json.loads(frag)
            return val if isinstance(val, dict) else {}
        except Exception:
            return {}

    def handle_calculation_error_with_retry(
        self,
        error: Exception | str,
        *,
        stage: str,
        retry_callable: Callable[[], Any],
        max_attempts: int = 2,
        extra_context: Optional[dict] = None,
        model: Optional[str] = None,
    ) -> dict:
        """Polityka: bot decyduje retry vs dopytanie usera, ale po 2 porażkach zawsze pyta usera albo mówi unsupported.

        Parametry:
        - `retry_callable`: funkcja bez argumentów, która próbuje ponownie wykonać operację i rzuca wyjątek przy błędzie

        Zwraca dict kontraktu:
        {
          "status": "ok"|"ask_user"|"unsupported"|"failed",
          "result": Any | None,
          "user_question": str | None,
          "unsupported_message": str | None,
          "error": str | None,
          "attempts": int
        }
        """
        err_text = str(error)
        ctx_json = ""
        if extra_context:
            try:
                ctx_json = json.dumps(extra_context, ensure_ascii=False, indent=2)
            except Exception:
                ctx_json = str(extra_context)

        last_err = err_text
        for attempt in range(1, max_attempts + 1):
            # 1) zapytaj bota o decyzję
            policy_prompt = self._retry_or_clarify_policy_prompt(
                error_text=last_err + (f"\n\n[Kontekst]\n{ctx_json}" if ctx_json else ""),
                stage=stage,
                attempt=attempt,
                max_attempts=max_attempts,
            )

            decision_res = self.ask_bot(policy_prompt, model=model)
            raw_text = getattr(decision_res, "content", None) or getattr(decision_res, "message", None)
            decision_dict = self._extract_decision_json(raw_text)
            decision_dict = self._validate_decision_dict(decision_dict, attempt=attempt, max_attempts=max_attempts)

            # fallback jeśli model nie zwrócił poprawnego JSON
            if not decision_dict:
                clar = self.request_user_clarification(topic=stage, details=last_err, model=model)
                q = getattr(clar, "message", None) or "Czy możesz doprecyzować dane wejściowe?"
                return {
                    "status": "ask_user",
                    "result": None,
                    "user_question": q,
                    "unsupported_message": None,
                    "error": last_err,
                    "attempts": attempt,
                }

            decision = decision_dict["decision"]

            if decision == "retry":
                patched_input = decision_dict.get("patched_input")
                instr = decision_dict.get("retry_instruction")
                if instr:
                    self._emit_progress(f"Retry: {instr}")

                try:
                    if patched_input is not None:
                        try:
                            result = retry_callable(patched_input)
                        except TypeError:
                            result = retry_callable()
                    else:
                        result = retry_callable()

                    return {
                        "status": "ok",
                        "result": result,
                        "user_question": None,
                        "unsupported_message": None,
                        "error": None,
                        "attempts": attempt,
                    }
                except Exception as e:
                    last_err = str(e)
                    continue

            if decision == "unsupported":
                msg = decision_dict.get("unsupported_message")
                if not msg:
                    msg = "Wygląda na to, że to działanie nie jest obsługiwane przez system. Podaj proszę inne sformułowanie lub prostszy zapis."
                return {
                    "status": "unsupported",
                    "result": None,
                    "user_question": None,
                    "unsupported_message": msg,
                    "error": last_err,
                    "attempts": attempt,
                }

            # ask_user
            q = decision_dict.get("user_question")
            if not q:
                clar = self.request_user_clarification(topic=stage, details=last_err, model=model)
                q = getattr(clar, "message", None) or "Czy możesz doprecyzować dane wejściowe?"

            return {
                "status": "ask_user",
                "result": None,
                "user_question": q,
                "unsupported_message": None,
                "error": last_err,
                "attempts": attempt,
            }

        return {
            "status": "failed",
            "result": None,
            "user_question": None,
            "unsupported_message": None,
            "error": last_err,
            "attempts": max_attempts,
        }

