# ChatLogic.py
import cmath

import openai
from environs import Env
import json
import math
import re
import ast
import operator as op
import os
import uuid
from typing import Any, Optional
from logic.calculus_engine import CalculusEngine
from logic.equation_solver import EquationSolver

# --- Importy do wykresów ---
import matplotlib
# Ustaw backend na Agg, aby uniknąć błędów GUI w wątkach
matplotlib.use("Agg") 
import matplotlib.pyplot as plt
import numpy as np

# Upewnij się, że katalog na obrazy istnieje
IMAGES_DIR = os.path.join("ui", "images")
os.makedirs(IMAGES_DIR, exist_ok=True)

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
    def __init__(self):
        self.message: Optional[Any] = None
        self.data: Optional[Any] = None
        self.response: Optional[Any] = None  # obiekt/str zwrócony przez API po wywołaniu
        self.content: Optional[str] = None    # wypakowany tekst (string) z odpowiedzi
        self.client = None
        self.env = None
        self.history = []
        self.last_raw_completion = None  # <- tu zachowamy pełny surowy obiekt od providera
        self._system_added = False
        self.calculus_engine = CalculusEngine()
        self.equation_solver = EquationSolver()

    def _normalize_expression(self, expr: str, var_name: str = "x") -> str:
        """Normalizuje proste wyrażenia użytkownika.

        - zamienia ^ na ** (użytkownicy często używają potęgowania ^)
        - wstawia * pomiędzy liczbą a zmienną, np. 2x -> 2*x
        - wstawia * pomiędzy liczbą a nawiasem, np. 3(x+1) -> 3*(x+1)
        """
        if not isinstance(expr, str):
            return expr
        # potęgowanie
        s = expr.replace("^", "**")
        # liczba bezpośrednio przed zmienną, np. 2x -> 2*x
        s = re.sub(rf"(\d)(\s*){re.escape(var_name)}\b", rf"\1*\2{var_name}", s)
        # liczba bezpośrednio przed nawiasem, np. 3(x+1) -> 3*(x+1)
        s = re.sub(r"(\d)\s*\(", r"\1*(", s)
        return s

    def read_env(self):
        self.env = Env()
        self.env.read_env()

    # ---- bezpieczny evaluator matematyczny (ast-based) ----

    _ALLOWED_NAMES = {
        "sqrt": math.sqrt,
        "pow": pow,

        # podstawowe statystyki
        "abs": abs,
        "max": max,
        "min": min,

        # trygonometria
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "asin": math.asin,
        "acos": math.acos,
        "atan": math.atan,
        "atan2": math.atan2,

        # logarytmy i eksponenty
        "log": math.log,
        "log10": math.log10,
        "exp": math.exp,

        # inne przydatne
        "ceil": math.ceil,
        "floor": math.floor,
        "fabs": math.fabs,
        "round": round,
        "degrees": math.degrees,
        "radians": math.radians,

        # stałe matematyczne
        "pi": math.pi,
        "e": math.e
    }

    _ALLOWED_OPERATORS = {
        ast.Add: op.add,
        ast.Sub: op.sub,
        ast.Mult: op.mul,
        ast.Div: op.truediv,
        ast.Pow: op.pow,
        ast.Mod: op.mod,
        ast.USub: op.neg,
        ast.UAdd: op.pos,
    }

    def _eval_ast(self, node, variables=None):
        if variables is None:
            variables = {}
        
        if isinstance(node, ast.Expression):
            return self._eval_ast(node.body, variables)
        if isinstance(node, ast.Constant):  # Python 3.8+
            return node.value
        if isinstance(node, ast.Num):  # compatibility
            return node.n
        if isinstance(node, ast.BinOp):
            left = self._eval_ast(node.left, variables)
            right = self._eval_ast(node.right, variables)
            op_type = type(node.op)
            if op_type in self._ALLOWED_OPERATORS:
                return self._ALLOWED_OPERATORS[op_type](left, right)
            raise ValueError(f"Operator {op_type} not allowed")
        if isinstance(node, ast.UnaryOp):
            operand = self._eval_ast(node.operand, variables)
            op_type = type(node.op)
            if op_type in self._ALLOWED_OPERATORS:
                return self._ALLOWED_OPERATORS[op_type](operand)
            raise ValueError(f"Unary operator {op_type} not allowed")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Only simple function calls allowed")
            func_name = node.func.id
            if func_name not in self._ALLOWED_NAMES:
                raise ValueError(f"Function {func_name} not allowed")
            func = self._ALLOWED_NAMES[func_name]
            args = [self._eval_ast(a, variables) for a in node.args]
            return func(*args)
        if isinstance(node, ast.Name):
            # TU JEST KLUCZOWA ZMIANA: sprawdzamy czy nazwa jest w zmiennych (np. x)
            if node.id in variables:
                return variables[node.id]
            if node.id in self._ALLOWED_NAMES:
                return self._ALLOWED_NAMES[node.id]
            raise ValueError(f"Use of name {node.id} not allowed")
        # nie pozwalamy na nic więcej (No Attribute, Subscript, Lambda itp.)
        raise ValueError(f"Unsupported AST node: {type(node).__name__}")

    def safe_eval_math(self, expression: str, variables=None):
        try:
            # normalizacja (potęgowanie, brakujący operator mnożenia)
            expr = self._normalize_expression(expression)
            parsed = ast.parse(expr, mode="eval")
            val = self._eval_ast(parsed, variables)
            return {"result": val}
        except Exception as e:
            return {"error": str(e)}


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
            payload["expression"] = self._normalize_expression(str(payload["expression"]))
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
            payload["expression"] = self._normalize_expression(str(payload["expression"]))
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

    # ---- inicjalizacja klienta ----
    # ---- Generowanie Wykresu (POPRAWIONE) ----
    def _generate_plot_image(self, expression: str, x_min=-10, x_max=10):
        """Generuje wykres za pomocą matplotlib i zapisuje do pliku."""
        try:
            x_values = np.linspace(x_min, x_max, 200)
            y_values = []
            # normalizacja wyrażenia (np. 2x -> 2*x, ^ -> **)
            expr_clean = self._normalize_expression(expression)
            parsed = ast.parse(expr_clean, mode="eval")

            for x in x_values:
                res = self._eval_ast(parsed, variables={"x": x})
                y_values.append(res)
            
            # Tworzenie figury
            plt.figure(figsize=(6, 4), dpi=100)
            
            # Rysowanie linii
            plt.plot(x_values, y_values, label=f"f(x) = {expression}", color="#849FF5", linewidth=2)
            
            # Linie pomocnicze (osie)
            plt.axhline(0, color='gray', linewidth=0.8, linestyle='--')
            plt.axvline(0, color='gray', linewidth=0.8, linestyle='--')
            plt.grid(True, linestyle=':', alpha=0.6)
            
            # Legenda i tytuł (ustawiamy kolor od razu tutaj)
            plt.title("Wykres funkcji", color='#C3C3C5')
            plt.legend()
            
            # Stylizacja pod ciemny motyw
            ax = plt.gca()
            ax.set_facecolor('#28282A')
            fig = plt.gcf()
            fig.patch.set_facecolor('#28282A')
            
            # Kolory osi i etykiet
            ax.tick_params(colors='#C3C3C5')
            ax.yaxis.label.set_color('#C3C3C5')
            ax.xaxis.label.set_color('#C3C3C5')
            for spine in ax.spines.values():
                spine.set_edgecolor('#555555')

            # Bezpieczna zmiana koloru tekstu legendy
            legend = ax.get_legend()
            if legend:
                for text in legend.get_texts():
                    text.set_color("#333333")

            # Zapis do pliku
            filename = f"plot_{uuid.uuid4().hex}.png"
            path = os.path.join(IMAGES_DIR, filename)
            plt.savefig(path, bbox_inches='tight')
            plt.close() # Zamknij figurę, aby zwolnić pamięć
            
            return path
        except Exception as e:
            print(f"Plot generation error: {e}")
            # Zamknij plot w razie błędu, żeby nie wisiał w pamięci
            try: plt.close() 
            except: pass
            return None

    # ---- Inicjalizacja klienta ----
    def init_client(self):
        self.client = openai.OpenAI(
            api_key=self.env.str("OPENAI_API_KEY"),
            base_url="https://services.clarin-pl.eu/api/v1/oapi/"
        )

    # ---- wysyłka zapytania do modelu ----
    def call_method(self, user_message: str):

        if not self._system_added:
            system_prompt = (
                "Jesteś inteligentnym asystentem konwersacyjnym. "
                "Kiedy użytkownik prosi o obliczenia, równania, pochodne, całki lub wykresy, NIE odpowiadaj opisowo, "
                "tylko zwracaj wyłącznie JSON w jednym z poniższych formatów.\n\n"

                "FORMATY KOMEND SPECJALNYCH (używaj ich tylko do zadań matematycznych):\n"
                "1. Obliczenia (np. 2+2):\n"
                "   {\"action\": \"evaluate_math\", \"action_input\": {\"expression\": \"...\"}}\n\n"

                "2. Rozwiązanie równania (np. 2x^2+3x-5=0):\n"
                "   {\"action\": \"solve_equation\", \"action_input\": {\"equation\": \"...\"}}\n\n"

                "3. Pochodna (z opcjonalnym obliczeniem w punkcie):\n"
                "   {\"action\": \"differentiate\", \"action_input\": {"
                "\"expression\": \"...\", \"variable\": \"x\", \"order\": 1, \"at\": null}}\n\n"

                "4. Całka (nieoznaczona lub oznaczona):\n"
                "   {\"action\": \"integrate\", \"action_input\": {"
                "\"expression\": \"...\", \"variable\": \"x\", \"bounds\": [dolna, górna]}}\n\n"

                "5. Wykres funkcji (np. 'narysuj x^2'):\n"
                "   {\"action\": \"plot_function\", \"action_input\": {"
                "\"expression\": \"...\", \"min\": -10, \"max\": 10}}\n\n"

                "Jeśli pytanie użytkownika NIE wymaga powyższych działań, odpowiadaj normalnie po polsku, bez JSON."
            )

            self.history.append({
                "role": "system",
                "content": system_prompt,
            })
            self._system_added = True

        self.history.append({"role": "user", "content": user_message})

        try:
            self.response = self.client.chat.completions.create(
                model="or-gpt-oss-120b",
                messages=self.history,
                temperature=0
            )
            self.last_raw_completion = self.response
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
                else:
                    error_value = sol.get("error")
                    message_text += f"⚠️ Błąd rozwiązania: {error_value}"
                success = sol.get("success", False)

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
                    path = self._generate_plot_image(expr_str, x_min, x_max)
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
