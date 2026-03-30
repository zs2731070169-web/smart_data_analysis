from argparse import ArgumentParser


def read_cli_args() -> str:
    parser = ArgumentParser(description="接收用户从终端输入参数")
    parser.add_argument("-c", "--conf")
    args = parser.parse_args()
    return args.conf
