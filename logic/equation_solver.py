import ast
import math
import cmath
import re
from typing import Any, Dict, List, Optional

try:
    import sympy as sp
except Exception:
    sp = None

_TRIG_FUNCTION_NAMES = (
    "sin", "cos", "tan", "tg", "cot", "ctg", "sec", "csc",
    "asin", "acos", "atan", "atan2"
)
_TRIG_PATTERN = re.compile(r"\b(" + "|".join(_TRIG_FUNCTION_NAMES) + r")\b", re.IGNORECASE)
_BASIC_TRIG_FUNCS = {"sin", "cos", "tan"}
_CONST_ALLOWED_ATTR_BASES = {"math", "cmath", "numpy", "np"}


class EquationSolver:
    """
    Klasa do rozwiązywania równań wielomianowych stopnia do 2 oraz prostych równań trygonometrycznych.
    Metody przeniesione z ChatLogic.py — niezależny moduł.
    """

    def _normalize_expression(self, expr: str, var_name: str = "x") -> str:
        if not isinstance(expr, str):
            return expr
        s = expr.replace("^", "**")
        s = re.sub(r"\btg\b", "tan", s, flags=re.IGNORECASE)
        s = re.sub(r"\bctg\b", "cot", s, flags=re.IGNORECASE)
        s = re.sub(rf"(\d)(\s*){re.escape(var_name)}\b", rf"\1*\2{var_name}", s)
        s = re.sub(r"(\d)\s*\(", r"\1*(", s)
        s = re.sub(
            r"(\d)\s*(?=(sin|cos|tan|cot|sec|csc|asin|acos|atan|atan2)\b)",
            r"\1*",
            s,
            flags=re.IGNORECASE,
        )
        s = re.sub(
            rf"\b(sin|cos|tan|cot|sec|csc|asin|acos|atan|atan2)\s+({re.escape(var_name)})\b",
            r"\1(\2)",
            s,
            flags=re.IGNORECASE,
        )
        return s

    def _match_basic_trig_call(self, node: ast.AST, var_name: str) -> Optional[str]:
        if not isinstance(node, ast.Call) or node.keywords:
            return None
        func_node = node.func
        func_name = None
        if isinstance(func_node, ast.Name):
            func_name = func_node.id.lower()
        elif isinstance(func_node, ast.Attribute) and isinstance(func_node.value, ast.Name):
            base = func_node.value.id.lower()
            if base not in _CONST_ALLOWED_ATTR_BASES:
                return None
            func_name = func_node.attr.lower()
        if func_name not in _BASIC_TRIG_FUNCS:
            return None
        if len(node.args) != 1:
            return None
        arg = node.args[0]
        if isinstance(arg, ast.Name) and arg.id == var_name:
            return func_name
        return None

    def _extract_constant_value(self, node: ast.AST) -> Optional[float]:
        if isinstance(node, ast.Expression):
            return self._extract_constant_value(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.Num):
            return float(node.n)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            val = self._extract_constant_value(node.operand)
            if val is None:
                return None
            return val if isinstance(node.op, ast.UAdd) else -val
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
            left = self._extract_constant_value(node.left)
            right = self._extract_constant_value(node.right)
            if left is None or right is None:
                return None
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                if abs(right) < 1e-15:
                    return None
                return left / right
            if isinstance(node.op, ast.Pow):
                try:
                    return left ** right
                except Exception:
                    return None
        if isinstance(node, ast.Name):
            name = node.id.lower()
            if name == "pi":
                return math.pi
            if name == "e":
                return math.e
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            base = node.value.id.lower()
            attr = node.attr.lower()
            if base in _CONST_ALLOWED_ATTR_BASES:
                if attr == "pi":
                    return math.pi
                if attr == "e":
                    return math.e
        return None

    def _extract_basic_trig_data(self, left_node: ast.AST, right_node: ast.AST, var_name: str) -> Optional[Dict[str, Any]]:
        func = self._match_basic_trig_call(left_node, var_name)
        if func:
            const_val = self._extract_constant_value(right_node)
            if const_val is not None:
                return {"func": func, "value": float(const_val)}
        func = self._match_basic_trig_call(right_node, var_name)
        if func:
            const_val = self._extract_constant_value(left_node)
            if const_val is not None:
                return {"func": func, "value": float(const_val)}
        return None

    def _solve_basic_trig_equation(self, func: str, value: float, var_name: str) -> Dict[str, Any]:
        tol = 1e-12
        if func == "cos":
            if abs(value) > 1 + tol:
                return {"success": True, "solution": f"Brak rozwiązań rzeczywistych dla cos({var_name}) = {self._format_number(value)}"}
            value = max(min(value, 1.0), -1.0)
            if math.isclose(value, 1.0, abs_tol=tol):
                return {"success": True, "solution": f"{var_name} = 2*pi*k, k in Z"}
            if math.isclose(value, -1.0, abs_tol=tol):
                return {"success": True, "solution": f"{var_name} = pi + 2*pi*k, k in Z"}
            angle = math.acos(value)
            angle_text = self._format_angle_value(angle)
            neg_text = self._negate_expression_text(angle_text)
            return {
                "success": True,
                "solution": f"{var_name} = {angle_text} + 2*pi*k lub {var_name} = {neg_text} + 2*pi*k, k in Z",
            }

        if func == "sin":
            if abs(value) > 1 + tol:
                return {"success": True, "solution": f"Brak rozwiązań rzeczywistych dla sin({var_name}) = {self._format_number(value)}"}
            value = max(min(value, 1.0), -1.0)
            if math.isclose(value, 1.0, abs_tol=tol):
                return {"success": True, "solution": f"{var_name} = pi/2 + 2*pi*k, k in Z"}
            if math.isclose(value, -1.0, abs_tol=tol):
                return {"success": True, "solution": f"{var_name} = -pi/2 + 2*pi*k, k in Z"}
            if math.isclose(value, 0.0, abs_tol=tol):
                return {"success": True, "solution": f"{var_name} = pi*k, k in Z"}
            angle = math.asin(value)
            angle_text = self._format_angle_value(angle)
            alt_text = self._format_angle_value(math.pi - angle)
            if angle_text == alt_text:
                return {"success": True, "solution": f"{var_name} = {angle_text} + 2*pi*k, k in Z"}
            return {
                "success": True,
                "solution": f"{var_name} = {angle_text} + 2*pi*k lub {var_name} = {alt_text} + 2*pi*k, k in Z",
            }

        if func == "tan":
            angle = math.atan(value)
            angle_text = self._format_angle_value(angle)
            return {"success": True, "solution": f"{var_name} = {angle_text} + pi*k, k in Z"}

        return {"success": False, "error": "Nieobsługiwany typ równania trygonometrycznego"}

    def _format_number(self, value: float) -> str:
        if value is None:
            return "?"
        if math.isclose(value, 0.0, abs_tol=1e-15):
            value = 0.0
        return f"{value:.12g}"

    def _format_angle_value(self, value: float) -> str:
        if math.isclose(value, 0.0, abs_tol=1e-12):
            return "0"
        ratio = value / math.pi
        for denom in range(1, 13):
            approx = ratio * denom
            nearest = round(approx)
            if abs(approx - nearest) < 1e-9:
                num = nearest
                if num == 0:
                    return "0"
                g = math.gcd(abs(num), denom)
                num //= g
                denom //= g
                if denom == 1:
                    if num == 1:
                        return "pi"
                    if num == -1:
                        return "-pi"
                    return f"{num}*pi"
                sign = "-" if num < 0 else ""
                num_abs = abs(num)
                if num_abs == 1:
                    return f"{sign}pi/{denom}"
                return f"{sign}{num_abs}*pi/{denom}"
        return f"{value:.12g}"

    def _negate_expression_text(self, text: str) -> str:
        if not text or text == "0":
            return text
        if text.startswith("-"):
            return text[1:]
        return f"-{text}"

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
            if not isinstance(equation, str):
                equation = str(equation)
            if "=" not in equation:
                return {"success": False, "error": "Brak znaku '=' w równaniu"}

            eq = self._normalize_expression(equation, var_name=var_name)
            left_s, right_s = eq.split("=", 1)

            left_node = right_node = None
            parse_error = None
            try:
                left_node = ast.parse(left_s, mode="eval").body
                right_node = ast.parse(right_s, mode="eval").body
            except Exception as exc:
                parse_error = exc

            if left_node is not None and right_node is not None:
                basic_trig = self._extract_basic_trig_data(left_node, right_node, var_name)
                if basic_trig:
                    return self._solve_basic_trig_equation(basic_trig["func"], basic_trig["value"], var_name)

            if self._contains_trig_functions(eq):
                return self._solve_trigonometric_equation(
                    eq,
                    var_name,
                    left_str=left_s,
                    right_str=right_s,
                )

            if left_node is not None and right_node is not None:
                return self._solve_polynomial_equation(
                    eq,
                    var_name,
                    left_node=left_node,
                    right_node=right_node,
                )

            if parse_error is not None:
                return {"success": False, "error": f"Nie można sparsować równania: {parse_error}"}
            return {"success": False, "error": "Nie można sparsować równania"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _solve_polynomial_equation(self, eq: str, var_name: str, left_node: Optional[ast.AST] = None, right_node: Optional[ast.AST] = None) -> Dict[str, Any]:
        if left_node is None or right_node is None:
            left_s, right_s = eq.split("=", 1)
            left_node = ast.parse(left_s, mode="eval").body
            right_node = ast.parse(right_s, mode="eval").body

        left_poly = self._ast_to_poly(left_node, var_name)
        right_poly = self._ast_to_poly(right_node, var_name)

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

    def _contains_trig_functions(self, expr: str) -> bool:
        if not isinstance(expr, str):
            return False
        return bool(_TRIG_PATTERN.search(expr))

    def _solve_trigonometric_equation(self, eq: str, var_name: str, left_str: Optional[str] = None, right_str: Optional[str] = None) -> Dict[str, Any]:
        if sp is None:
            return {"success": False, "error": "Równania trygonometryczne wymagają pakietu 'sympy'."}

        if left_str is None or right_str is None:
            left_str, right_str = eq.split("=", 1)
        var_symbol = sp.Symbol(var_name)
        locals_dict = {var_name: var_symbol}

        try:
            left_expr = sp.sympify(left_str, locals=locals_dict)
            right_expr = sp.sympify(right_str, locals=locals_dict)
        except Exception as exc:
            return {"success": False, "error": f"Nie udało się sparsować równania trygonometrycznego: {exc}"}

        diff_expr = sp.simplify(left_expr - right_expr)
        if diff_expr == 0:
            return {"success": True, "solution": "Tożsamość (wszystkie x)"}

        trig_funcs = (sp.sin, sp.cos, sp.tan, sp.cot, sp.sec, sp.csc, sp.asin, sp.acos, sp.atan, sp.atan2)
        if not diff_expr.has(*trig_funcs):
            return self._solve_polynomial_equation(eq, var_name)

        try:
            solution_set = sp.solveset(diff_expr, var_symbol, domain=sp.S.Reals)
        except Exception as exc:
            return {"success": False, "error": f"SymPy nie rozwiązał równania trygonometrycznego: {exc}"}

        if isinstance(solution_set, sp.ConditionSet):
            return {
                "success": False,
                "error": f"Nie znaleziono jawnego rozwiązania trygonometrycznego: {self._format_sympy_text(solution_set)}",
            }
        if solution_set is sp.EmptySet or solution_set == sp.EmptySet:
            return {"success": True, "solution": "Brak rozwiązań rzeczywistych dla równania trygonometrycznego"}

        formatted = self._format_trig_solution_set(solution_set, var_name)
        if formatted is None:
            return {"success": True, "solution": "Brak rozwiązań rzeczywistych dla równania trygonometrycznego"}
        return {"success": True, "solution": formatted}

    def _format_sympy_text(self, value: Any) -> str:
        text = str(value)
        return text.replace("**", "^")

    def _format_trig_solution_set(self, solution_set: Any, var_name: str) -> Optional[Any]:
        if sp is None or solution_set is None:
            return None

        if isinstance(solution_set, sp.EmptySet):
            return None

        if isinstance(solution_set, sp.FiniteSet):
            values: List[str] = []
            for val in solution_set:
                values.append(self._format_sympy_text(sp.simplify(val)))
            values = sorted(values)
            if not values:
                return None
            if len(values) == 1:
                return values[0]
            return values

        if isinstance(solution_set, sp.ImageSet):
            return self._format_imageset_solution(solution_set, var_name)

        if isinstance(solution_set, sp.Union):
            parts: List[str] = []
            for subset in solution_set.args:
                formatted = self._format_trig_solution_set(subset, var_name)
                if not formatted:
                    continue
                if isinstance(formatted, list):
                    parts.append(", ".join(formatted))
                else:
                    parts.append(str(formatted))
            if not parts:
                return None
            if len(parts) == 1:
                return parts[0]
            return " lub ".join(parts)

        return self._format_sympy_text(solution_set)

    def _format_imageset_solution(self, image_set: Any, var_name: str) -> str:
        lam = getattr(image_set, "lamda", None)
        base_set = getattr(image_set, "base_set", None)
        if lam is None or not getattr(lam, "variables", None):
            return self._format_sympy_text(image_set)

        parameter = lam.variables[0]
        param_name = str(parameter)
        display_name = param_name.lstrip("_") or param_name
        display_symbol = sp.Symbol(display_name)
        expr = lam.expr.subs(parameter, display_symbol)

        expr_text = self._format_sympy_text(expr)
        if base_set in (sp.S.Integers, sp.Integers):
            base_text = "Z"
        else:
            base_text = self._format_sympy_text(base_set)

        return f"{var_name} = {expr_text}, {display_name} in {base_text}"