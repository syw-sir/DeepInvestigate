"""
DeepSeek API Backend for DeepAnalyze Chat Demo
"""

import os
import sys
import json
import time
import uuid
import shutil
import asyncio
import tempfile
import subprocess
import threading
import re
import yaml
from pathlib import Path
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, Request, Body, File, UploadFile, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import socketserver
import http.server
from functools import partial
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI

# 创建线程池用于异步执行
thread_pool = ThreadPoolExecutor(max_workers=4)


base_system_prompt = '''
# 强制指令：你是DeepInvestigate，一个面向复杂任务分析的智能体，必须严格遵循以下格式和工作流回答问题！

      ## 核心原则
      - 所有输出必须严格使用指定标签，否则将被系统拒绝
      - 标签内容中不得包含其他标签
      - 事实性问题必须通过代码验证，禁止直接回答

      ## 两种工作模式

      ### 1. 正常问答模式
      适用于简单问候、闲聊或非任务类问题，**直接回答，不使用任何标签**。

      ### 2. 任务模式（核心）
      适用于数据分析、问题解决等明确任务，必须严格遵循以下工作流：
      ```
      <Analyze> → <OODA> → [Code → (系统自动生成<Execute>) → <OODA>] → ... → <Answer>
      ```

      ## 标签使用规则（任务模式专属）

      ### <Analyze>（必须是第一个标签）
      - 分析用户任务需求
      - 制定详细解决方案
      - 说明后续步骤计划
      - 示例：
        ```
        <Analyze>
        用户需要分析销售数据找出最受欢迎的产品类别。我将先查看数据结构，然后分析各产品类别的销售额，最后给出结论。
        </Analyze>
        ```

      ### <OODA>（核心观察-调整-决策-行动循环）
      - **观察**：深入分析当前数据状态、代码执行结果或任务进展
      - **调整**：理解上下文含义，评估当前进展与目标差距，识别关键问题与模式
      - **决策**：基于分析确定下一步最优行动，调整任务策略与优先级
      - **行动**：指导后续代码生成或分析方向，优化步骤序列节奏
      - 每次收到`<Analyze>`或`<Execute>`后必须立即使用`<OODA>`进行深度思考
      - 必须对当前状态进行逻辑分析，评估任务完成度，动态调整后续步骤
      - 示例：
        ```
        <OODA>
        **观察**：销售数据包含5个字段（产品ID、类别、销售额、日期、地区），共有1000条记录，无缺失值。
        **调整**：数据结构清晰完整，当前完成度约30%。需要深入分析各类别销售额分布，识别核心业务模式。
        **决策**：下一步应计算各产品类别的销售额占比，使用可视化分析Top 3类别趋势。
        **行动**：将指导生成统计分析代码，重点关注类别字段的聚合计算和趋势可视化。
        </OODA>
        ```

      ### <Code>（生成可执行代码）
      - 必须使用 ```python ``` 格式包裹
      - 代码必须完整可执行
      - 仅在需要数据操作时使用
      - 示例：
        ```
        <Code>
        ```python
        import pandas as pd
        
        # 读取数据
        df = pd.read_csv('sales_data.csv')
        
        # 查看数据基本信息
        print(df.info())
        
        # 查看前5行数据
        print(df.head())
        ```
        </Code>
        ```

      ### <Execute>（系统自动生成，禁止使用）
      - 由系统自动生成，包含代码执行结果
      - 收到<Execute>后必须立即使用<OODA>分析结果

      ### <Answer>（必须是最后一个标签）
      - 基于分析和执行结果给出明确结论
      - 必须清晰、简洁、有针对性
      - 示例：
        ```
        <Answer>
        根据数据分析，电子产品类别是最受欢迎的，占总销售额的45%。其次是家居用品(28%)和服装(27%)。
        </Answer>
        ```

      ## 严格禁止事项
      1. 禁止生成<Execute>标签
      2. 禁止在标签内容中嵌套其他标签
      3. 禁止跳过<Analyze>标签直接使用其他标签
      4. 禁止在收到<Execute>后不使用<OODA>
      5. 禁止在任务未完成时使用<Answer>标签
      6. 禁止直接回答需要代码验证的事实性问题

      ## 代码执行环境
      - Python 3.x环境
      - 常用库：pandas, numpy, requests, os, sys, json等
      - 所有文件操作基于当前工作目录

'''

