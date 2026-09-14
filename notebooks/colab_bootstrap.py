import json, os, subprocess, sys
from pathlib import Path

# Colab bootstrap: clone/pull the repository, install dependencies, and expose src.
REPO=os.getenv("TRADE_AI_REPO","https://github.com/betaanoiar1-gif/trade-ai-.git")
ROOT=Path("/content/trade-ai-")
if not ROOT.exists(): subprocess.run(["git","clone",REPO,str(ROOT)],check=True)
os.chdir(ROOT)
subprocess.run([sys.executable,"-m","pip","install","-e",".[dev]"],check=True)
print(f"Ready: {ROOT}")
print("Configure AI_BASE_URL / AI_API_KEY / AI_MODEL only when an AI provider is available.")
