"""Harness stdio entry point; graph and application state belong to Python core."""
import config
import sys
from datanet.core.backend import Backend
from transport import Transport

def main():
    Transport(Backend(sys.argv[1])).run(sys.stdin)

if __name__ == '__main__':
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    main()
