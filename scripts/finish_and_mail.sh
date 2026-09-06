#!/usr/bin/env bash
# 等某个项目全部跑完 → 导出 markdown → 打 epub → 打包 → 发邮件。
#
# 守护进程跑完一本书要按小时计，人不可能一直盯着；这个脚本守在旁边，
# 项目文件的 state 变成 done 就自动收尾。中途失败会把原因留在日志里并照样发信，
# 免得「静悄悄什么都没有」。
#
# 用法： nohup bash scripts/finish_and_mail.sh mn-majjhimapannasa 165 131 193 &
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PROJ="$1"; shift
BOOKS=("$@")
PJ="workspace/projects/$PROJ.json"
CH=$(python3 -c "import json;print(json.load(open('$PJ'))['channel'])")

state() { python3 -c "
import json;d=json.load(open('$PJ'))
js=d['jobs']
done=sum(1 for j in js if j.get('status')=='done')   # 作业上的字段是 status，不是 state
print(d.get('state'), done, len(js))"; }

while :; do
    read -r ST DONE TOT <<<"$(state)"
    [[ "$DONE" == "$TOT" ]] && break
    [[ "$ST" == "done" ]] && break
    sleep 300
done
echo "[$(date '+%F %T')] $PROJ 跑完（$DONE/$TOT），开始收尾"

# 导出三层 markdown，再打 epub。
# 附件**只装这一个项目的产物**：它的 markdown 导出、它的 epub、它的过程报告。
# workspace/export 是历次项目共用的目录（长部三卷、中部各本都堆在里面），整个打包
# 等于把别的书一并寄出；epub 同理——build_epub 的 --root 给整个 export，合集里就会
# 混进不相干的书。所以先把本项目写到的书目录挑进一个暂存目录，epub 与打包都只认它。
# 日志（logs / daemon.out / watchdog.log / audit.log）一概不装。
EXP="workspace/export"
STAGE="workspace/export-$PROJ"
EPUB="workspace/epub-$PROJ"
OUTLOG="$(mktemp)"
rm -rf "$STAGE" "$EPUB"; mkdir -p "$STAGE" "$EPUB"

for B in "${BOOKS[@]}"; do
    python3 scripts/export_markdown.py --book "$B" --channel "$CH" --out "$EXP" \
        2>&1 | tee -a "$OUTLOG" || echo "⚠ 导出 book $B 失败"
done

# 本项目写到了哪些书目录，以导出自己打印的路径为准，不靠书名猜
python3 scripts/pick_export.py "$OUTLOG" "$EXP" "$STAGE" || echo "⚠ 挑选导出目录失败"

python3 scripts/build_epub.py --root "$STAGE" --out "$EPUB" --merge "$PROJ 三层合集" \
    || echo "⚠ epub 失败"

# 本项目的过程报告：workspace/reports 下按书号分目录
RPT="workspace/reports-$PROJ"
rm -rf "$RPT"; mkdir -p "$RPT"
for B in "${BOOKS[@]}"; do cp -r "workspace/reports/$B" "$RPT/" 2>/dev/null; done

PKG="workspace/$PROJ.zip"
rm -f "$PKG"
(cd workspace && zip -qr "../$PKG" "export-$PROJ" "epub-$PROJ" "reports-$PROJ") || echo "⚠ 打包失败"
ls -la "$PKG"

python3 scripts/mail_file.py "$PKG" \
    --subject "$PROJ 翻译完成" \
    --body "$PROJ 全部 $TOT 个作业已完成。附件含 markdown 导出、epub 与过程报告。"
echo "[$(date '+%F %T')] 已发信"
