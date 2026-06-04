"""
Utility functions for DeepAnalyze API Server
Contains helper functions for file operations, workspace management, and more
"""

import os
import json
import re
import shutil
import sys
import traceback
import subprocess
import tempfile
import http.server
import socketserver
import asyncio
import yaml
from pathlib import Path
from urllib.parse import quote
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from functools import partial

try:
    from config_deepseek import WORKSPACE_BASE_DIR, HTTP_SERVER_PORT
except ImportError:
    from .config_deepseek import WORKSPACE_BASE_DIR, HTTP_SERVER_PORT


base_system_prompt = '''
# 强制指令：你是DeepInvestigate，一个面向复杂任务分析的智能体，必须严格遵循以下格式和工作流回答问题！不要过度思考，完成用户核心任务即可！任何回答中不准出现任何<Analyze>  <OODA>  <Code>  <Execute>  <Answer>标签的字样！

      ## 核心原则
      - 所有输出必须严格使用指定标签，否则将被系统拒绝
      - 标签内容中不得包含其他标签
      - 事实性问题必须通过代码验证，禁止直接回答
      - 注意用户原始问题如果简单，那么最终的回答要简约。只要明确回答问题即可，answer不必过度

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
      - **决策**：分析当前结果是否达到用户预期，基于分析确定下一步最优行动，调整任务策略与优先级
      - **行动**：指导后续代码生成或分析方向，优化步骤序列节奏
      - 每次收到`<Analyze>`或`<Execute>`后必须立即使用`<OODA>`进行深度思考
      - 必须对当前状态进行逻辑分析，评估任务完成度，动态调整后续步骤
      - 不要过度思考，完成用户任务即可
      - 要有长远的对目标任务进展的反思，但是对下一步动作的规划要明确、简洁，不要要求后续的一个步骤做过于复杂的目标
      - 该部分内容中不要出现任何其他标签的名字
      - OODA每个部分换行，每个部分之间用空行隔开
      - 示例：
        ```
        <OODA>
        **观察**：销售数据包含5个字段（产品ID、类别、销售额、日期、地区），共有1000条记录，无缺失值。
        **调整**：数据结构清晰完整，当前完成度约30%。需要深入分析各类别销售额分布，识别核心业务模式。
        **决策**：下一步应计算各产品类别的销售额占比，使用可视化分析Top 3类别趋势。
        **行动**：接下来，需要重点关注类别字段的聚合计算和趋势可视化。
        </OODA>
        ```

      ### <Code>（生成可执行代码）
      - 必须使用 ```python ``` 格式包裹
      - 代码必须完整可执行
      - 注意生成的代码、脚本不允许有任何危害系统的行为，涉及对系统的操作只能在明确授权的情况下进行，禁止直接执行对系统进行修改、删除、重启等操作。
      - 仅在需要数据操作时使用
      - 代码在完成任务的基础上要尽量简洁
      - 代码不要假设依赖任何外部工具，出发有明确的指示
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


def load_prompt(prompt_name: str) -> str:
    """Load prompt content from config.yaml
    
    Args:
        prompt_name: Name of the prompt to load. Available options:
            - "base_system": 基础系统提示 (backend_deepseek.py, utils.py基础功能)
            - "investigation_scenario": 调查场景扩展 (utils.py)
    
    Returns:
        Prompt content as string
    """
    try:
        # Get the directory of this file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_dir, "config.yaml")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # Navigate through the structure: prompts -> prompt_name -> content
        if "prompts" in config and prompt_name in config["prompts"]:
            return config["prompts"][prompt_name]["content"]
        else:
            raise KeyError(f"Prompt '{prompt_name}' not found in configuration")
            
    except Exception as e:
        print(f"Warning: Failed to load prompt '{prompt_name}': {e}")
        # Return fallback prompts
        fallback_prompts = {
            "base_system": "# 强制指令：你是DeepInvestigate自主调查智能体，必须严格遵循以下格式和工作流回答问题！\n\n## 核心原则\n- 所有输出必须严格使用指定标签，否则将被系统拒绝",
            "investigation_scenario": "## 调查场景：主机安全与系统状态调查"
        }
        return fallback_prompts.get(prompt_name, f"# Error: Prompt '{prompt_name}' not found")


def get_thread_workspace(thread_id: str) -> str:
    """Get workspace directory for a thread"""
    workspace_dir = os.path.join(WORKSPACE_BASE_DIR, thread_id)
    os.makedirs(workspace_dir, exist_ok=True)
    
    # Create subdirectories
    os.makedirs(os.path.join(workspace_dir, "uploaded"), exist_ok=True)
    os.makedirs(os.path.join(workspace_dir, "generated"), exist_ok=True)
    os.makedirs(os.path.join(workspace_dir, "context"), exist_ok=True)
    
    return workspace_dir


def build_download_url(thread_id: str, rel_path: str) -> str:
    """Build download URL for a file"""
    try:
        encoded = quote(f"{thread_id}/{rel_path}", safe="/")
    except Exception:
        encoded = f"{thread_id}/{rel_path}"
    # 生成正确的下载 URL
    # 注意：0.0.0.0 不是可访问的客户端地址，使用 localhost 或实际 IP
    return f"http://localhost:{HTTP_SERVER_PORT}/{encoded}"


def uniquify_path(target: Path) -> Path:
    """Return a unique path if target already exists"""
    if not target.exists():
        return target
    
    counter = 1
    stem = target.stem
    suffix = target.suffix
    parent = target.parent
    
    while True:
        new_path = parent / f"{stem}_{counter}{suffix}"
        if not new_path.exists():
            return new_path
        counter += 1


def _normalize_openai_message_content(raw_content: Any) -> str:
    """Normalize OpenAI-style message content into a plain string."""
    if isinstance(raw_content, list):
        parts: List[str] = []
        for item in raw_content:
            if (
                isinstance(item, dict)
                and item.get("type") == "text"
                and "text" in item
            ):
                parts.append(item.get("text", {}).get("value", ""))
        return "".join(parts)
    return str(raw_content or "")


def extract_text_from_content(content: List[Dict[str, Any]]) -> str:
    """Extract plain text from message content items."""
    text_parts: List[str] = []
    for item in content or []:
        if isinstance(item, dict) and item.get("type") == "text":
            text_parts.append(item.get("text", {}).get("value", ""))
    return "".join(text_parts)


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




def prepare_vllm_messages(
    messages: List[Dict[str, Any]],
    workspace_dir: str,
) -> List[Dict[str, str]]:
    """
    Convert incoming messages to vLLM format and inject DeepAnalyze template:
    - Always wrap user message with "# Instruction" heading
    - Optionally append workspace file info under "# Data"
    - Add strong system prompt to enforce DeepSeek to generate required tags
    """
    # Add a very strong system prompt to enforce tag generation
    # Load prompts from YAML configuration
    core_prompt = base_system_prompt
    investigation_prompt = load_prompt("investigation_scenario")
    
    # Combine the prompts with a separator
    system_prompt = f"{core_prompt}\n\n---\n\n{investigation_prompt}"
    
    # Initialize messages with system prompt
    vllm_messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_prompt}
    ]
    
    # Process user and assistant messages
    for msg in messages:
        role = msg.get("role") if isinstance(msg, dict) else None
        raw_content = msg.get("content") if isinstance(msg, dict) else None
        content = _normalize_openai_message_content(raw_content)
        if role:
            vllm_messages.append({"role": role, "content": content})

    # Locate last user message
    last_user_idx: Optional[int] = None
    for idx in range(len(vllm_messages) - 1, -1, -1):
        if vllm_messages[idx].get("role") == "user":
            last_user_idx = idx
            break

    # 只收集uploaded子目录的文件信息
    uploaded_dir = os.path.join(workspace_dir, "uploaded")
    workspace_file_info = collect_file_info(uploaded_dir)

    if last_user_idx is not None:
        user_content = str(vllm_messages[last_user_idx].get("content", "")).strip()
        instruction_body = user_content if user_content else "# Instruction"
        if workspace_file_info:
            vllm_messages[last_user_idx]["content"] = (
                f"# Instruction\n{instruction_body}\n\n# Data\n{workspace_file_info}"
            )
        else:
            vllm_messages[last_user_idx]["content"] = f"# Instruction\n{instruction_body}"

    return vllm_messages


def execute_code_safe(
    code_str: str, workspace_dir: str, timeout_sec: int = 120
) -> str:
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


async def execute_code_safe_async(
    code_str: str, workspace_dir: str, timeout_sec: int = 120
) -> str:
    """Execute Python code in a separate process with timeout (async version)"""
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

        # Use asyncio.subprocess for non-blocking execution
        process = await asyncio.create_subprocess_exec(
            sys.executable, tmp_path,
            cwd=exec_cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=child_env,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_sec
            )
            # 尝试用utf-8解码，如果失败则用gbk解码，解决中文乱码问题
            output = ""
            if stdout:
                try:
                    output += stdout.decode('utf-8')
                except UnicodeDecodeError:
                    output += stdout.decode('gbk', 'ignore')
            if stderr:
                try:
                    output += stderr.decode('utf-8')
                except UnicodeDecodeError:
                    output += stderr.decode('gbk', 'ignore')
            return output
        except asyncio.TimeoutError:
            # Kill the process if it times out
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass
            return f"[Timeout]: execution exceeded {timeout_sec} seconds"
    except Exception as e:
        return f"[Error]: {str(e)}"
    finally:
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


def extract_code_from_segment(segment: str) -> Optional[str]:
    """Extract python code between <Code>...</Code>, optionally fenced by ```python ... ```"""
    code_match = re.search(r"<Code>(.*?)</Code>", segment, re.DOTALL)
    if not code_match:
        return None
    code_content = code_match.group(1).strip()
    md_match = re.search(r"```(?:python)?(.*?)```", code_content, re.DOTALL)
    return (md_match.group(1).strip() if md_match else code_content)


def fix_tags_and_codeblock(s: str) -> str:
    """Fix unclosed tags and code blocks"""
    # 定义允许的标签
    allowed_tags = ['Analyze', 'OODA', 'Code', 'Answer']
    
    # 使用栈来跟踪未闭合的标签
    stack = []
    i = 0
    while i < len(s):
        # 检查是否匹配开始标签
        match_start = None
        for tag in allowed_tags:
            if s.startswith(f'<{tag}>', i):
                match_start = tag
                break
        if match_start:
            stack.append(match_start)
            i += len(f'<{match_start}>')
            continue
        
        # 检查是否匹配结束标签
        match_end = None
        for tag in allowed_tags:
            if s.startswith(f'</{tag}>', i):
                match_end = tag
                break
        if match_end:
            # 如果栈顶是匹配的开始标签，则弹出
            if stack and stack[-1] == match_end:
                stack.pop()
            # 否则忽略不匹配的结束标签（可能是多余的）
            i += len(f'</{match_end}>')
            continue
        
        # 否则移动到下一个字符
        i += 1
    
    # 在字符串末尾添加缺失的结束标签（按相反顺序）
    result = s
    for tag in reversed(stack):
        result += f'\n</{tag}>'
    
    # 额外处理 Code 标签中的未闭合代码块
    if 'Code' in stack or '</Code>' not in result:
        # 检查代码块是否闭合
        if '```' in result and result.count('```') % 2 != 0:
            result += '\n```'
    
    return result


def sanitize_model_output(s: str) -> str:
    """
    Sanitize model output by:
    1. Only preserving the outermost action tags (except Execute which is system-generated)
    2. Escaping inner tags to prevent page misinterpretation
    3. Filtering out any model-generated Execute tags
    """
    # First, remove any model-generated Execute tags completely
    s = re.sub(r"<Execute>(.*?)</Execute>", "", s, flags=re.DOTALL)
    
    # Define the action tags we need to handle (Execute is system-generated only)
    action_tags = ['Analyze', 'OODA', 'Code', 'Answer']
    
    # Pattern to find all action tags
    tag_pattern = re.compile(r"<(/?)(" + '|'.join(action_tags) + r")>" , re.IGNORECASE)
    
    # Find all occurrences of action tags
    matches = list(tag_pattern.finditer(s))
    if not matches:
        return s
    
    # Stack to track tag nesting
    tag_stack = []
    result = []
    last_pos = 0
    
    for match in matches:
        start, end = match.span()
        full_tag = match.group(0)
        is_closing = match.group(1) == '/'  # Check if it's a closing tag
        tag_name = match.group(2).capitalize()  # Normalize tag name to uppercase
        
        # Add text before the tag
        result.append(s[last_pos:start])
        
        if is_closing:
            # For closing tags, only keep if it matches the top of the stack
            if tag_stack and tag_stack[-1] == tag_name:
                tag_stack.pop()
                # Keep the closing tag if it's an outer tag
                if not tag_stack:
                    result.append(full_tag)
                else:
                    # Escape inner closing tags
                    result.append(full_tag.replace('<', '&lt;').replace('>', '&gt;'))
            else:
                # Mismatched closing tag, escape it
                result.append(full_tag.replace('<', '&lt;').replace('>', '&gt;'))
        else:
            # For opening tags, only keep if stack is empty (outer tag)
            if not tag_stack:
                tag_stack.append(tag_name)
                result.append(full_tag)
            else:
                # Escape inner opening tags
                result.append(full_tag.replace('<', '&lt;').replace('>', '&gt;'))
        
        last_pos = end
    
    # Add remaining text
    result.append(s[last_pos:])
    
    return ''.join(result)


def extract_sections_from_history(messages: List[Dict[str, str]]) -> str:
    """Build report body and appendix from tagged assistant messages."""
    if not isinstance(messages, list):
        return ""

    parts: List[str] = []
    appendix: List[str] = []
    tag_pattern = re.compile(r"<(Analyze|OODA|Code|Execute|File|Answer)>([\s\S]*?)</\1>")

    # 收集所有用户和助手消息对，用于构建完整的对话历史
    conversation_pairs: List[Dict[str, Any]] = []
    user_message = None

    # 第一轮遍历：收集用户-助手消息对
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = (msg.get("role") or "").lower()
        content = str(msg.get("content", ""))

        if role == "user":
            user_message = content
        elif role == "assistant" and user_message is not None:
            conversation_pairs.append({
                "user": user_message,
                "assistant": content
            })
            user_message = None

    # 第二轮遍历：处理助手响应的标签内容
    # 找到最后一轮对话的Answer内容作为报告主体
    last_answer_content = ""
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        if (msg.get("role") or "").lower() != "assistant":
            continue
        content = str(msg.get("content", ""))

        # 提取所有Answer标签内容，保留最后一次的
        answer_matches = tag_pattern.finditer(content)
        for match in answer_matches:
            tag, segment = match.groups()
            if tag == "Answer":
                segment = (segment or "").strip()
                if segment:
                    last_answer_content = segment

    # 将最后一轮的Answer内容添加到报告主体
    if last_answer_content:
        parts.append(f"{last_answer_content}\n")

    # 构建报告附件：包含所有对话轮次，每轮对话前加上用户指令
    conversation_round = 1
    for pair in conversation_pairs:
        user_content = pair["user"].strip()
        assistant_content = pair["assistant"]

        # 添加用户指令
        appendix.append(f"\n## 对话轮次 {conversation_round}\n\n")
        appendix.append(f"### 用户指令\n\n{user_content}\n\n")
        appendix.append(f"### 助手响应\n\n")

        # 处理助手响应中的标签
        step = 1
        for match in tag_pattern.finditer(assistant_content):
            tag, segment = match.groups()
            segment = (segment or "").strip()
            if not segment:
                continue
            appendix.append(f"#### 步骤 {step}: {tag}\n\n{segment}\n")
            step += 1

        conversation_round += 1

    final_text = "".join(parts).strip()
    if appendix:
        final_text += (
            "\n\n\\newpage\n\n# 附录：完整对话过程\n"
            + "".join(appendix).strip()
        )

    return final_text.strip()


def save_markdown_report(md_text: str, base_name: str, target_dir: Path) -> Path:
    """Persist markdown report under target directory."""
    target_dir.mkdir(parents=True, exist_ok=True)
    md_path = uniquify_path(target_dir / f"{base_name}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_text)
    return md_path




class WorkspaceTracker:
    """Track workspace file changes and collect artifacts into generated/ folder."""

    def __init__(self, workspace_dir: str, generated_dir: str):
        self.workspace_dir = Path(workspace_dir).resolve()
        self.generated_dir = Path(generated_dir).resolve()
        self.generated_dir.mkdir(parents=True, exist_ok=True)
        self.before_state = self._snapshot()

    def _snapshot(self) -> Dict[Path, Tuple[int, int]]:
        try:
            return {
                p.resolve(): (p.stat().st_size, p.stat().st_mtime_ns)
                for p in self.workspace_dir.rglob("*")
                if p.is_file()
            }
        except Exception:
            return {}

    def diff_and_collect(self) -> List[Path]:
        """Compute added/modified files, copy into generated/, and return artifact paths."""
        try:
            after_state = {
                p.resolve(): (p.stat().st_size, p.stat().st_mtime_ns)
                for p in self.workspace_dir.rglob("*")
                if p.is_file()
            }
        except Exception:
            after_state = {}

        added = [p for p in after_state.keys() if p not in self.before_state]
        modified = [
            p for p in after_state.keys()
            if p in self.before_state and after_state[p] != self.before_state[p]
        ]

        artifact_paths: List[Path] = []
        for p in added:
            try:
                if not str(p).startswith(str(self.generated_dir)):
                    dest = self.generated_dir / p.name
                    dest = uniquify_path(dest)
                    shutil.copy2(str(p), str(dest))
                    artifact_paths.append(dest.resolve())
                else:
                    artifact_paths.append(p)
            except Exception as e:
                print(f"Error moving file {p}: {e}")

        for p in modified:
            try:
                dest = self.generated_dir / f"{p.stem}_modified{p.suffix}"
                dest = uniquify_path(dest)
                shutil.copy2(str(p), str(dest))
                artifact_paths.append(dest.resolve())
            except Exception as e:
                print(f"Error copying modified file {p}: {e}")

        self.before_state = after_state
        return artifact_paths


def generate_report_from_messages(
    original_messages: List[Dict[str, Any]],
    assistant_reply: str,
    workspace_dir: str,
    thread_id: str,
    generated_files_sink: Optional[List[Dict[str, str]]] = None,
) -> str:
    """
    Generate markdown report from conversation history and return file block.

    Args:
        original_messages: Original message list from the API request
        assistant_reply: Complete assistant response text
        workspace_dir: Workspace directory path
        thread_id: Thread ID for building download URLs
        generated_files_sink: Optional list to append generated file metadata

    Returns:
        File block string with report link, or empty string on failure
    """
    # Build conversation history for report generation
    history_records: List[Dict[str, str]] = []
    for raw_msg in original_messages:
        role = raw_msg.get("role", "") if isinstance(raw_msg, dict) else ""
        raw_content = raw_msg.get("content", "") if isinstance(raw_msg, dict) else ""
        content_text = _normalize_openai_message_content(raw_content)
        history_records.append({"role": role, "content": content_text})

    history_records.append({"role": "assistant", "content": assistant_reply})

    try:
        md_text = extract_sections_from_history(history_records)
        if not md_text:
            md_text = (
                "(No <Analyze>/<OODA>/<Code>/<Execute>/<File>/<Answer> "
                "sections found.)"
            )

        export_dir = Path(workspace_dir) / "generated"
        export_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"Conversation_Report_{timestamp}"
        report_path = save_markdown_report(md_text, base_name, export_dir)

        try:
            rel = report_path.resolve().relative_to(Path(workspace_dir).resolve())
            rel_path = rel.as_posix()
        except Exception:
            rel_path = report_path.name

        url = build_download_url(thread_id, rel_path)

        if generated_files_sink is not None:
            generated_files_sink.append({"name": report_path.name, "url": url})
        return "\n"

    except Exception as report_error:
        print(f"Report generation error: {report_error}")
        return ""
def render_file_block(
    artifact_paths: List[Path],
    workspace_dir: str,
    thread_id: str,
    generated_files_sink: Optional[List[Dict[str, str]]] = None,
) -> str:
    """Build the <File> markdown block and optionally collect generated file metadata."""
    if not artifact_paths:
        return ""

    file_items = []
    for p in artifact_paths:
        try:
            rel = Path(p).resolve().relative_to(Path(workspace_dir).resolve()).as_posix()
        except Exception:
            rel = Path(p).name
        url = build_download_url(thread_id, rel)
        name = Path(p).name
        
        # 添加文件项到列表
        file_items.append(f"- [{name}]({url})")
        
        if generated_files_sink is not None:
            if {"name": name, "url": url} not in generated_files_sink:
                generated_files_sink.append({"name": name, "url": url})
    
    # 构建 <File> 标签块
    if file_items:
        joined = '\n'.join(file_items)
        return f"\n<File>\n{joined}\n</File>\n"
    
    return ""

def start_http_server():
    os.makedirs(WORKSPACE_BASE_DIR, exist_ok=True)

    # 创建自定义HTTP请求处理器，修复中文乱码问题
    class UTF8SimpleHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
        def end_headers(self):
            # 设置正确的Content-Type头
            path = self.translate_path(self.path)
            if os.path.isfile(path):
                ext = os.path.splitext(path)[1].lower()
                if ext in ['.txt', '.py', '.md', '.json', '.yaml', '.yml', '.csv', '.log']:
                    self.send_header('Content-Type', 'text/plain; charset=utf-8')
            super().end_headers()

    # 使用 ThreadingTCPServer 处理并发
    handler = partial(
        UTF8SimpleHTTPRequestHandler,
        directory=WORKSPACE_BASE_DIR
    )

    with socketserver.ThreadingTCPServer(("", HTTP_SERVER_PORT), handler) as httpd:
        httpd.allow_reuse_address = True
        print(f"HTTP Server serving {WORKSPACE_BASE_DIR} at port {HTTP_SERVER_PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("HTTP server shutting down...")
            httpd.shutdown()