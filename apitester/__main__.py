#!/usr/bin/env python3
"""APITester CLI — python -m apitester <command> [args]

Commands:
  collect  <base_url> <api_key> <model>  — 数据采集
  judge    <yaml_path>                   — LLM 评判
  render   <yaml_path>                   — 渲染 Markdown 报告
  flagship                                — 旗舰模型综合对比报告
"""
import sys
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    # 剥掉命令名，让子命令的 argparse 从正确位置开始解析
    sys.argv = [sys.argv[0]] + sys.argv[2:]

    if cmd == "collect":
        from apitester.collector import main as cli
        cli()
    elif cmd == "judge":
        from apitester.judge import main as cli
        cli()
    elif cmd == "render":
        from apitester.renderer import main as cli
        cli()
    elif cmd == "flagship":
        from apitester.reports.flagship import main as cli
        cli()
    else:
        print(f"未知命令: {cmd}\n{__doc__}")
        sys.exit(1)


if __name__ == "__main__":
    main()
