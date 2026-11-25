import os
import sys
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import ollama
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.session import ClientSession

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# MCP Client state
mcp_session = None
mcp_exit_stack = None

class ChatRequest(BaseModel):
    messages: list

@app.on_event("startup")
async def startup():
    global mcp_session, mcp_exit_stack
    import contextlib
    mcp_exit_stack = contextlib.AsyncExitStack()
    
    python_exe = sys.executable
    server_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "adapters", "claude", "server.py"))
    
    server_params = StdioServerParameters(
        command=python_exe,
        args=[server_script],
        env=None
    )
    
    try:
        read, write = await mcp_exit_stack.enter_async_context(stdio_client(server_params))
        mcp_session = await mcp_exit_stack.enter_async_context(ClientSession(read, write))
        await mcp_session.initialize()
        print("Successfully connected to Solidworks MCP Server")
    except Exception as e:
        print(f"Failed to connect to MCP Server: {e}")

@app.on_event("shutdown")
async def shutdown():
    if mcp_exit_stack:
        await mcp_exit_stack.aclose()

@app.post("/api/chat")
async def chat(request: ChatRequest):
    if not mcp_session:
        raise HTTPException(status_code=500, detail="MCP Server is not connected.")
    
    try:
        # 1. Fetch available tools from the MCP server
        mcp_tools_resp = await mcp_session.list_tools()
        
        # Convert MCP tools to Ollama format
        # Llama 3.2 3B gets overwhelmed by 40+ complex tools, so we filter to the essential ones for basic testing
        allowed_tools = {"ensure_ready", "open_document", "open_new_part", "create_sketch", "add_sketch_entity", "extrude_feature", "add_dimension"}
        
        ollama_tools = []
        for t in mcp_tools_resp.tools:
            if t.name in allowed_tools:
                ollama_tools.append({
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description or "",
                        "parameters": t.input_schema
                    }
                })
            
        client = ollama.AsyncClient(host=OLLAMA_HOST)
        messages = request.messages
        
        print(f"Sending request to Ollama ({OLLAMA_MODEL}) with {len(ollama_tools)} tools")
        
        # 2. Call Ollama with tools
        response = await client.chat(
            model=OLLAMA_MODEL,
            messages=messages,
            tools=ollama_tools
        )
        
        messages.append(response["message"])
        
        # 3. Process any tool calls made by Ollama
        while response["message"].get("tool_calls"):
            for tool_call in response["message"]["tool_calls"]:
                func_name = tool_call["function"]["name"]
                func_args = tool_call["function"]["arguments"]
                
                print(f"Ollama called tool: {func_name} with args: {func_args}")
                
                # Execute tool against Solidworks via MCP
                tool_result = await mcp_session.call_tool(func_name, arguments=func_args)
                
                # Format result for Ollama
                result_text = tool_result.content[0].text if tool_result.content else str(tool_result)
                
                messages.append({
                    "role": "tool",
                    "content": result_text,
                    "name": func_name
                })
            
            # 4. Give the tool results back to Ollama to generate final response
            response = await client.chat(
                model=OLLAMA_MODEL,
                messages=messages,
                tools=ollama_tools
            )
            messages.append(response["message"])
            
        return {"messages": messages}
        
    except Exception as e:
        print(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))