# 辅助函数：异步执行同步函数
def run_in_threadpool(func, *args, **kwargs):
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(thread_pool, func, *args, **kwargs)

# Import DeepSeek configuration
from API.config_deepseek import API_BASE, MODEL_PATH, API_KEY, WORKSPACE_BASE_DIR, HTTP_SERVER_PORT
from API.utils import sanitize_model_output, get_thread_workspace, load_prompt

# Initialize OpenAI client with DeepSeek API
client = OpenAI(base_url=API_BASE, api_key=API_KEY)

# Workspace configuration - Using imported values from API.config_deepseek
HTTP_SERVER_BASE = f"http://localhost:{HTTP_SERVER_PORT}"

# Chinese matplotlib support
Chinese_matplot_str = ""
with open("demo/chat/chinese_matplotlib.py", "r", encoding="utf-8") as f:
    Chinese_matplot_str = f.read()


# Helper functions
# 使用API.utils中的get_thread_workspace函数统一管理工作区
def get_session_workspace(session_id: str) -> str:
    """返回指定 session 的 workspace 路径（workspace_deepseek/{session_id}/）。"""
    if not session_id:
        session_id = "default"
    workspace_dir = get_thread_workspace(session_id)
    
    # Create subdirectories
    os.makedirs(os.path.join(workspace_dir, "uploaded"), exist_ok=True)
    os.makedirs(os.path.join(workspace_dir, "generated"), exist_ok=True)
    os.makedirs(os.path.join(workspace_dir, "context"), exist_ok=True)
    
    return workspace_dir


def uniquify_path(path: Path) -> Path:
    """确保路径唯一，避免覆盖现有文件。"""
    if not path.exists():
        return path
    
    counter = 1
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    
    while True:
        new_path = parent / f"{stem}_{counter}{suffix}"
        if not new_path.exists():
            return new_path
        counter += 1


def build_download_url(rel_path: str) -> str:
    try:
        encoded = quote(rel_path, safe="/")
    except Exception:
        encoded = rel_path
    return f"{HTTP_SERVER_BASE}/{encoded}"


def collect_file_info(directory: str) -> str:
    """Collect file information from directory, including subdirectories"""
    all_file_info_str = ""
    dir_path = Path(directory)
    if not dir_path.exists():
        return ""

    # 递归收集所有文件
    files = sorted([f for f in dir_path.rglob("*") if f.is_file()])
    for idx, file_path in enumerate(files, start=1):
        size_bytes = os.path.getsize(file_path)
        size_kb = size_bytes / 1024
        size_str = f"{size_kb:.1f}KB"
        # 获取文件相对于工作区根目录的路径
        rel_path = file_path.relative_to(dir_path)
        file_info = {"name": str(rel_path), "size": size_str}
        file_info_str = json.dumps(file_info, indent=4, ensure_ascii=False)
        all_file_info_str += f"File {idx}:\n{file_info_str}\n\n"
    return all_file_info_str


