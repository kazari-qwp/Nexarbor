"""Bounded unittest collector for network authors; fixture prepared by the host."""
import ast,os,sys,unittest
from pathlib import Path


def main():
    folder=Path(sys.argv[1]).resolve();os.chdir(folder)
    for file in (folder/'tests').rglob('*.py'):
        ast.parse(file.read_text(encoding='utf-8'),filename=str(file))
    sys.path.insert(0,str(folder))
    suite=unittest.defaultTestLoader.discover(str(folder/'tests'),pattern='test_*.py') if (folder/'tests').is_dir() else unittest.TestSuite()
    if (folder/'tests').is_dir() and any((folder/'tests').glob('test_*.py')) and not suite.countTestCases():
        raise ValueError('测试文件未收集到 unittest 用例')
    result=unittest.TextTestRunner(stream=sys.stdout,verbosity=2).run(suite)
    if not result.wasSuccessful():raise SystemExit(1)
    print('PASS：网络真实运行时行为测试；测试数量：'+str(suite.countTestCases()))


if __name__=='__main__':main()
