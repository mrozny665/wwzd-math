import openai
from environs import Env
import json
import math
import re
env = Env()
env.read_env()
client = openai.OpenAI(
        api_key=env.str("OPENAI_API_KEY"),
        base_url="https://services.clarin-pl.eu/api/v1/oapi/"
    )

# prompt = "TEST"
#
# response = client.chat.completions.create(
#         model="bielik",
#         messages=[{"role": "user", "content": prompt}],
#         temperature=0.7
# )
# print(response)
# --- Funkcja lokalna ---
# --- Funkcja lokalna ---
def evaluate_math(expression: str):
    try:
        safe_expr = expression.replace("^", "**")
        result = eval(safe_expr, {"__builtins__": None}, {"sqrt": math.sqrt, "pow": pow})
        return {"result": result}
    except Exception as e:
        return {"error": str(e)}

# --- Wiadomość użytkownika ---
user_message = input("Ty: ")

# --- Wywołanie modelu ---
response = client.chat.completions.create(
    model="or-gpt-oss-120b",
    messages=[
        {
            "role": "system",
            "content": (
                "Jesteś inteligentnym asystentem konwersacyjnym. "
                "Jeśli użytkownik poprosi o wykonanie obliczeń matematycznych, "
                "nie odpowiadaj tekstowo, tylko zwróć JSON w formacie:\n"
                "{\"action\": \"evaluate_math\", \"action_input\": {\"expression\": \"...\"}}. "
                "W pozostałych przypadkach odpowiadaj normalnie po polsku."
            ),
        },
        {"role": "user", "content": user_message},
    ],
    temperature=0.2
)

# --- Odczyt odpowiedzi ---
message = response.choices[0].message
content = message.content.strip()

# --- Próba parsowania JSON ---
data = None
try:
    data = json.loads(content)
except json.JSONDecodeError:
    # Jeśli model zwrócił dict w stylu Pythona z apostrofami
    if re.match(r"^\{'.*'\}$", content):
        try:
            fixed = content.replace("'", '"')
            data = json.loads(fixed)
        except Exception:
            data = None

# --- Obsługa wyniku ---
if isinstance(data, dict) and data.get("action") == "evaluate_math":
    expr = data["action_input"]["expression"]
    print(f"📞 Model wykrył działanie: {expr}")
    result = evaluate_math(expr)

    if "result" in result:
        print(f"🧮 Wynik obliczenia: {expr} = {result['result']}")
    else:
        print(f"⚠️ Błąd podczas obliczania: {result['error']}")
else:
    print(f"🤖 Asystent: {content}")