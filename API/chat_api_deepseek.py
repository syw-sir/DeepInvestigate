"""
DeepAnalyze DeepSeek API Server
"""

import os
import json
import time
import uuid
import asyncio
import tempfile
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from fastapi import FastAPI, Request, Depends, HTTPException, Body
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI, AsyncOpenAI

# Import DeepSeek configuration
from config_deepseek import (
    API_BASE,
    MODEL_PATH,
    API_KEY,
    WORKSPACE_BASE_DIR,
    HTTP_SERVER_PORT,
    API_HOST,
    API_PORT,
    API_TITLE,
    API_VERSION,
    CODE_EXECUTION_TIMEOUT,
    MAX_NEW_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_MODEL,
)

# Import utility functions
from utils import (
    get_thread_workspace,
    build_download_url,
    prepare_vllm_messages,
    execute_code_safe,
    execute_code_safe_async,
    extract_code_from_segment,
    fix_tags_and_codeblock,
    sanitize_model_output,
    generate_report_from_messages,
    render_file_block,
    start_http_server,
    collect_file_info,
    _normalize_openai_message_content,
    WorkspaceTracker,
    uniquify_path,
)

# Initialize OpenAI client with DeepSeek API
vllm_client = OpenAI(base_url=API_BASE, api_key=API_KEY)
vllm_client_async = AsyncOpenAI(base_url=API_BASE, api_key=API_KEY)

# Create FastAPI app
app = FastAPI(title=API_TITLE, version=API_VERSION)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Chinese matplotlib support
Chinese_matplot_str = ""  # 文件不存在，使用空字符串

# Start HTTP server for file downloads
import threading
server_thread = threading.Thread(target=start_http_server, daemon=True)
server_thread.start()

# Define request models
class ChatCompletionRequest(BaseModel):
    model: str = DEFAULT_MODEL
    messages: List[Dict[str, Any]]
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = MAX_NEW_TOKENS
    stream: bool = False
    session_id: Optional[str] = None
    # Additional parameters for compatibility
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None

class ThreadCreateRequest(BaseModel):
    pass

class ThreadMessageRequest(BaseModel):
    role: str
    content: str
    file_ids: Optional[List[str]] = None

class RunCreateRequest(BaseModel):
    assistant_id: str = "default"
    instructions: Optional[str] = None
    tools: Optional[List[Dict[str, Any]]] = None

# Define response models
class ThreadResponse(BaseModel):
    id: str
    object: str = "thread"
    created_at: int

class MessageResponse(BaseModel):
    id: str
    object: str = "message"
    thread_id: str
    role: str
    content: List[Dict[str, Any]]
    created_at: int

class RunResponse(BaseModel):
    id: str
    object: str = "run"
    thread_id: str
    assistant_id: str
    status: str
    created_at: int
    started_at: Optional[int] = None
    completed_at: Optional[int] = None
    last_error: Optional[Dict[str, Any]] = None
    model: str = MODEL_PATH
    instructions: Optional[str] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    required_action: Optional[Dict[str, Any]] = None

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "model": MODEL_PATH}

