import os
import sys

value = sys.stdin.readline().strip()
if not value:
    print("no_token_received")
    sys.exit(1)
path = "/home/ubuntu/.hf_token_raqim"
with open(path, "w", encoding="utf-8") as f:
    f.write(value + "\n")
os.chmod(path, 0o600)
print("token_saved")
