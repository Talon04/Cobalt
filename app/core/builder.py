async def build_history(chat_id: int):
    from sqlalchemy import select
    from app.db.models.db import ChatPrompt
    from app.services.db import SessionLocal

    async with SessionLocal() as session:
        result = await session.execute(
            select(ChatPrompt).where(ChatPrompt.chat_id == chat_id).order_by(ChatPrompt.created_at.asc(), ChatPrompt.id.asc())
        )
        messages = result.scalars().all()

    history = []
    for msg in messages:
        history.append({
            "role": msg.role,
            "content": msg.content
        })

    return history


async def build_full_prompt(chat_id: int):
    full_prompt = await build_history(chat_id=chat_id)
    return full_prompt


def build_first_message_summary_prompt(message: str) -> list[dict[str, str]]:
    content = message.strip()
    return [
        {
            "role": "system",
            "content": (
                "Generate a concise chat title using exactly 4 words. "
                "Return only the title text."
            ),
        },
        {
            "role": "user",
            "content": f"Make a 4 word summary out of this:\n{content}",
        },
    ]