@app.post("/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """Chat completions endpoint with DeepSeek API"""
    model = request.model
    messages = request.messages
    temperature = request.temperature
    max_tokens = request.max_tokens
    stream = request.stream

    # Get session_id from request, if not provided generate a new one with frontend format
    session_id = request.session_id if hasattr(request, 'session_id') and request.session_id else None
    if session_id:
        current_thread_id = session_id
    else:
        # Generate a new thread ID with frontend format: session_${Date.now()}_${random_str}
        current_thread_id = f"session_{int(time.time())}_{random.randint(1000000000, 9999999999)}"
    workspace_dir = get_thread_workspace(current_thread_id)
    generated_files = []

    # Initialize workspace tracker
    generated_dir = os.path.join(workspace_dir, "generated")
    os.makedirs(generated_dir, exist_ok=True)
    tracker = WorkspaceTracker(workspace_dir, generated_dir)

    async def generate_stream_with_execution():
        """Generate streaming response with code execution"""
        assistant_reply = ""
        vllm_messages = prepare_vllm_messages(messages, workspace_dir)
        finished = False

        while not finished:
            try:
                response = await vllm_client_async.chat.completions.create(
                    model=model,
                    messages=vllm_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                )

                cur_res = ""
                async for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content is not None:
                        delta = chunk.choices[0].delta.content
                        cur_res += delta
                        assistant_reply += delta

                        # Check if Answer tag is completed
                        if "</Answer>" in cur_res:
                            finished = True

                        chunk_data = {
                            "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"content": delta},
                                    "finish_reason": None,
                                }
                            ],
                        }
                        yield f"data: {json.dumps(chunk_data)}\n\n"

                    # Check if message is complete
                    finish_reason = chunk.choices[0].finish_reason if chunk.choices else None
                    
                    if finished:
                        break

                has_code_segment = "<Code>" in cur_res
                has_closed_code = "</Code>" in cur_res

                if finish_reason == "stop" and not finished:
                    if has_code_segment and not has_closed_code:
                        cur_res += "</Code>"
                        assistant_reply += "</Code>"
                        has_closed_code = True
                    elif not has_code_segment:
                        # 修复未闭合的标签，特别是<Answer>标签
                        cur_res = fix_tags_and_codeblock(cur_res)
                        assistant_reply = fix_tags_and_codeblock(assistant_reply)
                        # 转义内部标签
                        cur_res = sanitize_model_output(cur_res)
                        assistant_reply = sanitize_model_output(assistant_reply)
                        finished = True

                # Handle code execution
                if has_code_segment and has_closed_code and not finished and "<Answer>" not in cur_res:
                    vllm_messages.append({"role": "assistant", "content": cur_res})

                    code_str = extract_code_from_segment(cur_res)
                    if code_str:
                        code_str = Chinese_matplot_str + "\n" + code_str
                        exe_output = await execute_code_safe_async(code_str, workspace_dir)
                        artifacts = tracker.diff_and_collect()
                        exe_str = f"\n<Execute>\n```\n{exe_output}\n```\n</Execute>\n"
                        file_block = render_file_block(
                                artifacts, workspace_dir, current_thread_id, generated_files
                            )
                        assistant_reply += exe_str + file_block

                        # Stream execution result
                        for char in exe_str:
                            chunk_data = {
                                "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
                                "object": "chat.completion.chunk",
                                "created": int(time.time()),
                                "model": model,
                                "choices": [
                                    {
                                        "index": 0,
                                        "delta": {"content": char},
                                        "finish_reason": None,
                                    }
                                ],
                            }
                            yield f"data: {json.dumps(chunk_data)}\n\n"

                        # 检查是否已经生成了Answer标签，如果有则停止循环
                        if "</Answer>" in assistant_reply:
                            finished = True
                        else:
                            vllm_messages.append({"role": "user", "content": f"代码执行结果：\n{exe_output}"})
                    else:
                        finished = True
                elif "<Answer>" in cur_res:
                    # 如果已经包含<Answer>标签，修复未闭合的标签并标记为完成
                    original_cur_res = cur_res
                    cur_res = fix_tags_and_codeblock(cur_res)
                    assistant_reply = fix_tags_and_codeblock(assistant_reply)
                    # 转义内部标签
                    cur_res = sanitize_model_output(cur_res)
                    assistant_reply = sanitize_model_output(assistant_reply)
                    
                    # 发送修复后的内容（特别是闭合标签）
                    if cur_res != original_cur_res:
                        delta = cur_res[len(original_cur_res):]
                        for char in delta:
                            chunk_data = {
                                "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
                                "object": "chat.completion.chunk",
                                "created": int(time.time()),
                                "model": model,
                                "choices": [
                                    {
                                        "index": 0,
                                        "delta": {"content": char},
                                        "finish_reason": None,
                                    }
                                ],
                            }
                            yield f"data: {json.dumps(chunk_data)}\n\n"
                    
                    finished = True

            except Exception as e:
                error_msg = f"Error during generation: {str(e)}"
                chunk_data = {
                    "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": error_msg},
                            "finish_reason": "error",
                        }
                    ],
                }
                yield f"data: {json.dumps(chunk_data)}\n\n"
                finished = True

        # Generate and stream report
        report_block = generate_report_from_messages(
            messages, assistant_reply, workspace_dir, current_thread_id, generated_files
        )
        if report_block:
            for char in report_block:
                chunk_data = {
                    "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": char},
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(chunk_data)}\n\n"

        # Send final chunk with generated files and thread_id
        final_chunk_data = {}
        if generated_files:
            final_chunk_data["files"] = generated_files

        # Add thread_id to final chunk
        final_chunk_data["thread_id"] = current_thread_id

        final_chunk = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": final_chunk_data,
                    "finish_reason": "stop"
                }
            ],
        }

        # Keep backward compatibility with generated_files field
        if generated_files:
            final_chunk["generated_files"] = generated_files

        yield f"data: {json.dumps(final_chunk)}\n\n"
        yield "data: [DONE]\n\n"

    if stream:
        return StreamingResponse(generate_stream_with_execution(), media_type="text/event-stream")
    else:
        # Non-streaming response
        vllm_messages = prepare_vllm_messages(messages, workspace_dir)
        

        
        response = vllm_client.chat.completions.create(
            model=model,
            messages=vllm_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )

        assistant_reply = response.choices[0].message.content
        assistant_reply = fix_tags_and_codeblock(assistant_reply)
        assistant_reply = sanitize_model_output(assistant_reply)

        # Handle code execution - only if no <Answer> tag is present
        if "<Answer>" not in assistant_reply:
            code_str = extract_code_from_segment(assistant_reply)
            if code_str:
                code_str = Chinese_matplot_str + "\n" + code_str
                exe_output = execute_code_safe(code_str, workspace_dir)
                artifacts = tracker.diff_and_collect()
                exe_str = f"\n<Execute>\n```\n{exe_output}\n```\n</Execute>\n"
                file_block = render_file_block(
                        artifacts, workspace_dir, current_thread_id, generated_files
                    )
                assistant_reply += exe_str + file_block

        # Generate report
        report_block = generate_report_from_messages(
            messages, assistant_reply, workspace_dir, current_thread_id, generated_files
        )
        assistant_reply += report_block

        # Return response
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": assistant_reply,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
            "thread_id": current_thread_id,
            "generated_files": generated_files if generated_files else None,
        }

# Workspace management endpoints
@app.get("/workspace/files")
async def get_workspace_files(session_id: str = None):
    """Get workspace files list"""
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    
    workspace_dir = get_thread_workspace(session_id)
    files = []
    
    try:
        for root, _, filenames in os.walk(workspace_dir):
            for filename in filenames:
                file_path = os.path.join(root, filename)
                rel_path = os.path.relpath(file_path, workspace_dir)
                files.append({
                    "name": filename,
                    "size": os.path.getsize(file_path),
                    "path": rel_path,
                    "download_url": build_download_url(session_id, rel_path)
                })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get workspace files: {str(e)}")
    
    return {"files": files}

@app.get("/workspace/tree")
async def get_workspace_tree(session_id: str = None):
    """Get workspace files tree"""
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    
    workspace_dir = get_thread_workspace(session_id)
    
    def build_tree(path):
        """Build tree structure from directory"""
        node = {
            "name": os.path.basename(path) or "workspace",
            "path": os.path.relpath(path, workspace_dir),
            "is_dir": True,
            "children": []
        }
        
        try:
            for item in os.listdir(path):
                item_path = os.path.join(path, item)
                if os.path.isdir(item_path):
                    node["children"].append(build_tree(item_path))
                else:
                    node["children"].append({
                        "name": item,
                        "path": os.path.relpath(item_path, workspace_dir),
                        "is_dir": False,
                        "size": os.path.getsize(item_path),
                        "download_url": build_download_url(session_id, os.path.relpath(item_path, workspace_dir))
                    })
        except Exception as e:
            pass
        
        return node
    
    try:
        tree = build_tree(workspace_dir)
        return tree
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get workspace tree: {str(e)}")

@app.post("/workspace/upload")
async def upload_file(request: Request, session_id: str = None):
    """Upload file to workspace"""
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    
    workspace_dir = get_thread_workspace(session_id)
    
    try:
        form = await request.form()
        uploaded_files = form.getlist("files")
        
        if not uploaded_files:
            raise HTTPException(status_code=400, detail="No files uploaded")
        
        uploaded_file_info = []
        for file in uploaded_files:
            # 使用uniquify_path确保文件名唯一，上传到uploaded子文件夹
            uploaded_dir = os.path.join(workspace_dir, "uploaded")
            file_path = uniquify_path(Path(uploaded_dir) / file.filename)
            with open(file_path, "wb") as f:
                f.write(await file.read())
            
            # 构建相对于工作区根目录的路径
            rel_path = os.path.relpath(file_path, workspace_dir)
            uploaded_file_info.append({
                "name": file_path.name,
                "size": os.path.getsize(file_path),
                "path": rel_path,
                "download_url": build_download_url(session_id, rel_path)
            })
        
        return {"files": uploaded_file_info}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")

@app.post("/workspace/clear")
async def clear_workspace(session_id: str = None):
    """Clear workspace"""
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    
    workspace_dir = get_thread_workspace(session_id)
    generated_dir = os.path.join(workspace_dir, "generated")
    
    try:
        # Clear generated directory
        if os.path.exists(generated_dir):
            for root, _, files in os.walk(generated_dir):
                for file in files:
                    os.remove(os.path.join(root, file))
        
        return {"status": "success", "message": "Workspace cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear workspace: {str(e)}")

@app.delete("/workspace/file")
async def delete_file(path: str, session_id: str = None):
    """Delete workspace file"""
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    
    workspace_dir = get_thread_workspace(session_id)
    file_path = os.path.join(workspace_dir, path)
    
    try:
        if os.path.exists(file_path) and os.path.isfile(file_path):
            os.remove(file_path)
            return {"status": "success", "message": "File deleted"}
        else:
            raise HTTPException(status_code=404, detail="File not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {str(e)}")

@app.delete("/workspace/dir")
async def delete_dir(path: str, recursive: bool = False, session_id: str = None):
    """Delete workspace directory"""
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    
    workspace_dir = get_thread_workspace(session_id)
    dir_path = os.path.join(workspace_dir, path)
    
    try:
        if os.path.exists(dir_path) and os.path.isdir(dir_path):
            if recursive:
                shutil.rmtree(dir_path)
            else:
                # Check if directory is empty
                if os.listdir(dir_path):
                    raise HTTPException(status_code=400, detail="Directory is not empty")
                os.rmdir(dir_path)
            return {"status": "success", "message": "Directory deleted"}
        else:
            raise HTTPException(status_code=404, detail="Directory not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete directory: {str(e)}")

@app.post("/workspace/upload-to")
async def upload_to_dir(request: Request, dir: str = None, session_id: str = None):
    """Upload file to specified directory"""
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    
    workspace_dir = get_thread_workspace(session_id)
    target_dir = os.path.join(workspace_dir, dir or "")
    
    try:
        # Create directory if it doesn't exist
        os.makedirs(target_dir, exist_ok=True)
        
        form = await request.form()
        uploaded_files = form.getlist("files")
        
        if not uploaded_files:
            raise HTTPException(status_code=400, detail="No files uploaded")
        
        uploaded_file_info = []
        for file in uploaded_files:
            # 使用uniquify_path确保文件名唯一
            file_path = uniquify_path(Path(target_dir) / file.filename)
            with open(file_path, "wb") as f:
                f.write(await file.read())
            
            # Calculate relative path
            rel_path = os.path.relpath(file_path, workspace_dir)
            uploaded_file_info.append({
                "name": file_path.name,
                "size": os.path.getsize(file_path),
                "download_url": build_download_url(session_id, rel_path)
            })
        
        return {"files": uploaded_file_info}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")

@app.post("/execute")
async def execute_code(request: Request):
    """Execute Python code"""
    try:
        data = await request.json()
        code_str = data.get("code")
        session_id = data.get("session_id")
        
        if not code_str:
            raise HTTPException(status_code=400, detail="Code is required")
        
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id is required")
        
        workspace_dir = get_thread_workspace(session_id)
        
        # Execute code safely
        execution_result = await execute_code_safe_async(code_str, workspace_dir)
        
        # Track generated files
        generated_dir = os.path.join(workspace_dir, "generated")
        os.makedirs(generated_dir, exist_ok=True)
        tracker = WorkspaceTracker(workspace_dir, generated_dir)
        artifacts = tracker.diff_and_collect()
        
        # Build generated files list
        generated_files = []
        for artifact in artifacts:
            rel_path = os.path.relpath(artifact, workspace_dir)
            generated_files.append({
                "name": artifact.name,
                "size": artifact.stat().st_size,
                "path": rel_path,
                "download_url": build_download_url(session_id, rel_path)
            })
        
        return {
            "result": execution_result,
            "generated_files": generated_files
        }
    except Exception as e:
        return {
            "result": f"Error executing code: {str(e)}",
            "generated_files": []
        }

@app.post("/export/report")
async def export_report(request: Request):
    """Export report from conversation"""
    try:
        data = await request.json()
        messages = data.get("messages")
        title = data.get("title")
        session_id = data.get("session_id")
        
        if not messages:
            raise HTTPException(status_code=400, detail="Messages are required")
        
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id is required")
        
        workspace_dir = get_thread_workspace(session_id)
        generated_files = []
        
        # Get assistant reply from messages
        assistant_reply = ""
        for message in messages:
            if message.get("role") == "assistant":
                assistant_reply = message.get("content", "")
                break
        
        # Generate report
        report_block = generate_report_from_messages(
            messages, 
            assistant_reply, 
            workspace_dir, 
            session_id, 
            generated_files
        )
        
        # Create report metadata
        report_info = {
            "title": title or "Conversation Report",
            "generated_at": int(time.time()),
            "generated_files": generated_files
        }
        
        return {
            "status": "success",
            "message": "Report generated",
            "report": report_info
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")

# Thread management endpoints
@app.post("/threads", response_model=ThreadResponse)
async def create_thread(request: ThreadCreateRequest = Body(...)):
    """Create a new thread"""
    thread_id = str(uuid.uuid4())
    get_thread_workspace(thread_id)  # Create workspace directory
    return {
        "id": thread_id,
        "object": "thread",
        "created_at": int(time.time()),
    }

@app.get("/threads/{thread_id}", response_model=ThreadResponse)
async def get_thread(thread_id: str):
    """Get thread details"""
    workspace_dir = get_thread_workspace(thread_id)
    if not os.path.exists(workspace_dir):
        raise HTTPException(status_code=404, detail="Thread not found")
    return {
        "id": thread_id,
        "object": "thread",
        "created_at": int(os.path.getctime(workspace_dir)),
    }

@app.delete("/threads/{thread_id}")
async def delete_thread(thread_id: str):
    """Delete a thread"""
    import shutil
    workspace_dir = get_thread_workspace(thread_id)
    if os.path.exists(workspace_dir):
        shutil.rmtree(workspace_dir)
    return {
        "id": thread_id,
        "object": "thread.deleted",
        "deleted": True,
    }

# Message management endpoints
@app.post("/threads/{thread_id}/messages", response_model=MessageResponse)
async def create_message(thread_id: str, request: ThreadMessageRequest = Body(...)):
    """Create a new message in a thread"""
    # This is a simplified implementation
    return {
        "id": str(uuid.uuid4()),
        "object": "message",
        "thread_id": thread_id,
        "role": request.role,
        "content": [{"type": "text", "text": {"value": request.content}}],
        "created_at": int(time.time()),
    }

@app.get("/threads/{thread_id}/messages")
async def list_messages(thread_id: str):
    """List messages in a thread"""
    # This is a simplified implementation
    return {
        "object": "list",
        "data": [],
        "first_id": None,
        "last_id": None,
        "has_more": False,
    }

# Run management endpoints
@app.post("/threads/{thread_id}/runs", response_model=RunResponse)
async def create_run(thread_id: str, request: RunCreateRequest = Body(...)):
    """Create a new run"""
    return {
        "id": str(uuid.uuid4()),
        "object": "run",
        "thread_id": thread_id,
        "assistant_id": request.assistant_id,
        "status": "queued",
        "created_at": int(time.time()),
        "started_at": None,
        "completed_at": None,
        "last_error": None,
        "model": MODEL_PATH,
        "instructions": request.instructions,
        "tools": request.tools,
        "tool_calls": None,
        "required_action": None,
    }

@app.get("/threads/{thread_id}/runs/{run_id}", response_model=RunResponse)
async def get_run(thread_id: str, run_id: str):
    """Get run details"""
    # This is a simplified implementation
    return {
        "id": run_id,
        "object": "run",
        "thread_id": thread_id,
        "assistant_id": "default",
        "status": "completed",
        "created_at": int(time.time()) - 60,
        "started_at": int(time.time()) - 50,
        "completed_at": int(time.time()),
        "last_error": None,
        "model": MODEL_PATH,
        "instructions": None,
        "tools": None,
        "tool_calls": None,
        "required_action": None,
    }

@app.post("/threads/{thread_id}/runs/{run_id}/cancel")
async def cancel_run(thread_id: str, run_id: str):
    """Cancel a run"""
    return {
        "id": run_id,
        "object": "run",
        "thread_id": thread_id,
        "assistant_id": "default",
        "status": "cancelled",
        "created_at": int(time.time()) - 60,
        "started_at": int(time.time()) - 50,
        "completed_at": int(time.time()),
        "last_error": None,
        "model": MODEL_PATH,
        "instructions": None,
        "tools": None,
        "tool_calls": None,
        "required_action": None,
    }

@app.post("/generate-report")
async def generate_report_endpoint(request: Request):
    """Generate comprehensive report using LLM"""
    try:
        data = await request.json()
        session_id = data.get("session_id")
        
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id is required")
        
        # Get workspace directory
        workspace_dir = get_thread_workspace(session_id)
        generated_dir = os.path.join(workspace_dir, "generated")
        
        # Find all Conversation_Report files
        report_files = []
        if os.path.exists(generated_dir):
            for file in os.listdir(generated_dir):
                if file.startswith("Conversation_Report_") and file.endswith(".md"):
                    report_files.append(os.path.join(generated_dir, file))
        
        if not report_files:
            raise HTTPException(status_code=404, detail="No report files found")
        
        # Read the latest report file
        latest_report = max(report_files, key=os.path.getmtime)
        with open(latest_report, "r", encoding="utf-8") as f:
            report_content = f.read()
        
        # Load report prompt from config
        import yaml
        config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        
        report_prompt = config.get("prompts", {}).get("report_prompt", {}).get("content", "")
        if not report_prompt:
            report_prompt = "你是一名专业的技术文档撰写专家，请根据提供的内容撰写一份详细的报告。"
        
        # Prepare messages for LLM
        messages = [
            {"role": "system", "content": report_prompt},
            {"role": "user", "content": f"请根据以下报告内容撰写一份详细的综合报告：\n\n{report_content}"}
        ]
        
        # Call LLM to generate report
        client = OpenAI(
            api_key=API_KEY,
            base_url=API_BASE
        )
        
        response = client.chat.completions.create(
            model=MODEL_PATH,
            messages=messages,
            temperature=0.7,
            max_tokens=2000
        )
        
        generated_report = response.choices[0].message.content
        
        # Save the generated report
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        comprehensive_report_path = os.path.join(generated_dir, f"Comprehensive_Report_{timestamp}.md")
        
        with open(comprehensive_report_path, "w", encoding="utf-8") as f:
            f.write(generated_report)
        
        # Build download URL
        rel_path = os.path.relpath(comprehensive_report_path, workspace_dir)
        # Fix path separators and remove trailing slash
        rel_path = rel_path.replace('\\', '/').rstrip('/')
        download_url = build_download_url(session_id, rel_path)
        
        return {
            "status": "success",
            "message": "Report generated successfully",
            "report_url": download_url,
            "report_file": os.path.basename(comprehensive_report_path)
        }
        
    except Exception as e:
        print(f"Report generation error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=API_HOST, port=API_PORT)
