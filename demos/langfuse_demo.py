"""本地模型及自托管LangFuse演示：python -m demos.langfuse_demo --invoke。"""
import argparse
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from agents.observability import tracing_config
from config import ClaimLLMFactory
from settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--invoke', action='store_true', help='显式调用配置好的本地模型与LangFuse')
    args = parser.parse_args()
    if not args.invoke:
        print('配置LANGFUSE_ENABLED=true、LANGFUSE_HOST、LANGFUSE_PUBLIC_KEY、LANGFUSE_SECRET_KEY后加--invoke。')
        return
    settings = Settings()
    if not settings.langfuse_enabled or settings.model_provider != 'local':
        raise ValueError('此演示需要开启LangFuse并选择local模型服务')
    config, handler = tracing_config('claims-training-demo', settings)
    prompt = ChatPromptTemplate.from_messages([('system', '你是理赔客服，先确认安全，不承诺赔付。'), ('human', '{input}')])
    chain = prompt | ClaimLLMFactory.create('main') | StrOutputParser()
    try:
        print(chain.invoke({'input': '教学案例：车辆刮擦，报案需准备什么材料？'}, config=config))
        print('真实Token统计：', config['callbacks'][0].snapshot())
    finally:
        if handler:
            handler.flush()
    print('已提交追踪数据；请在自托管LangFuse中检查claims-training-demo会话和嵌套链路。')


if __name__ == '__main__':
    main()
