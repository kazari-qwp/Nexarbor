import argparse

from labinsight.agent import run_agent


def main():
    parser = argparse.ArgumentParser(description="运行实验数据分析助手")
    parser.add_argument(
        "question", nargs="?", default="请查询项目 B 的合格率。",
        help="要交给助手的问题",
    )
    args = parser.parse_args()
    run_agent(args.question)


if __name__ == "__main__":
    main()
