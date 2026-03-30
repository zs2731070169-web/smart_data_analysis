import asyncio

from infra.factory.repository_factory import repository_factory
from infra.log.logging import logger
from service.knowledge_service import KnowledgeService
from utils.args_utils import read_cli_args


async def run_cli():
    """
    构建索引入口
    :return:
    """
    try:
        # 读取控制台参数
        conf_path = read_cli_args()
        logger.info(f"从命令行接收参数: {conf_path}")
        async with repository_factory as repos:
            # 执行知识库索引构建
            knowledge = KnowledgeService(repos)
            await knowledge.execute(conf_path)
    except Exception as e:
        logger.error(f"构建索引失败: {e}")
        raise

if __name__ == '__main__':
    async def main():
        await run_cli()

    asyncio.run(main())
