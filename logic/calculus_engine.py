import math
from typing import Any, Dict, Optional

try:
    import sympy as sp
except Exception:
    sp = None


def _format_expression_string(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("**", "^")


if sp is not None:
    _SYMPY_BASE_LOCALS = {
        "abs": sp.Abs,
        "atan2": sp.atan2,
        "ceil": sp.ceiling,
        "degrees": lambda val: val * 180 / sp.pi,
        "fabs": sp.Abs,
        "floor": sp.floor,
        "log10": lambda val: sp.log(val, 10),
        "max": sp.Max,
        "min": sp.Min,
        "pow": sp.Pow,
        "radians": lambda val: val * sp.pi / 180,
    }
else:
    _SYMPY_BASE_LOCALS = {}


class CalculusEngine:
    """Obsługuje obliczanie pochodnych i całek przy użyciu SymPy."""

    def __init__(self):
        self._sympy_available = sp is not None

    def differentiate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            self._ensure_sympy()
        except RuntimeError as exc:
            return {"error": str(exc)}
        if not isinstance(payload, dict):
            payload = {}

        expression = payload.get("expression") or payload.get("expr")
        if not expression:
            return {"error": "Brak wyrażenia do zróżniczkowania."}
        var_name = payload.get("variable") or payload.get("var") or "x"
        var_name = (str(var_name).strip() or "x")
        order_value = payload.get("order") or payload.get("nth") or 1
        try:
            order = int(order_value)
            if order < 1:
                raise ValueError
        except Exception:
            return {"error": "Parametr 'order' musi być dodatnią liczbą całkowitą."}

        try:
            expr, symbol = self._parse_sympy_expression(expression, var_name)
            derivative = sp.simplify(sp.diff(expr, symbol, order))
        except Exception as exc:
            return {"error": f"Nie można policzyć pochodnej: {exc}"}

        result = {
            "expression": _format_expression_string(expression),
            "variable": var_name,
            "order": order,
            "derivative": _format_expression_string(derivative),
        }

        eval_point = None
        for key in ("at", "point", "value", "evaluate_at"):
            if key in payload and payload[key] is not None:
                eval_point = payload[key]
                break

        if eval_point is not None:
            try:
                val_expr = self._sympify_value(eval_point)
                evaluated = sp.simplify(derivative.subs(symbol, val_expr))
                result["at"] = self._format_sympy_output(val_expr)
                result["value_at"] = self._format_sympy_output(evaluated)
            except Exception as exc:
                result["value_error"] = f"Nie udało się obliczyć wartości w punkcie: {exc}"

        return result

    def integrate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            self._ensure_sympy()
        except RuntimeError as exc:
            return {"error": str(exc)}
        if not isinstance(payload, dict):
            payload = {}

        expression = payload.get("expression") or payload.get("expr")
        if not expression:
            return {"error": "Brak wyrażenia do scałkowania."}
        var_name = payload.get("variable") or payload.get("var") or "x"
        var_name = (str(var_name).strip() or "x")

        try:
            expr, symbol = self._parse_sympy_expression(expression, var_name)
            integral_result = sp.integrate(expr, symbol)
        except Exception as exc:
            return {"error": f"Nie można policzyć całki: {exc}"}

        bounds = payload.get("bounds") or payload.get("limits")
        lower_raw = upper_raw = None
        if isinstance(bounds, (list, tuple)) and len(bounds) == 2:
            lower_raw, upper_raw = bounds
        else:
            for key in ("lower", "from", "a"):
                if key in payload and payload[key] is not None:
                    lower_raw = payload[key]
                    break
            for key in ("upper", "to", "b"):
                if key in payload and payload[key] is not None:
                    upper_raw = payload[key]
                    break

        result = {
            "expression": _format_expression_string(expression),
            "variable": var_name,
            "integral_result": _format_expression_string(integral_result),
            "type": "indefinite",
        }

        if lower_raw is not None and upper_raw is not None:
            try:
                lower = self._sympify_value(lower_raw)
                upper = self._sympify_value(upper_raw)
                definite_value = sp.integrate(expr, (symbol, lower, upper))
                result.update({
                    "type": "definite",
                    "lower": self._format_sympy_output(lower),
                    "upper": self._format_sympy_output(upper),
                    "value": self._format_sympy_output(definite_value),
                })
            except Exception as exc:
                result["value_error"] = f"Nie udało się policzyć całki oznaczonej: {exc}"

        return result

    def _ensure_sympy(self):
        if not self._sympy_available:
            raise RuntimeError("Pakiet 'sympy' nie jest dostępny. Zainstaluj go aby liczyć pochodne/całki.")

    def _sympy_locals(self, variable: Optional[str] = None):
        self._ensure_sympy()
        locals_dict = dict(_SYMPY_BASE_LOCALS)
        if variable:
            var_name = str(variable).strip() or "x"
            locals_dict[var_name] = sp.Symbol(var_name)
        return locals_dict

    def _parse_sympy_expression(self, expression: Any, variable: Optional[str] = None):
        self._ensure_sympy()
        if expression is None:
            raise ValueError("Brak wyrażenia do przetworzenia.")
        expr_str = str(expression)
        var_name = (str(variable).strip() or "x") if variable else "x"
        locals_dict = self._sympy_locals(var_name)
        try:
            expr = sp.sympify(expr_str, locals=locals_dict)
        except Exception as exc:
            raise ValueError(f"Nie można sparsować wyrażenia '{expression}': {exc}") from exc
        return expr, locals_dict[var_name]

    def _sympify_value(self, value: Any):
        self._ensure_sympy()
        if value is None:
            raise ValueError("Nie podano wartości.")
        if isinstance(value, (int, float)):
            return sp.sympify(value)
        val_str = str(value).strip()
        if not val_str:
            raise ValueError("Pusta wartość.")
        try:
            return sp.sympify(val_str, locals=dict(_SYMPY_BASE_LOCALS))
        except Exception as exc:
            raise ValueError(f"Nie można zinterpretować wartości '{value}': {exc}") from exc

    def _format_sympy_output(self, value: Any):
        if sp is None or value is None:
            return value
        if isinstance(value, (int, float)):
            return value
        try:
            if getattr(value, "is_number", False):
                approx = float(value.evalf())
                if math.isfinite(approx):
                    return approx
        except Exception:
            pass
        return _format_expression_string(value)
