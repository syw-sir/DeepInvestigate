"""
长期记忆子系统冒烟测试

依赖：
    - Redis Stack 运行中（docker compose up -d redis）
    - Embedder 模型可加载（首次会下载 BGE-M3）

用法：
    cd API
    python -m memory.test_memory
"""

import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def test_redis_ready():
    print("\n[1] Redis ping")
    from memory.redis_client import ping_redis, check_redis_modules
    assert ping_redis(), "Redis not reachable"
    mods = check_redis_modules()
    assert mods.get("search"), f"RediSearch missing! Modules: {mods}"
    print(f"  ✅ Redis OK, modules: {mods.get('all_modules')}")


def test_working_memory():
    print("\n[2] Working Memory")
    from memory import working_memory as wm
    tid = "test_thread_wm"
    assert wm.save(tid, {"step": 1, "note": "测试"}, ttl=60)
    data = wm.get(tid)
    assert data and data.get("step") == 1
    wm.patch(tid, {"step": 2})
    data = wm.get(tid)
    assert data["step"] == 2
    wm.clear(tid)
    assert wm.get(tid) is None
    print("  ✅ working_memory OK")


def test_episodic_memory():
    print("\n[3] Episodic Memory (vector)")
    from memory import episodic_memory as em
    from rag.embedder import get_embedder
    emb = get_embedder()

    user = "test_user_em"
    samples = [
        ("调查发现 SSH 暴力破解，封禁 IP 1.2.3.4", ["ssh", "brute_force"]),
        ("分析 nginx 日志发现 SQL 注入尝试", ["nginx", "sql注入"]),
        ("Linux 主机内存泄漏排查，进程 X 占用过高", ["linux", "performance"]),
    ]
    for text, tags in samples:
        vec = emb.encode_one(text)
        mid = em.add(user, text, vec, tags=tags, thread_id="t_demo")
        assert mid, f"failed to add: {text}"

    # 给 RediSearch 一点点时间索引（HNSW 是同步的，但留点余量）
    time.sleep(0.2)

    results = em.recall(user, "SSH 暴力破解的处理记录", top_k=3)
    print(f"  Recall返回 {len(results)} 条:")
    for r in results:
        print(f"    - score={r.get('score')} tags={r.get('tags')} content={r['content'][:40]}")
    assert results, "no recall results"
    assert any("ssh" in r.get("content", "").lower() or "ssh" in r.get("tags", []) for r in results)
    print(f"  ✅ episodic_memory OK (count={em.count(user)})")


def test_semantic_memory():
    print("\n[4] Semantic Memory (RedisJSON)")
    from memory import semantic_memory as sm
    if not sm._has_redisjson():
        print("  ⚠️  RedisJSON unavailable, skip")
        return
    user = "test_user_sm"
    sm.upsert_profile(user, {"skill_level": "advanced"})
    sm.add_preference(user, "关注 SSH 异常")
    sm.add_preference(user, "关注横向移动")
    sm.increment_investigation(user)
    p = sm.get_profile(user)
    print(f"  Profile: {p}")
    assert p and p["skill_level"] == "advanced"
    assert "关注 SSH 异常" in p["preferences"]
    assert p["stats"]["total_investigations"] >= 1
    print("  ✅ semantic_memory OK")


def test_procedural_memory():
    print("\n[5] Procedural Memory")
    from memory import procedural_memory as pm
    from rag.embedder import get_embedder
    emb = get_embedder()

    desc = "处理 SSH 暴力破解攻击的标准流程"
    vec = emb.encode_one(desc)
    pm.add(
        pattern_id="sop_ssh_bruteforce",
        title="SSH 暴力破解处置 SOP",
        description=desc,
        steps=[
            "1. 识别失败登录次数 Top IP",
            "2. 检查这些 IP 的威胁情报",
            "3. 在 iptables/防火墙封禁",
            "4. 强制涉事账户改密 + 启用 MFA",
        ],
        embedding=vec,
        keywords=["ssh", "brute_force", "暴力破解"],
    )
    time.sleep(0.2)
    results = pm.recall("如何应对 SSH 反复登录失败", top_k=2)
    print(f"  Procedural recall {len(results)} 条:")
    for r in results:
        print(f"    - {r['title']} (score={r.get('score')})")
    assert results
    print("  ✅ procedural_memory OK")


def test_extractor():
    print("\n[6] Memory Extractor")
    from memory.extractor import extract_and_save
    from langchain_core.messages import AIMessage

    fake_state = {
        "user_id": "test_user_ex",
        "thread_id": "t_extract",
        "user_query": "分析 auth.log 是否存在 SSH 暴力破解",
        "plan": ["读取日志", "统计 Failed", "判断模式"],
        "final_answer": "确认存在来自 IP 1.2.3.4 的 SSH 暴力破解攻击，建议封禁。",
        "messages": [
            AIMessage(content="规划完成", name="planner"),
            AIMessage(content="发现 25 次失败登录", name="investigator"),
        ],
    }
    mem_id = extract_and_save(fake_state)
    print(f"  Saved: {mem_id}")
    assert mem_id, "extract_and_save returned None"
    print("  ✅ extractor OK")


def main():
    print("=" * 60)
    print("DeepInvestigate Memory — Smoke Test")
    print("=" * 60)
    test_redis_ready()
    test_working_memory()
    test_episodic_memory()
    test_semantic_memory()
    test_procedural_memory()
    test_extractor()
    print("\n" + "=" * 60)
    print("✅ All memory tests passed")
    print("=" * 60)


if __name__ == "__main__":
    main()
