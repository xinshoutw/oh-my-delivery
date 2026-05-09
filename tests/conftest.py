import os

os.environ.setdefault("SERVER_SECRET", "x" * 32)
os.environ.setdefault("JWT_SECRET", "y" * 32)
os.environ.setdefault("ENV", "test")
