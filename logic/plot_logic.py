# --- Importy do wykresów ---
import matplotlib
# Ustaw backend na Agg, aby uniknąć błędów GUI w wątkach
matplotlib.use("Agg") 
import matplotlib.pyplot as plt
import numpy as np
import ast
import os
import uuid
import cmath
import re
import operator as op
import math

# Upewnij się, że katalog na obrazy istnieje
IMAGES_DIR = os.path.join("ui", "images")
os.makedirs(IMAGES_DIR, exist_ok=True)

class PlotLogic:
    def __init__(self, store=None):
        self.store = store

    # ---- bezpieczny evaluator matematyczny (ast-based) ----
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

    # ---- inicjalizacja klienta ----
    # ---- Generowanie Wykresu (POPRAWIONE) ----
    def _generate_plot_image(self, expression: str, x_min: float = -10, x_max: float = 10):
        """Generuje wykres i zapisuje go w folderze temp zarządzanym przez ChatStore."""
        try:
            # 1. Dynamiczne pobieranie ścieżki ze Store
            if self.store and hasattr(self.store, "get_images_dir"):
                target_dir = self.store.get_images_dir()
            else:
                # Fallback, gdyby store nie był przekazany
                target_dir = os.path.join("ui", "chats", "temp", "images")
                os.makedirs(target_dir, exist_ok=True)

            x_values = np.linspace(x_min, x_max, 400)  # Większa gęstość punktów dla gładkości
            y_values = []

            # Normalizacja i parsowanie
            expr_clean = self._normalize_expression(expression)
            parsed = ast.parse(expr_clean, mode="eval")

            for x in x_values:
                try:
                    res = self._eval_ast(parsed, variables={"x": x})
                    # Obsługa wartości zespolonych lub nieskończonych (np. 1/0)
                    if isinstance(res, (complex, np.complex128)):
                        res = res.real
                    y_values.append(res)
                except:
                    y_values.append(np.nan)

            # 2. Tworzenie i stylizacja wykresu
            plt.figure(figsize=(8, 5), dpi=100)
            plt.plot(x_values, y_values, label=f"f(x) = {expression}", color="#849FF5", linewidth=2.5)

            # Osie i siatka
            plt.axhline(0, color='white', linewidth=0.8, alpha=0.3)
            plt.axvline(0, color='white', linewidth=0.8, alpha=0.3)
            plt.grid(True, linestyle=':', alpha=0.2, color='#C3C3C5')

            # Konfiguracja kolorów tła
            ax = plt.gca()
            ax.set_facecolor('#28282A')
            fig = plt.gcf()
            fig.patch.set_facecolor('#28282A')

            # Kolory tekstu i etykiet
            plt.title("Wykres funkcji", color='#C3C3C5', pad=15)
            ax.tick_params(colors='#C3C3C5', labelsize=9)

            for spine in ax.spines.values():
                spine.set_edgecolor('#3D3D40')

            # Naprawiona legenda (poprawiony kolor tekstu na jasny)
            legend = plt.legend(facecolor='#3D3D40', edgecolor='#849FF5')
            if legend:
                for text in legend.get_texts():
                    text.set_color("#C3C3C5")

            # 3. Zapis do dynamicznej lokalizacji
            filename = f"plot_{uuid.uuid4().hex}.png"
            path = os.path.join(target_dir, filename)

            plt.savefig(path, bbox_inches='tight', facecolor=fig.get_facecolor())
            plt.close()

            return path

        except Exception as e:
            print(f"Błąd generowania wykresu: {e}")
            try:
                plt.close()
            except:
                pass
            return None
    
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