def execute_code_safe(code_str: str, workspace_dir: str, timeout_sec: int = 120) -> str:
    """Execute Python code in a separate process with timeout"""
    exec_cwd = os.path.abspath(workspace_dir)
    os.makedirs(exec_cwd, exist_ok=True)
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".py", dir=exec_cwd)
        os.close(fd)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(code_str)

        child_env = os.environ.copy()
        child_env.setdefault("MPLBACKEND", "Agg")
        child_env.setdefault("QT_QPA_PLATFORM", "offscreen")
        child_env.pop("DISPLAY", None)

        completed = subprocess.run(
            [sys.executable, tmp_path],
            cwd=exec_cwd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env=child_env,
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        return output
    except subprocess.TimeoutExpired:
        return f"[Timeout]: execution exceeded {timeout_sec} seconds"
    except Exception as e:
        return f"[Error]: {str(e)}"
    finally:
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


# HTTP Server for file downloads

def start_http_server():
    """启动HTTP文件服务器（不修改全局工作目录）。"""
    os.makedirs(WORKSPACE_BASE_DIR, exist_ok=True)
    handler = partial(
        http.server.SimpleHTTPRequestHandler, directory=WORKSPACE_BASE_DIR
    )
    with socketserver.TCPServer(("", HTTP_SERVER_PORT), handler) as httpd:
        print(f"DeepSeek HTTP Server serving {WORKSPACE_BASE_DIR} at port {HTTP_SERVER_PORT}")
        httpd.serve_forever()


# Start HTTP server in a separate thread
server_thread = threading.Thread(target=start_http_server, daemon=True)
server_thread.start()


# FastAPI app
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Helper function to get file icon
ICON_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".html": "html",
    ".css": "css",
    ".json": "json",
    ".csv": "csv",
    ".md": "markdown",
    ".txt": "text",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".gif": "image",
    ".pdf": "pdf",
    ".doc": "document",
    ".docx": "document",
    ".xlsx": "spreadsheet",
    ".xls": "spreadsheet",
}

def get_file_icon(extension: str) -> str:
    """Get icon name for file extension"""
    return ICON_EXTENSIONS.get(extension.lower(), "file")


# ---------- Workspace Files ----------
@app.get("/workspace/files")
async def get_workspace_files(session_id: str = "default"):
    """获取工作区文件列表（支持 session 隔离）"""
    from pathlib import Path
    
    workspace_dir = get_session_workspace(session_id)
    generated_dir = Path(workspace_dir) / "generated"
    # 获取 generated 目录下的文件名集合
    generated_files = (
        set(f.name for f in generated_dir.iterdir() if f.is_file())
        if generated_dir.exists()
        else set()
    )

    files = []
    for file_path in Path(workspace_dir).iterdir():
        if file_path.is_file():
            if file_path.name in generated_files:
                continue
            stat = file_path.stat()
            rel_path = f"{session_id}/{file_path.name}"
            files.append(
                {
                    "name": file_path.name,
                    "size": stat.st_size,
                    "extension": file_path.suffix.lower(),
                    "icon": get_file_icon(file_path.suffix),
                    "download_url": build_download_url(rel_path),
                    "preview_url": (
                        build_download_url(rel_path)
                        if file_path.suffix.lower()
                        in [
                            ".jpg",
                            ".jpeg",
                            ".png",
                            ".gif",
                            ".bmp",
                            ".pdf",
                            ".txt",
                            ".doc",
                            ".docx",
                            ".csv",
                            ".xlsx",
                        ]
                        else None
                    ),
                }
            )
    return {"files": files}


# ---------- Workspace Tree ----------
def _rel_path(path: Path, root: Path) -> str:
    try:
        rel = path.relative_to(root)
        return rel.as_posix()
    except Exception:
        return path.name


def build_tree(path: Path, root: Path = None) -> dict:
    if root is None:
        root = path
    node: dict = {
        "name": path.name or "workspace",
        "path": _rel_path(path, root),
        "is_dir": path.is_dir(),
    }
    if path.is_dir():
        children = []

        # 自定义排序：generated 文件夹放在最后，其他按目录优先、名称排序
        def sort_key(p):
            is_generated = p.name == "generated"
            is_dir = p.is_dir()
            return (is_generated, not is_dir, p.name.lower())

        for child in sorted(path.iterdir(), key=sort_key):
            if child.name.startswith("."):
                continue
            children.append(build_tree(child, root))
        node["children"] = children
    else:
        node["size"] = path.stat().st_size
        node["extension"] = path.suffix.lower()
        node["icon"] = get_file_icon(path.suffix)
        rel = _rel_path(path, root)
        node["download_url"] = build_download_url(f"{root.parent.name}/{rel}")
    return node


