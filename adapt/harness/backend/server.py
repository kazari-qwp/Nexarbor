"""并发 stdio RPC 入口；运行目录由宿主明确传入。"""

import sys
from app.runtime.backend import Backend
from .transport import Transport


def main():
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    Transport(Backend(sys.argv[1])).run(sys.stdin)


if __name__ == '__main__':
    main()
