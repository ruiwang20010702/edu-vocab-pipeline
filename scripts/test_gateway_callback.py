"""测试 Gateway 回调功能.

用法（在服务器上运行）：
    PYTHONPATH=backend python scripts/test_gateway_callback.py

做的事情：
1. 向 Gateway 提交一个简单任务（带 client_callback_url）
2. 打印 Gateway 的提交响应
3. 同时用轮询方式等结果（确认任务能正常完成）
4. 你在服务器日志中观察是否收到回调

前提：
- 后端服务已启动且可通过 callback_url 访问
- .env 中已配置 AI_API_KEY 等
"""

import json
import sys
import time

import httpx

from vocab_qc.core.config import settings


def main():
    if not settings.ai_api_key or not settings.ai_api_base_url:
        print("错误：未配置 AI_API_KEY 或 AI_API_BASE_URL")
        sys.exit(1)

    # 回调地址（改成你的实际地址）
    callback_url = settings.ai_callback_url or input("请输入回调 URL（如 https://s9-vocab-pipeline.51suyang.cn/api/callback/ai-task）: ").strip()
    if not callback_url:
        print("未指定回调 URL，仅测试提交+轮询")

    # 构造请求
    import uuid
    from vocab_qc.core.generators.base import ContentGenerator

    body = {
        "model": settings.ai_model,
        "provider": ContentGenerator._resolve_gateway_provider(settings.ai_model),
        "api_key": settings.ai_api_key,
        "biz_type": settings.ai_gateway_biz_type,
        "biz_id": str(uuid.uuid4()),
        "stream": False,
        "async": True,
        "messages": [
            {"role": "system", "content": [{"type": "text", "text": "你是英语教学助手。返回 JSON: {\"content\": \"...\"}"}]},
            {"role": "user", "content": [{"type": "text", "text": "Word: hello | Meaning: 你好"}]},
        ],
        "temperature": 0.7,
        "response_format": {"type": "json_object"},
    }
    if callback_url:
        body["client_callback_url"] = callback_url

    submit_url = f"{settings.ai_api_base_url}/chat/completions"

    print(f"\n=== 提交任务 ===")
    print(f"URL: {submit_url}")
    print(f"callback_url: {callback_url or '(无)'}")
    print(f"model: {settings.ai_model}")

    # 提交
    with httpx.Client(timeout=30.0, verify=False) as client:
        resp = client.post(submit_url, json=body, headers={"Content-Type": "application/json"})
        print(f"\n状态码: {resp.status_code}")
        data = resp.json()
        print(f"响应: {json.dumps(data, indent=2, ensure_ascii=False)}")

        if data.get("code") != 10000:
            print("提交失败！")
            sys.exit(1)

        task_no = data.get("res")
        if not isinstance(task_no, str):
            print(f"异常：res 不是字符串，而是 {type(task_no).__name__}: {task_no}")
            sys.exit(1)

        print(f"\ntask_no: {task_no}")

        # 轮询等结果（同时观察服务器日志是否收到回调）
        print(f"\n=== 开始轮询（同时观察服务器日志是否收到回调）===")
        poll_url = f"{settings.ai_api_base_url}/chat/task/result"
        poll_body = {
            "provider": body["provider"],
            "model": body["model"],
            "api_key": body["api_key"],
            "biz_type": body["biz_type"],
            "biz_id": body["biz_id"],
            "task_no": task_no,
        }

        for i in range(60):
            time.sleep(3)
            poll_resp = client.post(poll_url, json=poll_body, headers={"Content-Type": "application/json"})
            poll_data = poll_resp.json()
            res = poll_data.get("res", {})

            if isinstance(res, dict):
                status = res.get("status", "?")
                print(f"  轮询 #{i+1}: status={status}")
                if status == "COMPLETED":
                    print(f"\n=== 任务完成 ===")
                    result = res.get("result", {})
                    print(f"result type: {type(result).__name__}")
                    print(f"result: {json.dumps(result, indent=2, ensure_ascii=False)[:1000] if isinstance(result, dict) else str(result)[:1000]}")
                    break
                elif status == "FAILED":
                    print(f"\n=== 任务失败 ===")
                    print(f"reason: {res.get('failed_reason', '?')}")
                    break
            else:
                print(f"  轮询 #{i+1}: res={res}")
        else:
            print("\n轮询超时（3分钟）")

    if callback_url:
        print(f"\n=== 检查服务器日志 ===")
        print(f"在服务器上执行: docker logs <container> | grep '回调详情'")
        print(f"如果看到 '回调详情 task_no={task_no}'，说明回调正常工作")
        print(f"如果没有，说明 Gateway 未触发回调或 URL 不可达")


if __name__ == "__main__":
    main()
