import asyncio, httpx, os
from dotenv import load_dotenv
load_dotenv()

async def test():
    api_key = os.getenv("OPENROUTER_API_KEY")
    model   = os.getenv("OPENROUTER_EMBED_MODEL", "nomic-ai/nomic-embed-text-v1.5:free")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/embeddings",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            json={"model": model, "input": ["test sentence"]},
        )
        print("Status:", resp.status_code)
        print("Body:  ", resp.text)

asyncio.run(test())