"""准备 Tauri 安装包资源（生成 src-tauri/resources/，产物不入库）。

用法（项目根目录）：
    backend/.venv/Scripts/python.exe scripts/prepare-tauri-resources.py

步骤：
1. backend/ → resources/backend/（剔除 .venv / 缓存 / 数据库 / 日志）
2. frontend/ → resources/frontend/（后端同端口托管前端，安装后布局保持同级）
3. 下载 Python embeddable → resources/runtime/（与 venv 同版本，保证 wheel ABI 匹配）
4. 向 runtime/Lib/site-packages 安装生产依赖（requirements.txt 生产部分）

`npm run tauri build` 前必须先跑本脚本；重复执行安全（幂等）。
"""

import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "src-tauri", "resources")
SRC_BACKEND = os.path.join(ROOT, "backend")
SRC_FRONTEND = os.path.join(ROOT, "frontend")

# 与 backend/.venv 解释器同版本（pydantic-core / watchfiles 等二进制 wheel 的 ABI 才匹配）
PY_VERSION = "3.14.6"
EMBED_URL = f"https://www.python.org/ftp/python/{PY_VERSION}/python-{PY_VERSION}-embed-amd64.zip"
RUNTIME = os.path.join(RES, "runtime")
SITE_PKGS = os.path.join(RUNTIME, "Lib", "site-packages")

# 生产依赖（requirements.txt「生产运行」一节；开发/测试依赖不入包）
PROD_DEPS = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "openai>=1.40",
    "pydantic>=2.7",
    "mcp>=1.9",
]

# 复制时剔除的运行时产物
EXCLUDE_DIRS = {".venv", "__pycache__", ".pytest_cache", "data"}
EXCLUDE_FILES = {"server.log"}
EXCLUDE_SUFFIX = (".db", ".db-journal", ".db-wal", ".db-shm", ".sqlite", ".pyc")


def copy_tree(src: str, dst: str) -> int:
    """剔除运行时产物后整树复制，返回复制文件数。"""
    copied = 0
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        rel = os.path.relpath(dirpath, src)
        target_dir = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(target_dir, exist_ok=True)
        for name in filenames:
            if name in EXCLUDE_FILES or name.lower().endswith(EXCLUDE_SUFFIX):
                continue
            shutil.copy2(os.path.join(dirpath, name), os.path.join(target_dir, name))
            copied += 1
    return copied


def fresh_dir(dst: str) -> None:
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    os.makedirs(dst, exist_ok=True)


def download(url: str, dst: str, retries: int = 3) -> None:
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=120) as resp, open(dst, "wb") as f:
                shutil.copyfileobj(resp, f)
            return
        except Exception as e:  # noqa: BLE001
            if attempt == retries:
                raise
            print(f"      下载失败（{e}），重试 {attempt}/{retries} ...")


def patch_pth() -> None:
    """embeddable python 默认不搜 site-packages，改写 ._pth 启用。"""
    for name in os.listdir(RUNTIME):
        if name.endswith("._pth"):
            with open(os.path.join(RUNTIME, name), "w", encoding="utf-8") as f:
                f.write(f"python{PY_VERSION.replace('.', '')[:3]}.zip\n.\nLib/site-packages\nimport site\n")
            print(f"      已改写 {name}（启用 site-packages）")
            return
    raise RuntimeError("runtime 下未找到 ._pth 文件")


def main() -> int:
    print("[1/4] 复制 backend → resources/backend ...")
    fresh_dir(os.path.join(RES, "backend"))
    n1 = copy_tree(SRC_BACKEND, os.path.join(RES, "backend"))

    print("[2/4] 复制 frontend → resources/frontend ...")
    fresh_dir(os.path.join(RES, "frontend"))
    n2 = copy_tree(SRC_FRONTEND, os.path.join(RES, "frontend"))
    print(f"      backend {n1} 个文件，frontend {n2} 个文件")

    if os.path.isfile(os.path.join(RUNTIME, "python.exe")):
        print("[3/4] resources/runtime/python.exe 已存在，跳过下载")
    else:
        zip_path = os.path.join(RES, "_python-embed.zip")
        print(f"[3/4] 下载 Python {PY_VERSION} embeddable ...")
        download(EMBED_URL, zip_path)
        print("      解压 → resources/runtime ...")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(RUNTIME)
        os.remove(zip_path)
        patch_pth()

    if os.path.isfile(os.path.join(SITE_PKGS, ".deps-ok")):
        print("[4/4] 生产依赖已安装，跳过")
    else:
        print("[4/4] 安装生产依赖 → runtime/Lib/site-packages ...")
        fresh_dir(SITE_PKGS)
        cmd = [
            sys.executable, "-m", "pip", "install",
            "--no-warn-script-location", "--target", SITE_PKGS,
            *PROD_DEPS,
        ]
        if subprocess.run(cmd).returncode != 0:
            print("      pip 安装失败")
            return 1
        with open(os.path.join(SITE_PKGS, ".deps-ok"), "w", encoding="utf-8") as f:
            f.write(PY_VERSION + "\n")

    print("完成：src-tauri/resources/ 就绪，可执行 npm run tauri build")
    return 0


if __name__ == "__main__":
    sys.exit(main())
