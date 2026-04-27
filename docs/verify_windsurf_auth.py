#!/usr/bin/env python3
import os, sys, json, shutil, sqlite3, subprocess, time
from pathlib import Path

HOME = Path.home()
WINDSURF_DIR = HOME / ".config/Windsurf"
STATE_VSCDB = WINDSURF_DIR / "User/globalStorage/state.vscdb"
COOKIES = WINDSURF_DIR / "Cookies"
BACKUP_DIR = Path(__file__).parent / ".windsurf_verify_backups"
AUTH_KEYS = ["windsurfAuthStatus","codeium.windsurf","windsurf.settings.cachedPlanInfo"]

def ensure_dir(p): p.mkdir(parents=True, exist_ok=True)

def kill_windsurf():
    subprocess.run(["pkill","-f","windsurf"], capture_output=True)
    time.sleep(0.5)
    if subprocess.run(["pgrep","-f","windsurf"], capture_output=True).stdout.strip():
        subprocess.run(["pkill","-9","-f","windsurf"], capture_output=True)
    time.sleep(0.5)

def read_state(path):
    conn = sqlite3.connect(str(path))
    c = conn.cursor(); c.execute("SELECT key,value FROM ItemTable")
    rows = {k:v for k,v in c.fetchall()}; conn.close()
    return rows

def write_state(path, rows):
    conn = sqlite3.connect(str(path))
    c = conn.cursor()
    for k,v in rows.items():
        c.execute("INSERT OR REPLACE INTO ItemTable (key,value) VALUES (?,?)", (k,v))
    conn.commit(); conn.close()

def backup(name):
    d = BACKUP_DIR / name; ensure_dir(d)
    if STATE_VSCDB.exists(): shutil.copy2(STATE_VSCDB, d / "state.vscdb")
    if COOKIES.exists(): shutil.copy2(COOKIES, d / "Cookies")
    rows = read_state(STATE_VSCDB)
    auth = {}; extra = {}
    for k,v in rows.items():
        sv = v.decode("utf-8","surrogatepass") if isinstance(v,bytes) else v
        if any(a in k for a in AUTH_KEYS): auth[k] = sv
        if "windsurf_auth" in k.lower(): extra[k] = sv
    with open(d/"auth.json","w") as f: json.dump(auth, f, indent=2, ensure_ascii=False)
    with open(d/"extra.json","w") as f: json.dump(extra, f, indent=2, ensure_ascii=False)
    print(f"[backup] {name}: {len(auth)} auth keys, {len(extra)} extra keys")

def cross(a_name, b_name):
    a,b = BACKUP_DIR/a_name, BACKUP_DIR/b_name
    if not a.exists() or not b.exists(): print("先 backup"); return
    md = BACKUP_DIR/f"{a_name}_mixed_{b_name}"; ensure_dir(md)
    shutil.copy2(a/"state.vscdb", md/"state.vscdb")
    with open(b/"auth.json") as f: ba = json.load(f)
    with open(b/"extra.json") as f: be = json.load(f)
    rows = read_state(md/"state.vscdb")
    for k in list(rows):
        if any(a in k for a in AUTH_KEYS) or "windsurf_auth" in k.lower(): del rows[k]
    for k,v in {**ba,**be}.items(): rows[k] = v.encode("utf-8","surrogatepass") if isinstance(v,str) else v
    write_state(md/"state.vscdb", rows)
    print(f"[cross] {md.name}: replaced auth with {b_name}")

def apply(name):
    d = BACKUP_DIR/name
    if not d.exists(): print("备份不存在"); return
    kill_windsurf()
    shutil.copy2(d/"state.vscdb", STATE_VSCDB)
    if (d/"Cookies").exists(): shutil.copy2(d/"Cookies", COOKIES)
    print(f"[apply] 已用 {name} 替换。请手动启动 Windsurf 观察登录态。")

def restore(name):
    d = BACKUP_DIR/name
    if not d.exists(): print("备份不存在"); return
    kill_windsurf()
    shutil.copy2(d/"state.vscdb", STATE_VSCDB)
    if (d/"Cookies").exists(): shutil.copy2(d/"Cookies", COOKIES)
    print(f"[restore] 已恢复 {name}")

def main():
    if len(sys.argv) < 2: print(__doc__); return
    cmd = sys.argv[1]
    if cmd == "backup" and len(sys.argv) >= 3: backup(sys.argv[2])
    elif cmd == "cross" and len(sys.argv) >= 4: cross(sys.argv[2], sys.argv[3])
    elif cmd == "apply" and len(sys.argv) >= 3: apply(sys.argv[2])
    elif cmd == "restore" and len(sys.argv) >= 3: restore(sys.argv[2])
    else: print("用法: backup <name> | cross <a> <b> | apply <name> | restore <name>")

if __name__ == "__main__":
    main()
