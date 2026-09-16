"""模块05本地OpenAI兼容接口接入：聊天和bge-m3 embedding。"""
import argparse
from config import ClaimLLMFactory
from tools.rag_retrieval import create_embeddings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chat', action='store_true')
    parser.add_argument('--embed', action='store_true')
    args = parser.parse_args()
    if not args.chat and not args.embed:
        print('使用--chat请求本地聊天模型，或--embed请求本地bge-m3服务。')
    if args.chat:
        print(ClaimLLMFactory.create('main').invoke('教学问题：理赔报案需要哪些基本信息？').content)
    if args.embed:
        vectors = create_embeddings().embed_documents(['机动车保险责任条款', '住院医疗费用材料'])
        print({'documents': len(vectors), 'dimensions': [len(vector) for vector in vectors]})


if __name__ == '__main__':
    main()
