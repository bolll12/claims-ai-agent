"""培训材料明确交付物的存在性检查，防止后续目录调整遗漏文件。"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_required_packages_have_init() -> None:
    for package in ("agents", "tools", "prompts", "models", "tests"):
        assert (ROOT / package / "__init__.py").is_file(), package


def test_material_code_and_diagram_deliverables_exist() -> None:
    files = {
        "app.py", "config.py", "settings.py", "requirements.txt", "claims_agent.py",
        "confidence_system.py", "agents/claim_agent.py", "agents/risk_agent.py",
        "agents/confidence.py", "agents/middleware.py", "agents/middleware_audit.py",
        "agents/deep_claims_agent.py", "agents/memory.py", "tools/policy_tool.py",
        "tools/claim_tool.py", "tools/medical_tool.py", "tools/rag_retrieval.py",
        "tools/claim_write_producer.py", "models/schemas.py", "models/parsers.py",
        "prompts/review_prompt.py", "prompts/risk_prompt.py", "demos/module02_demo.py",
        "demos/module04_demo.py", "demos/module05_demo.py", "demos/langfuse_demo.py",
        "demos/LangFuse使用流程.md", "demos/RAG五大核心流程图.md",
        "demos/理赔Agent端到端状态机图.md", "demos/理赔状态机图.md",
        "demos/置信度评估系统架构图.md", "demos/本地部署架构图.md",
        "adapters/legacy_adapter.py", "deploy/shadow_mode.py",
        "deploy/regression_gate.py", "Dockerfile", "docker-compose.yml",
        "docker-compose.langfuse.yml", "deploy.sh", "health_check.py",
        "monitoring.py", "deploy/alerting.yaml", "deploy/runbook.md",
        ".github/workflows/deploy.yml", "isolated_deep/runtime.py",
        "isolated_deep/requirements.txt",
    }
    missing = sorted(name for name in files if not (ROOT / name).is_file())
    assert not missing, missing
