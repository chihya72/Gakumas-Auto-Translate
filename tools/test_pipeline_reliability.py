"""付费翻译前置闸门自检。"""
import json
import os
from unittest.mock import patch

import auto_campus_pipeline as pipeline


def expect_system_exit(fn, contains):
    try:
        fn()
    except SystemExit as exc:
        assert contains in str(exc), exc
    else:
        raise AssertionError("预期 SystemExit，但函数正常返回")


assert pipeline.required_max_tokens("deepseek-v4-pro") == 65536
assert pipeline.required_max_tokens("DEEPSEEK-V4-PRO-0813") == 65536
assert pipeline.required_max_tokens("other-model") == 12288

with patch.dict(os.environ, {"MODEL": "deepseek-v4-pro", "MAX_TOKENS": "65536"}, clear=False):
    assert pipeline.validated_max_tokens() == "65536"

with patch.dict(os.environ, {"MODEL": "deepseek-v4-pro", "MAX_TOKENS": "12288"}, clear=False):
    expect_system_exit(pipeline.validated_max_tokens, "至少 65536")

failed_run = json.dumps({
    "workflow_runs": [{
        "id": 123,
        "conclusion": "failure",
        "html_url": "https://example.invalid/run/123",
    }]
})
scheduled_env = {
    "GITHUB_EVENT_NAME": "schedule",
    "GITHUB_RUN_ATTEMPT": "1",
    "GITHUB_REPOSITORY": "owner/repo",
    "GITHUB_REF_NAME": "master",
}
with patch.dict(os.environ, scheduled_env, clear=False), patch.object(
    pipeline, "out", return_value=failed_run
):
    expect_system_exit(pipeline.guard_repeated_scheduled_failure, "重复扣费")

# 人工 Re-run 明确表示恢复，不能被上一轮失败拦住。
with patch.dict(
    os.environ,
    {**scheduled_env, "GITHUB_RUN_ATTEMPT": "2"},
    clear=False,
), patch.object(pipeline, "out", side_effect=AssertionError("不应查询历史运行")):
    pipeline.guard_repeated_scheduled_failure()

# workflow_dispatch 同样绕过自动防重闸门。
with patch.dict(
    os.environ,
    {**scheduled_env, "GITHUB_EVENT_NAME": "workflow_dispatch"},
    clear=False,
), patch.object(pipeline, "out", side_effect=AssertionError("不应查询历史运行")):
    pipeline.guard_repeated_scheduled_failure()

print("OK: MAX_TOKENS 预检与定时失败防重闸门全部通过")
