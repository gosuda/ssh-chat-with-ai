"""Ensure generated gRPC stub uses package-relative import."""

from pathlib import Path


def main() -> None:
    stub = Path(__file__).resolve().parent.parent / "proto" / "middleware_pb2_grpc.py"
    text = stub.read_text()
    fixed = text.replace("import middleware_pb2 as middleware__pb2", "from . import middleware_pb2 as middleware__pb2")
    if text != fixed:
        stub.write_text(fixed)


if __name__ == "__main__":
    main()
