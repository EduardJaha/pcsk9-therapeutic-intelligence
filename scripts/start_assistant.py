"""Run an installed Ollama runtime locally with cloud inference disabled."""
import os
from pathlib import Path
import shutil
import subprocess


def main():
    root = Path(__file__).resolve().parents[1]
    local_binary = root / 'data' / 'ollama' / 'runtime' / ('ollama.exe' if os.name == 'nt' else 'ollama')
    executable = str(local_binary) if local_binary.is_file() else shutil.which('ollama')
    if executable is None:
        raise SystemExit('Install Ollama from https://ollama.com/download, then run this command again.')
    env = dict(os.environ, OLLAMA_HOST='127.0.0.1:11434', OLLAMA_NO_CLOUD='1',
               OLLAMA_MODELS=str(root / 'data' / 'ollama' / 'models'))
    print('Starting local Ollama on 127.0.0.1:11434. Ctrl+C stops it.', flush=True)
    try:
        result = subprocess.run([executable, 'serve'], env=env)
    except KeyboardInterrupt:
        return
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
