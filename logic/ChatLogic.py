# ChatLogic.py
import openai
from environs import Env
import json
import math
import re
import ast
import operator as op
from typing import Any, Optional

class ChatResult:
    """Reprezentuje wynik jednej interakcji z modelem."""
    def __init__(self, message, raw_json=None, content=None, action=None,
                 expression=None, result=None, error=None, success=True):
        self.message = message
        self.raw_json = raw_json
        self.content = content
        self.action = action
        self.expression = expression
        self.result = result
        self.error = error
        self.success = success

    def __repr__(self):
        return f"<ChatResult success={self.success} action={self.action} msg={self.message!r}>"


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

    def _eval_ast(self, node):
        if isinstance(node, ast.Expression):
            return self._eval_ast(node.body)
        if isinstance(node, ast.Constant):  # Python 3.8+
            return node.value
        if isinstance(node, ast.Num):  # compatibility
            return node.n
        if isinstance(node, ast.BinOp):
            left = self._eval_ast(node.left)
            right = self._eval_ast(node.right)
            op_type = type(node.op)
            if op_type in self._ALLOWED_OPERATORS:
                return self._ALLOWED_OPERATORS[op_type](left, right)
            raise ValueError(f"Operator {op_type} not allowed")
        if isinstance(node, ast.UnaryOp):
            operand = self._eval_ast(node.operand)
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
            args = [self._eval_ast(a) for a in node.args]
            return func(*args)
        if isinstance(node, ast.Name):
            if node.id in self._ALLOWED_NAMES:
                return self._ALLOWED_NAMES[node.id]
            raise ValueError(f"Use of name {node.id} not allowed")
        # nie pozwalamy na nic więcej (No Attribute, Subscript, Lambda itp.)
        raise ValueError(f"Unsupported AST node: {type(node).__name__}")

    def safe_eval_math(self, expression: str):
        try:
            # drobne sanity: zamień ^ na ** (użytkownicy mogą użyć ^)
            expr = expression.replace("^", "**")
            # usuń niebezpieczne znaki (tylko jako prosty filter — dalej AST zadba o bezpieczeństwo)
            # parsuj AST i ewaluuj
            parsed = ast.parse(expr, mode="eval")
            val = self._eval_ast(parsed)
            return {"result": val}
        except Exception as e:
            return {"error": str(e)}

    # ---- inicjalizacja klienta ----
    def init_client(self):
        self.client = openai.OpenAI(
            api_key=self.env.str("OPENAI_API_KEY"),
            base_url="https://services.clarin-pl.eu/api/v1/oapi/"
        )

    # ---- wysyłka zapytania do modelu ----
    def call_method(self, user_message: str):

        if not self._system_added:
            self.history.append({
                "role": "system",
                "content": (
                    "Jesteś inteligentnym asystentem konwersacyjnym. "
                    "Jeśli użytkownik poprosi o wykonanie obliczeń matematycznych, "
                    "nie odpowiadaj tekstowo, tylko zwróć JSON w formacie:\n"
                    "{\"action\": \"evaluate_math\", \"action_input\": {\"expression\": \"...\"}}. "
                    "W pozostałych przypadkach odpowiadaj normalnie po polsku."
                ),
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
        """
        Zwraca obiekt ChatResult, zawierający:
          - message: tekst który ma się pokazać użytkownikowi
          - raw_json: preferencyjnie parsowany JSON (self.data) lub pełny surowy obiekt (self.last_raw_completion)
          - content: surowy content (tekst)
          - plus pola action/expression/result/error
        """
        message_text = ""
        action = None
        expr = None
        result_value = None
        error_value = None
        success = True

        if isinstance(self.data, dict) and self.data.get("action") in ("evaluate_math", "evaluate"):
            action = self.data.get("action")
            expr = None
            try:
                ai = self.data.get("action_input") or self.data.get("action_input", {})
                if isinstance(ai, dict):
                    expr = ai.get("expression", "")
                else:
                    expr = self.data.get("expression", "")
            except Exception:
                expr = self.data.get("expression", "")

            message_text += f"📞 Model wykrył działanie: {expr}\n"
            math_res = self.safe_eval_math(expr)
            if "result" in math_res:
                result_value = math_res["result"]
                message_text += f"🧮 Wynik obliczenia: {expr} = {result_value}"
            else:
                error_value = math_res.get("error", "Nieznany błąd")
                message_text += f"⚠️ Błąd podczas obliczania: {error_value}"
                success = False
        else:
            if isinstance(self.content, str):
                message_text += self.content
            elif isinstance(self.content, (dict, list)):
                try:
                    message_text += json.dumps(self.content, ensure_ascii=False)
                except Exception:
                    message_text += str(self.content)
            else:
                try:
                    message_text += str(self.response)
                except Exception:
                    message_text += "(brak odpowiedzi)"


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
            success=success
        )
        return cr
