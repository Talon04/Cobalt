# Tool registry (empty Stage 1)
available_tools = {}

async def execute_tool(tool_name: str, **kwargs):
    """Execute registered tool"""
    if tool_name not in available_tools:
        raise ValueError(f"Unknown tool: {tool_name}")
    return await available_tools[tool_name](**kwargs)
