import openai
from environs import Env
import json
import math
import re


class ChatLogic:
    def __init__(self):
        self.message = None
        self.data = None
        self.response = None
        self.content = None
        self.client = None
        self.env = None

    def read_env(self):
        self.env = Env()
        self.env.read_env()

    def evaluate_math(self, expression: str):
        try:
            safe_expr = expression.replace("^", "**")
            result = eval(safe_expr, {"__builtins__": None}, {"sqrt": math.sqrt, "pow": pow})
            return {"result": result}
        except Exception as e:
            return {"error": str(e)}

    def init_client(self):
        self.client = openai.OpenAI(
            api_key=self.env.str("OPENAI_API_KEY"),
            base_url="https://services.clarin-pl.eu/api/v1/oapi/"
        )

    def call_method(self, user_message: str):
        self.response = self.client.chat.completions.create(
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

    def read_message(self):
        self.message = self.response.choices[0].message
        self.content = self.message.content.strip()

    def parse_json(self):
        self.data = None
        try:
            self.data = json.loads(self.content)
        except json.JSONDecodeError:
            # Jeśli model zwrócił dict w stylu Pythona z apostrofami
            if re.match(r"^\{'.*'\}$", self.content):
                try:
                    fixed = self.content.replace("'", '"')
                    self.data = json.loads(fixed)
                except Exception:
                    self.data = None

    def handle_response(self):
        message = ""

        if isinstance(self.data, dict) and self.data.get("action") == "evaluate_math":
            expr = self.data["action_input"]["expression"]
            message += f"📞 Model wykrył działanie: {expr}"
            result = self.evaluate_math(expr)

            if "result" in result:
                message += f"🧮 Wynik obliczenia: {expr} = {result['result']}"
            else:
                message += f"⚠️ Błąd podczas obliczania: {result['error']}"
        else:
            message += f"{self.content}"

        return message

# prompt = "TEST"
#
# response = client.chat.completions.create(
#         model="bielik",
#         messages=[{"role": "user", "content": prompt}],
#         temperature=0.7
# )
# print(response)
