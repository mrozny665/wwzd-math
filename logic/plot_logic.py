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