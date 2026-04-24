"""批量清理导出文件：只保留 email，删除 password 等其他字段"""

import json
from pathlib import Path


def clean_exports(export_dir: str | Path) -> None:
    export_dir = Path(export_dir)
    if not export_dir.is_dir():
        print(f"目录不存在: {export_dir}")
        return

    json_files = sorted(export_dir.glob("*.json"))
    if not json_files:
        print("未找到 JSON 文件")
        return

    for f in json_files:
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        # 兼容两种格式：[{email, password}, ...] 和 [email, ...]
        if isinstance(data, list):
            cleaned = []
            for item in data:
                if isinstance(item, dict) and "email" in item:
                    cleaned.append({"email": item["email"]})
                elif isinstance(item, str):
                    cleaned.append({"email": item})  # 纯邮箱也转为对象
                else:
                    cleaned.append(item)

            with open(f, "w", encoding="utf-8") as fh:
                json.dump(cleaned, fh, indent=2, ensure_ascii=False)

            removed = len([x for x in data if isinstance(x, dict) and len(x) > 1])
            print(f"✓ {f.name}: {len(cleaned)} 个邮箱, 清理了 {removed} 条含多余字段记录")
        else:
            print(f"⚠ {f.name}: 格式不符合预期，跳过")


if __name__ == "__main__":
    clean_exports(Path(__file__).resolve().parent.parent / "dist" / "exports")
