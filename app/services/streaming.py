async def stream_response(generator):
    """Server-Sent Events helper"""
    async for chunk in generator:
        yield f"data: {chunk}\n\n"
