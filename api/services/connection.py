from openai import OpenAI


def test_connection(base_url: str, api_key: str, model: str) -> tuple[bool, str]:
    client = OpenAI(api_key=api_key, base_url=base_url)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "test"}],
            max_tokens=1,
        )
        if not response.choices or not response.choices[0].message:
            return False, f"{model}: Invalid response from API"
        return True, f"{model}: API connection successful"
    except Exception as e:
        return False, f"{model}: API connection failed: {str(e)}"
