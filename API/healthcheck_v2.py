"""
DeepInvestigate v2.0 基础设施健康检查

用法：
    cd API
    python healthcheck_v2.py

检查项：
    - Redis Stack（含 RediSearch / RedisJSON 模块）
    - ChromaDB
    - Embedder 模型加载
"""

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def check_redis() -> bool:
    print("\n[1/3] Checking Redis Stack ...")
    try:
        from memory.redis_client import ping_redis, check_redis_modules

        if not ping_redis():
            print("  ❌ Redis ping failed")
            return False
        print("  ✅ Redis ping OK")

        mods = check_redis_modules()
        if not mods.get("search"):
            print(f"  ⚠️  RediSearch module not loaded. Use redis/redis-stack image!")
            print(f"     Modules: {mods.get('all_modules')}")
            return False
        print(f"  ✅ Modules OK: {mods.get('all_modules')}")
        return True
    except Exception as e:
        print(f"  ❌ Redis check error: {e}")
        return False


def check_chroma() -> bool:
    print("\n[2/3] Checking ChromaDB ...")
    try:
        from rag.chroma_client import ping_chroma, get_collection

        if not ping_chroma():
            print("  ❌ Chroma heartbeat failed")
            return False
        print("  ✅ Chroma heartbeat OK")

        coll = get_collection()
        print(f"  ✅ Collection '{coll.name}' ready (count={coll.count()})")
        return True
    except Exception as e:
        print(f"  ❌ Chroma check error: {e}")
        return False


def check_embedder() -> bool:
    print("\n[3/3] Checking Embedder ...")
    try:
        from rag.embedder import get_embedder

        emb = get_embedder()
        vec = emb.encode_one("test query")
        print(f"  ✅ Embedder OK: dim={len(vec)}")
        return True
    except Exception as e:
        print(f"  ❌ Embedder check error: {e}")
        return False


def main():
    print("=" * 60)
    print("DeepInvestigate v2.0 Infrastructure Health Check")
    print("=" * 60)

    results = {
        "Redis": check_redis(),
        "Chroma": check_chroma(),
        "Embedder": check_embedder(),
    }

    print("\n" + "=" * 60)
    print("Summary:")
    for k, v in results.items():
        print(f"  {k:10s}: {'✅ OK' if v else '❌ FAIL'}")
    print("=" * 60)

    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main()
