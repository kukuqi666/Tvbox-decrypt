#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TVBox 加密配置接口批量解密器（GitHub Actions / 本地通用）

用途：把"图片隐写 / base64 / 明文"三种加密的 TVBox 配置接口，抓下来解成干净 JSON，
      输出静态文件 + 索引页，供 GitHub Pages 或任意静态托管直接引用（TVBox 填 URL 即用）。

用法：
    python3 decrypt.py <lines.txt> <输出目录> [base_url]

    lines.txt  每行一条：  名称|URL     (名称用于输出文件名 <名称>.json)
    输出目录    解密产物 + index.html 落盘目录
    base_url   索引页里生成绝对地址用（如 https://kukuqi666.github.io/Tvbox-decrypt/mirror）

依赖：curl（Linux/Windows 均内置/常见）
"""
import sys, os, re, json, base64, subprocess, datetime, urllib.parse

UA = "okhttp/3.12.0"                 # 触发上游派发加密包的 UA
TIMEOUT = 60


def fetch(url: str) -> bytes:
    r = subprocess.run(
        ["curl", "-sS", "-L", "--max-time", str(TIMEOUT), "-A", UA, url],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return r.stdout


def json_start(s: bytes) -> int:
    a = s.find(b"{")
    b = s.find(b"[")
    if a == -1:
        return b
    if b == -1:
        return a
    return min(a, b)


def strip_comments(s: str) -> str:
    # 按行删行首注释（splitlines 同时兼容 \r\n / \n，比正则可靠），再删块注释
    keep = [ln for ln in s.splitlines() if not ln.lstrip().startswith("//")]
    s = "\n".join(keep)
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    return s.strip()


def decrypt(body: bytes):
    """返回解密后的配置文本(str)，失败返回 None。"""
    if not body:
        return None
    candidates = []
    # 图片隐写：JPEG EOI(FFD9) 之后附加加密数据
    if body[:2] == b"\xff\xd8":
        pos = body.rfind(b"\xff\xd9")
        if pos != -1 and pos + 2 < len(body):
            candidates.append(body[pos + 2:])
    candidates.append(body)

    for blob in candidates:
        blob = blob.strip()
        if not blob:
            continue
        # 方式A：整段 base64（剔除非 base64 字符，可容忍自定义前缀，解码后找首个 '{'）
        clean = re.sub(rb"[^A-Za-z0-9+/=]", b"", blob)
        if clean and len(clean) >= 4:
            try:
                padded = clean + b"=" * (-len(clean) % 4)
                dec = base64.b64decode(padded)
            except Exception:
                dec = None
            if dec is not None:
                p = json_start(dec)
                if p != -1:
                    return strip_comments(dec[p:].decode("utf-8", "replace"))
        # 方式B：blob 已含明文 JSON
        p = json_start(blob)
        if p != -1:
            return strip_comments(blob[p:].decode("utf-8", "replace"))
    return None


def safe_name(name: str) -> str:
    # 文件名安全化（保留中文，剔除路径危险符）
    name = re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_.")
    return name or "config"


def load_lines(path: str):
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            if "|" in ln:
                name, _, url = ln.partition("|")
            else:
                name, url = ln, ln
            out.append((name.strip(), url.strip()))
    return out


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    lines_file = sys.argv[1]
    out_dir = sys.argv[2]
    base_url = sys.argv[3] if len(sys.argv) > 3 else ""
    os.makedirs(out_dir, exist_ok=True)

    lines = load_lines(lines_file)
    rows = []
    for name, url in lines:
        print(f"[*] {name}: {url}")
        try:
            body = fetch(url)
            txt = decrypt(body)
        except Exception as e:
            txt = None
            print(f"    ! 异常: {e}")
        if txt is None:
            rows.append({"name": name, "url": url, "ok": False,
                         "file": None, "size": 0, "err": "decrypt_failed"})
            print(f"    x 解密失败")
            continue
        fn = safe_name(name) + ".json"
        fp = os.path.join(out_dir, fn)
        with open(fp, "w", encoding="utf-8") as f:
            f.write(txt)
        rows.append({"name": name, "url": url, "ok": True,
                     "file": fn, "size": len(txt), "err": ""})
        print(f"    ok -> {fn} ({len(txt)} 字符)")

    # 生成索引页
    gen_index(out_dir, base_url, rows)
    ok = sum(1 for r in rows if r["ok"])
    print(f"\n完成：{ok}/{len(rows)} 条解密成功 -> {out_dir}")


def gen_index(out_dir: str, base_url: str, rows):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    items = []
    for r in rows:
        if r["ok"]:
            href = (base_url.rstrip("/") + "/" + r["file"]) if base_url else r["file"]
            items.append(
                f'<tr><td><a href="{r["file"]}">{r["file"]}</a></td>'
                f'<td class="ok">✅ 成功</td>'
                f'<td>{r["size"]} 字符</td>'
                f'<td><code>{_esc(r["url"])}</code></td></tr>')
        else:
            items.append(
                f'<tr><td>{r["name"]}</td><td class="fail">❌ 失败</td>'
                f'<td>—</td><td><code>{_esc(r["url"])}</code></td></tr>')
    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TVBox 接口解密镜像</title>
<style>
 body{{margin:0;font-family:-apple-system,"Microsoft YaHei",sans-serif;background:#0f1220;color:#e8eaf0;padding:32px 16px}}
 .wrap{{max-width:960px;margin:0 auto}}
 h1{{font-size:22px}} p.hint{{color:#7a8296;font-size:13px}}
 table{{width:100%;border-collapse:collapse;margin-top:16px;font-size:13px}}
 th,td{{text-align:left;padding:9px 10px;border-bottom:1px solid #232a40}}
 th{{color:#9aa3b8;font-size:12px}}
 code{{font-size:11px;color:#8ab4ff;word-break:break-all}}
 a{{color:#6ea8ff;text-decoration:none}}
 .ok{{color:#49c97b}} .fail{{color:#ff6b6b}}
</style></head><body><div class="wrap">
<h1>TVBox 接口解密镜像</h1>
<p class="hint">由 GitHub Actions 定时抓取并解密生成。把下面任一 .json 地址填进 TVBox「配置地址」即可直接使用（原站挂了也不受影响）。最后刷新：{now}</p>
<table><tr><th>文件</th><th>状态</th><th>大小</th><th>源接口</th></tr>
{''.join(items)}
</table></div></body></html>"""
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


if __name__ == "__main__":
    main()