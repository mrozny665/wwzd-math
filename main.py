import openai
from environs import Env
env = Env()
env.read_env()
client = openai.OpenAI(
        api_key=env.str("OPENAI_API_KEY"),
        base_url="https://services.clarin-pl.eu/api/v1/oapi/"
    )

prompt = "TEST"

response = client.chat.completions.create(
        model="bielik",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
)
print(response)