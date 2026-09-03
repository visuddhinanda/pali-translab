# -*- coding: utf-8 -*-
"""把本地文件当附件寄出去——打包完直接发一封信，不用再手动 scp。

只用标准库（smtplib + email），不引入依赖。

凭据不进仓库，放 `~/.mailer.json`（权限 600）：

    {
      "host": "smtp.gmail.com",
      "port": 587,
      "user": "you@gmail.com",
      "password": "应用专用密码，不是账号密码",
      "from": "you@gmail.com",
      "to": ["someone@example.com", "other@example.com"]
    }

每一项都能用环境变量盖掉（cron 里方便）：
MAILER_HOST / MAILER_PORT / MAILER_USER / MAILER_PASSWORD / MAILER_FROM / MAILER_TO

用法：
    python3 scripts/mail_file.py workspace/dn-pathikavagga.tar.xz
    python3 scripts/mail_file.py a.tar.xz b.epub --to x@y.com --subject "波梨品"
    python3 scripts/mail_file.py workspace/x.tar.xz --dry-run   # 只演算，不连服务器

关于体积：附件要 base64 编码，实际发出去的字节约为原文件的 4/3。收件方的上限普遍
是 25 MB（Gmail、QQ 邮箱都是），所以这里按**编码后**的大小拦，超了就直接报错——
与其发出去被退回，不如发之前就知道。
"""
import argparse
import datetime
import json
import mimetypes
import os
import smtplib
import ssl
import sys
import tarfile
from email.message import EmailMessage

CONF = os.path.expanduser("~/.mailer.json")
DEFAULT_LIMIT_MB = 25.0          # 收件方常见上限（编码后）
ENV = {"host": "MAILER_HOST", "port": "MAILER_PORT", "user": "MAILER_USER",
       "password": "MAILER_PASSWORD", "from": "MAILER_FROM", "to": "MAILER_TO"}


def load_conf():
    conf = {}
    if os.path.exists(CONF):
        with open(CONF, encoding="utf-8") as f:
            conf = json.load(f)
        mode = os.stat(CONF).st_mode & 0o777
        if mode & 0o077:
            print(f"⚠ {CONF} 权限是 {mode:o}，建议 chmod 600（里面有密码）",
                  file=sys.stderr)
    for k, env in ENV.items():
        if os.environ.get(env):
            conf[k] = os.environ[env]
    conf["port"] = int(conf.get("port") or 587)
    conf["to"] = as_list(conf.get("to"))
    return conf


def as_list(v):
    """收件人可以写成一个字符串、逗号分隔的一串，或一个数组，统一成列表。"""
    if not v:
        return []
    if isinstance(v, str):
        v = v.replace("；", ";").replace("，", ",").replace(";", ",").split(",")
    return [x.strip() for x in v if x and x.strip()]


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024


def manifest(path):
    """tar 包就列出顶层目录的文件数与体积，让收信人不解压也知道里面是什么。"""
    if not tarfile.is_tarfile(path):
        return ""
    tops, total = {}, 0
    try:
        with tarfile.open(path) as tf:
            for m in tf:
                if not m.isfile():
                    continue
                total += 1
                parts = m.name.split("/")
                key = "/".join(parts[:2]) if len(parts) > 2 else parts[0]
                cnt, size = tops.get(key, (0, 0))
                tops[key] = (cnt + 1, size + m.size)
    except (tarfile.TarError, OSError) as e:
        return f"（清单读不出来：{e}）\n"
    lines = [f"包内 {total} 个文件："]
    for k in sorted(tops):
        cnt, size = tops[k]
        lines.append(f"  {k}/  {cnt} 个文件  {human(size)}")
    return "\n".join(lines) + "\n"


def build(files, sender, to, subject, body_extra):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    msg["Date"] = datetime.datetime.now().astimezone().strftime("%a, %d %b %Y %H:%M:%S %z")

    body = [body_extra] if body_extra else []
    for p in files:
        body.append(f"{os.path.basename(p)}  {human(os.path.getsize(p))}")
        m = manifest(p)
        if m:
            body.append(m)
    body.append("——由 pali-translab 自动寄出")
    msg.set_content("\n".join(body))

    for p in files:
        ctype, _ = mimetypes.guess_type(p)
        maintype, _, subtype = (ctype or "application/octet-stream").partition("/")
        with open(p, "rb") as f:
            msg.add_attachment(f.read(), maintype=maintype, subtype=subtype,
                               filename=os.path.basename(p))
    return msg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", help="要当附件寄的文件")
    ap.add_argument("--to", action="append", help="收件人（可重复），默认取配置里的 to")
    ap.add_argument("--subject", help="标题，默认用第一个附件的文件名")
    ap.add_argument("--body", default="", help="正文开头附加的一段话")
    ap.add_argument("--max-mb", type=float, default=DEFAULT_LIMIT_MB,
                    help=f"编码后体积上限 MB（默认 {DEFAULT_LIMIT_MB}）")
    ap.add_argument("--dry-run", action="store_true", help="只演算体积与收发信人，不连服务器")
    args = ap.parse_args()

    missing = [p for p in args.files if not os.path.isfile(p)]
    if missing:
        sys.exit("找不到文件：" + "，".join(missing))

    conf = load_conf()
    to = as_list(args.to) or conf.get("to") or []
    sender = conf.get("from") or conf.get("user")
    if not to:
        sys.exit(f"没有收件人：用 --to 指定，或写进 {CONF} 的 to")
    if not sender:
        sys.exit(f"没有发件人：写进 {CONF} 的 from")

    subject = args.subject or os.path.basename(args.files[0])
    msg = build(args.files, sender, to, subject, args.body)

    raw = len(bytes(msg))
    print(f"发件 {sender} → 收件 {', '.join(to)}")
    print(f"标题 {subject}")
    print(f"附件 {len(args.files)} 个，原始 "
          f"{human(sum(os.path.getsize(p) for p in args.files))}，"
          f"编码后整封 {human(raw)}")
    if raw > args.max_mb * 1024 * 1024:
        sys.exit(f"✗ 整封 {human(raw)} 超过上限 {args.max_mb} MB——"
                 "换成分卷（split -b 15m）或改传网盘，别指望发出去")
    if args.dry_run:
        print("（--dry-run，没有真的发）")
        return

    if not conf.get("host") or not conf.get("user") or not conf.get("password"):
        sys.exit(f"缺 host / user / password，请补进 {CONF}")

    ctx = ssl.create_default_context()
    try:
        if conf["port"] == 465:
            with smtplib.SMTP_SSL(conf["host"], conf["port"], context=ctx, timeout=60) as s:
                s.login(conf["user"], conf["password"])
                s.send_message(msg)
        else:
            with smtplib.SMTP(conf["host"], conf["port"], timeout=60) as s:
                s.starttls(context=ctx)
                s.login(conf["user"], conf["password"])
                s.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        # Gmail 开了两步验证后，账号密码是登不上的，必须用应用专用密码
        sys.exit("✗ 认证失败：Gmail 需要「应用专用密码」，不是账号密码"
                 "（https://myaccount.google.com/apppasswords）")
    except (smtplib.SMTPException, OSError) as e:
        sys.exit(f"✗ 发送失败：{type(e).__name__}: {e}")
    print("✓ 已寄出")


if __name__ == "__main__":
    main()
