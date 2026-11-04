# -*- coding: utf-8 -*-
"""上传 Release 附件。

为什么单独用 Python 传：
    PowerShell 调 Invoke-RestMethod 时，文件名里的中文会被转成
    "PDF工作台-1.0.0-Windows.zip" -> "PDF.-1.0.0-Windows.zip"，
    上传后 GitHub 上就是这个名字，用户下载会看到一个莫名其妙的点。
    用 Python 显式 quote 文件名，字节层面可控。
"""

import json
import os
import sys
import urllib.parse
import urllib.request

API = "https://api.github.com"


def request(url, token, method="GET", data=None, content_type=None):
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "pdfstudio-release")
    if content_type:
        req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            body = resp.read()
            return json.loads(body.decode("utf-8")) if body else {}
    except urllib.error.HTTPError as exc:
        sys.stderr.write("HTTP %d: %s\n" % (exc.code, exc.read().decode("utf-8", "replace")))
        raise


def main():
    token = os.environ.get("GH_TOKEN")
    if not token:
        sys.stderr.write("没有 GH_TOKEN\n")
        return 1

    owner, repo, tag = "ua11235-ops", "pdfstudio-uos", "v1.0.0"
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    path = sys.argv[2]
    if not os.path.isabs(path):
        path = os.path.join(root, path)
    if not os.path.isfile(path):
        sys.stderr.write("找不到文件：%s\n" % path)
        return 1

    release = request("%s/repos/%s/%s/releases/tags/%s" % (API, owner, repo, tag), token)
    rel_id = release["id"]
    name = os.path.basename(path)

    existing = [a for a in release.get("assets", []) if a["name"] == name]
    for asset in existing:
        print("删除同名旧附件：%s" % asset["name"])
        request("%s/repos/%s/%s/releases/assets/%d" % (API, owner, repo, asset["id"]),
                token, method="DELETE")

    print("上传 %s (%.1f MB)" % (name, os.path.getsize(path) / 1048576.0))
    query = urllib.parse.urlencode({"name": name})
    url = "https://uploads.github.com/repos/%s/%s/releases/%d/assets?%s" % (
        owner, repo, rel_id, query)
    with open(path, "rb") as fh:
        payload = fh.read()
    asset = request(url, token, method="POST", data=payload,
                    content_type="application/octet-stream")
    print("    OK %s  %.1f MB" % (asset["name"], asset["size"] / 1048576.0))
    print("    下载：%s" % asset["browser_download_url"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
