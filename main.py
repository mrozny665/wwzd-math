import openai

client = openai.OpenAI(
        api_key=api_key,
        base_url="https://services.clarin-pl.eu/api/v1/oapi/"
    )

prompt = "TEST"

response = client.chat.completions.create(
        model="bielik",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
)