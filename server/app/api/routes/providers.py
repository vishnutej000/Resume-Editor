from fastapi import APIRouter

router = APIRouter()

PROVIDERS = {
    "groq": {
        "name": "Groq",
        "free": True,
        "monthly_reset": True,
        "models": [
            {"id": "groq/llama-3.3-70b-versatile", "name": "Llama 3.3 70B", "context": 128000, "recommended": True},
            {"id": "groq/deepseek-r1-distill-llama-70b", "name": "DeepSeek R1 Distill 70B", "context": 128000},
            {"id": "groq/llama-3.1-70b-versatile", "name": "Llama 3.1 70B", "context": 128000},
            {"id": "groq/llama-3.1-8b-instant", "name": "Llama 3.1 8B Instant", "context": 128000},
            {"id": "groq/mixtral-8x7b-32768", "name": "Mixtral 8x7B", "context": 32768},
            {"id": "groq/gemma2-9b-it", "name": "Gemma 2 9B", "context": 8192},
        ],
    },
    "cerebras": {
        "name": "Cerebras",
        "free": True,
        "monthly_reset": True,
        "models": [
            {"id": "cerebras/llama3.1-8b", "name": "Llama 3.1 8B", "context": 8192, "recommended": True},
            {"id": "cerebras/qwen-3-235b-a22b-instruct-2507", "name": "Qwen 3 235B A22B Instruct", "context": 8192},
        ],
    },
    "nvidia_nim": {
        "name": "NVIDIA NIM",
        "free": True,
        "monthly_reset": False,
        "models": [
            {"id": "nvidia_nim/qwen/qwen2.5-72b-instruct", "name": "Qwen 2.5 72B", "context": 128000, "recommended": True},
            {"id": "nvidia_nim/meta/llama-3.3-70b-instruct", "name": "Llama 3.3 70B", "context": 128000},
            {"id": "nvidia_nim/deepseek-ai/deepseek-r1", "name": "DeepSeek R1", "context": 128000},
            {"id": "nvidia_nim/microsoft/phi-4", "name": "Phi-4", "context": 16384},
        ],
    },
    "together_ai": {
        "name": "Together AI",
        "free": True,
        "monthly_reset": False,
        "models": [
            {"id": "together_ai/Qwen/Qwen2.5-72B-Instruct-Turbo", "name": "Qwen 2.5 72B", "context": 128000, "recommended": True},
            {"id": "together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo", "name": "Llama 3.3 70B", "context": 128000},
            {"id": "together_ai/deepseek-ai/DeepSeek-V3", "name": "DeepSeek V3", "context": 128000},
        ],
    },
    "openrouter": {
        "name": "OpenRouter",
        "free": True,
        "monthly_reset": True,
        "models": [
            {"id": "openrouter/meta-llama/llama-3.3-70b-instruct:free", "name": "Llama 3.3 70B (Free)", "context": 128000, "recommended": True},
            {"id": "openrouter/deepseek/deepseek-chat-v3-0324:free", "name": "DeepSeek V3 (Free)", "context": 128000},
            {"id": "openrouter/qwen/qwen2.5-72b-instruct:free", "name": "Qwen 2.5 72B (Free)", "context": 128000},
        ],
    },
    "ollama": {
        "name": "Ollama (Local)",
        "free": True,
        "monthly_reset": True,
        "models": [
            {"id": "ollama/llama3.3", "name": "Llama 3.3", "context": 128000},
            {"id": "ollama/qwen2.5:72b", "name": "Qwen 2.5 72B", "context": 128000, "recommended": True},
            {"id": "ollama/deepseek-r1:70b", "name": "DeepSeek R1 70B", "context": 128000},
            {"id": "ollama/phi4", "name": "Phi-4", "context": 16384},
            {"id": "ollama/mistral", "name": "Mistral 7B", "context": 32768},
        ],
    },
    "mistral": {
        "name": "Mistral AI",
        "free": True,
        "monthly_reset": True,
        "models": [
            {"id": "mistral/mistral-small-latest", "name": "Mistral Small", "context": 32000, "recommended": True},
            {"id": "mistral/open-mistral-7b", "name": "Mistral 7B (Open)", "context": 32000},
            {"id": "mistral/open-mixtral-8x7b", "name": "Mixtral 8x7B (Open)", "context": 32000},
        ],
    },
}


@router.get("/providers")
async def get_providers():
    return PROVIDERS