@app.get("/workspace/tree")
async def workspace_tree(session_id: str = "default"):
    from pathlib import Path
    from typing import Optional
    
    workspace_dir = get_session_workspace(session_id)
    root = Path(workspace_dir)
    tree_data = build_tree(root, root)

    # 在下载链接前加上 session_id 前缀
    def prefix_urls(node, sid):
        if "download_url" in node:
            node["download_url"] = build_download_url(f"{sid}/{node['path']}")
        if "children" in node:
            for child in node["children"]:
                prefix_urls(child, sid)
    
    prefix_urls(tree_data, session_id)
    return tree_data


# ---------- File Upload ----------
@app.post("/workspace/upload")
async def upload_files(
    files: List[UploadFile] = File(...), session_id: str = Query("default")
):
    """上传文件到工作区（支持 session 隔离）"""
    workspace_dir = get_session_workspace(session_id)
    uploaded_dir = os.path.join(workspace_dir, "uploaded")
    os.makedirs(uploaded_dir, exist_ok=True)
    uploaded_files = []

    for file in files:
        # 唯一化文件名，避免覆盖，上传到uploaded子文件夹
        dst = uniquify_path(Path(uploaded_dir) / file.filename)
        with open(dst, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        uploaded_files.append(
            {
                "name": dst.name,
                "size": len(content),
                "path": str(dst.relative_to(Path(workspace_dir))),
            }
        )

    return {
        "message": f"Successfully uploaded {len(uploaded_files)} files",
        "files": uploaded_files,
    }


@app.delete("/workspace/clear")
async def clear_workspace(session_id: str = Query("default")):
    """清空工作区（支持 session 隔离）"""
    workspace_dir = get_session_workspace(session_id)
    if os.path.exists(workspace_dir):
        shutil.rmtree(workspace_dir)
    os.makedirs(workspace_dir, exist_ok=True)
    return {"message": "Workspace cleared successfully"}


@app.post("/workspace/upload-to")
async def upload_to_dir(
    dir: str = Query("", description="relative directory under workspace"),
    files: List[UploadFile] = File(...),
    session_id: str = Query("default"),
):
    """上传文件到 workspace 下的指定子目录（仅限工作区内）。"""
    workspace_dir = get_session_workspace(session_id)
    abs_workspace = Path(workspace_dir).resolve()
    target_dir = (abs_workspace / dir).resolve()
    if abs_workspace not in target_dir.parents and target_dir != abs_workspace:
        raise HTTPException(status_code=400, detail="Invalid dir path")
    target_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for f in files:
        dst = uniquify_path(target_dir / f.filename)
        try:
            with open(dst, "wb") as buffer:
                content = await f.read()
                buffer.write(content)
            saved.append(
                {
                    "name": dst.name,
                    "size": len(content),
                    "path": str(dst.relative_to(abs_workspace)),
                }
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Save failed: {e}")
    return {"message": f"uploaded {len(saved)}", "files": saved}


@app.post("/execute")
async def execute_code_api(request: dict):
    """执行 Python 代码"""
    try:
        code = request.get("code", "")
        session_id = request.get("session_id", "default")
        workspace_dir = get_session_workspace(session_id)

        if not code:
            raise HTTPException(status_code=400, detail="No code provided")

        # 使用子进程安全执行，避免 GUI/线程问题（在指定 session workspace 中）
        result = await run_in_threadpool(execute_code_safe, code, workspace_dir)

        return {
            "success": True,
            "result": result,
            "message": "Code executed successfully",
        }

    except Exception as e:
        return {
            "success": False,
            "result": f"Error: {str(e)}",
            "message": "Code execution failed",
        }


async def bot_stream(messages, workspace, session_id="default"):
    """
    DeepSeek API implementation of bot_stream function
    """
    import sys
    original_cwd = os.getcwd()
    WORKSPACE_DIR = get_session_workspace(session_id)
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    # 创建 generated 子文件夹用于存放代码生成的文件
    GENERATED_DIR = os.path.join(WORKSPACE_DIR, "generated")
    os.makedirs(GENERATED_DIR, exist_ok=True)
    
    # 添加强制生成标签的系统提示
    system_prompt = base_system_prompt 
    
    # 处理消息，添加系统提示
    processed_messages = [
        {"role": "system", "content": system_prompt}
    ]
    
    # 过滤掉可能存在的系统消息
    for msg in messages:
        if msg.get("role") != "system":
            processed_messages.append(msg)
    
    if processed_messages and processed_messages[-1]["role"] == "user":
        user_message = processed_messages[-1]["content"]
        # 统一使用基于session_id的工作区
        file_info = collect_file_info(WORKSPACE_DIR)
        if file_info:
            processed_messages[-1][
                "content"
            ] = f"# Instruction\n{user_message}\n\n# Data\n{file_info}"
        else:
            processed_messages[-1]["content"] = f"# Instruction\n{user_message}"
    
    # 获取初始工作区文件集合，包括所有子文件夹
    initial_workspace = set()
    for root, _, files in os.walk(WORKSPACE_DIR):
        for f in files:
            file_path = os.path.join(root, f)
            initial_workspace.add(file_path)
    assistant_reply = ""
    finished = False
    exe_output = None
    while not finished:
        response = client.chat.completions.create(
            model=MODEL_PATH,
            messages=processed_messages,
            temperature=0.4,
            stream=True,
            max_tokens=32768,
        )
        cur_res = ""
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content is not None:
                delta = chunk.choices[0].delta.content
                # Sanitize the delta content before adding to the response
                delta = sanitize_model_output(delta)
                cur_res += delta
                assistant_reply += delta
                yield delta
            if "</Answer>" in cur_res:
                finished = True
                break
        if chunk.choices[0].finish_reason == "stop" and not finished:
            if not cur_res.endswith("</Code>"):
                missing_tag = "</Code>"
                cur_res += missing_tag
                assistant_reply += missing_tag
                yield missing_tag
        if "</Code>" in cur_res and not finished:
            processed_messages.append({"role": "assistant", "content": cur_res})
            code_match = re.search(r"<Code>(.*?)</Code>", cur_res, re.DOTALL)
            if code_match:
                code_content = code_match.group(1).strip()
                md_match = re.search(r"```(?:python)?(.*?)```", code_content, re.DOTALL)
                code_str = md_match.group(1).strip() if md_match else code_content
                code_str = Chinese_matplot_str + "\n" + code_str
                # 执行前快照（路径 -> (size, mtime)）
                try:
                    before_state = {
                        p.resolve(): (p.stat().st_size, p.stat().st_mtime_ns)
                        for p in Path(WORKSPACE_DIR).rglob("*")
                        if p.is_file()
                    }
                except Exception:
                    before_state = {}
                # 在子进程中以固定工作区执行
                exe_output = execute_code_safe(code_str, WORKSPACE_DIR)
                # 执行后快照
                try:
                    after_state = {
                        p.resolve(): (p.stat().st_size, p.stat().st_mtime_ns)
                        for p in Path(WORKSPACE_DIR).rglob("*")
                        if p.is_file()
                    }
                except Exception:
                    after_state = {}
                # 计算新增与修改
                added_paths = [p for p in after_state.keys() if p not in before_state]
                modified_paths = [
                    p
                    for p in after_state.keys()
                    if p in before_state and after_state[p] != before_state[p]
                ]

                # 将新增和修改的文件移动到 generated 文件夹
                artifact_paths = []
                for p in added_paths:
                    try:
                        # 如果文件不在 generated 文件夹中，移动它
                        if not str(p).startswith(GENERATED_DIR):
                            dest_path = Path(GENERATED_DIR) / p.name
                            dest_path = p
                            shutil.copy2(str(p), str(dest_path))
                            artifact_paths.append(dest_path.resolve())
                        else:
                            artifact_paths.append(p)
                    except Exception as e:
                        print(f"Error moving file {p}: {e}")
                        artifact_paths.append(p)

                # 为修改的文件生成副本并移动到 generated 文件夹
                for p in modified_paths:
                    try:
                        dest_name = f"{Path(p).stem}_modified{Path(p).suffix}"
                        dest_path = Path(GENERATED_DIR) / dest_name
                        dest_path = p
                        shutil.copy2(p, dest_path)
                        artifact_paths.append(dest_path.resolve())
                    except Exception as e:
                        print(f"Error copying modified file {p}: {e}")

                # 旧：Execute 内部放控制台输出；新：追加 <File> 段落给前端渲染卡片
                exe_str = f"\n<Execute>\n```\n{exe_output}\n```\n</Execute>\n"
                file_block = ""
                if artifact_paths:
                    lines = ["<File>"]
                    for p in artifact_paths:
                        try:
                            rel = (
                                Path(p)
                                .relative_to(Path(WORKSPACE_DIR).resolve())
                                .as_posix()
                            )
                        except Exception:
                            rel = Path(p).name
                        # 在相对路径前加上 session_id 前缀
                        url = build_download_url(f"{session_id}/{rel}")
                        name = Path(p).name
                        lines.append(f"- [{name}]({url})")
                        if Path(p).suffix.lower() in [
                            ".png",
                            ".jpg",
                            ".jpeg",
                            ".gif",
                            ".webp",
                            ".svg",
                        ]:
                            lines.append(f"![{name}]({url})")
                    lines.append("</File>")
                    file_block = "\n" + "\n".join(lines) + "\n"
                full_execution_block = exe_str + file_block
                assistant_reply += full_execution_block
                yield full_execution_block
                
                # 检查是否已经生成了Answer标签，如果有则停止循环
                if "</Answer>" in assistant_reply:
                    finished = True
                else:
                    processed_messages.append({"role": "execute", "content": f"{exe_output}"})
                    # 刷新工作区快照（路径集合）
                    current_files = set(
                        os.path.join(WORKSPACE_DIR, f)
                        for f in os.listdir(WORKSPACE_DIR)
                        if os.path.isfile(os.path.join(WORKSPACE_DIR, f))
                    )
                    new_files = list(current_files - initial_workspace)
                    if new_files:
                        initial_workspace.update(new_files)
    os.chdir(original_cwd)


@app.post("/chat/completions")
async def chat(body: dict = Body(...)):
    messages = body.get("messages", [])
    workspace = body.get("workspace", [])
    session_id = body.get("session_id", "default")

    def generate():
        for delta_content in bot_stream(messages, workspace, session_id):
            chunk = {
                "id": "chatcmpl-stream",
                "object": "chat.completion.chunk",  # 标识为流式块
                "created": 1677652288,
                "model": MODEL_PATH,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "content": delta_content  # 直接填入原始内容
                        },
                        "finish_reason": None,  # 传输中为 None
                    }
                ],
            }

            yield json.dumps(chunk) + "\n"
        # 发送结束标记
        end_chunk = {
            "id": "chatcmpl-stream",
            "object": "chat.completion.chunk",
            "created": 1677652288,
            "model": MODEL_PATH,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",  # 结束标记
                }
            ],
        }
        yield json.dumps(end_chunk) + "\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


if __name__ == "__main__":
    import shutil
    uvicorn.run(app, host="0.0.0.0", port=8001)
