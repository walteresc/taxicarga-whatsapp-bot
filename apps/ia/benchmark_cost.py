from django.conf import settings


GPT41_MINI_INPUT_USD_PER_MILLION = 0.40
GPT41_MINI_OUTPUT_USD_PER_MILLION = 1.60


def openai_benchmark_cost(input_tokens, output_tokens):
    configured_input = settings.OPENAI_INPUT_USD_PER_MILLION
    configured_output = settings.OPENAI_OUTPUT_USD_PER_MILLION
    input_rate = configured_input or GPT41_MINI_INPUT_USD_PER_MILLION
    output_rate = configured_output or GPT41_MINI_OUTPUT_USD_PER_MILLION
    return {
        "estimated_cost_usd": round(
            (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000, 8),
        "input_usd_per_million": input_rate,
        "output_usd_per_million": output_rate,
        "rates_source": "settings" if configured_input and configured_output
                        else "gpt-4.1-mini benchmark fallback",
    }
