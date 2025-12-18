import ast
import math
import cmath
import re
from typing import Any, Dict


class EquationSolver:
    """
    Klasa do rozwiązywania równań wielomianowych stopnia do 2.
    Metody przeniesione z ChatLogic.py — niezależny moduł.
    """

    def _normalize_expression(self, expr: str, var_name: str = "x") -> str:
        if not isinstance(expr, str):
            return expr
        s = expr.replace("^", "**")
        s = re.sub(rf"(\d)(\s*){re.escape(var_name)}\b", rf"\1*\2{var_name}", s)
        s = re.sub(r"(\d)\s*\(", r"\1*(", s)
        return s

    def _ast_to_poly(self, node: ast.AST, var_name: str = "x") -> Dict[int, float]:
        if isinstance(node, ast.Expression):
            return self._ast_to_poly(node.body, var_name)
        if isinstance(node, ast.Constant):
            return {0: float(node.value)}
        if isinstance(node, ast.Num):  # compat
            return {0: float(node.n)}
        if isinstance(node, ast.Name):
            if node.id == var_name:
                return {1: 1.0}
            raise ValueError(f"Nieznana nazwa: {node.id}")
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            p = self._ast_to_poly(node.operand, var_name)
            return {k: -v for k, v in p.items()}
        if isinstance(node, ast.BinOp):
            left = self._ast_to_poly(node.left, var_name)
            right = self._ast_to_poly(node.right, var_name)
            if isinstance(node.op, ast.Add):
                res = left.copy()
                for k, v in right.items():
                    res[k] = res.get(k, 0.0) + v
                return res
            if isinstance(node.op, ast.Sub):
                res = left.copy()
                for k, v in right.items():
                    res[k] = res.get(k, 0.0) - v
                return res
            if isinstance(node.op, ast.Mult):
                res = {}
                for a, va in left.items():
                    for b, vb in right.items():
                        deg = a + b
                        res[deg] = res.get(deg, 0.0) + va * vb
                return res
            if isinstance(node.op, ast.Div):
                if len(right) == 1 and 0 in right and right[0] != 0:
                    denom = right[0]
                    return {k: v / denom for k, v in left.items()}
                raise ValueError("Dzielenie przez wyrażenie z zmienną nieobsługiwane")
            if isinstance(node.op, ast.Pow):
                if len(right) == 1 and 0 in right:
                    exp = int(right[0])
                    if exp < 0 or exp > 2:
                        raise ValueError("Tylko potęgi 0..2 obsługiwane")
                    res = {0: 1.0}
                    for _ in range(exp):
                        new = {}
                        for a, va in res.items():
                            for b, vb in left.items():
                                deg = a + b
                                new[deg] = new.get(deg, 0.0) + va * vb
                        res = new
                    return res
                raise ValueError("Nieobsługiwana potęga")
        raise ValueError(f"Nieobsługiwany węzeł AST: {type(node).__name__}")

    def solve_equation(self, equation: str, var_name: str = "x") -> Dict[str, Any]:
        try:
            if "=" not in equation:
                return {"success": False, "error": "Brak znaku '=' w równaniu"}

            eq = self._normalize_expression(equation, var_name=var_name)
            left_s, right_s = eq.split("=", 1)

            left_ast = ast.parse(left_s, mode="eval")
            right_ast = ast.parse(right_s, mode="eval")

            left_poly = self._ast_to_poly(left_ast, var_name)
            right_poly = self._ast_to_poly(right_ast, var_name)

            res = {}
            for k, v in left_poly.items():
                res[k] = res.get(k, 0.0) + v
            for k, v in right_poly.items():
                res[k] = res.get(k, 0.0) - v

            res = {k: (0.0 if abs(v) < 1e-12 else v) for k, v in res.items()}
            if not res:
                return {"success": True, "solution": "Tożsamość (wszystkie x)"}

            max_deg = max(res.keys())
            if max_deg == 0:
                if abs(res.get(0, 0.0)) < 1e-12:
                    return {"success": True, "solution": "Tożsamość (wszystkie x)"}
                return {"success": False, "error": "Sprzeczne równanie (brak rozwiązań)"}

            if max_deg == 1:
                a = res.get(1, 0.0)
                b = res.get(0, 0.0)
                if abs(a) < 1e-12:
                    return {"success": False, "error": "Brak składnika przy zmiennej"}
                return {"success": True, "solution": -b / a}

            if max_deg == 2:
                a = res.get(2, 0.0)
                b = res.get(1, 0.0)
                c = res.get(0, 0.0)
                if abs(a) < 1e-12:
                    if abs(b) < 1e-12:
                        return {"success": False, "error": "Niewystarczające współczynniki"}
                    return {"success": True, "solution": -c / b}

                disc = b * b - 4 * a * c
                if disc > 0:
                    sqrt_disc = math.sqrt(disc)
                    x1 = (-b + sqrt_disc) / (2 * a)
                    x2 = (-b - sqrt_disc) / (2 * a)
                    return {"success": True, "solution": [x1, x2]}
                elif abs(disc) < 1e-15:
                    x = (-b) / (2 * a)
                    return {"success": True, "solution": x}
                else:
                    sqrt_disc = cmath.sqrt(disc)
                    x1 = (-b + sqrt_disc) / (2 * a)
                    x2 = (-b - sqrt_disc) / (2 * a)
                    return {"success": True, "solution": [x1, x2]}

            return {"success": False, "error": f"Stopień {max_deg} nieobsługiwany"}
        except Exception as e:
            return {"success": False, "error": str(e)}