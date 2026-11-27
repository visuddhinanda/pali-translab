#!/usr/bin/env bash
# 等某个项目全部跑完 → 导出 markdown → 打 epub → 打包 → 发邮件。
#
# 守护进程跑完一本书要按小时计，人不可能一直盯着；这个脚本守在旁边，
# 项目文件的 state 变成 done 就自动收尾。中途失败会把原因留在日志里并照样发信，
# 免得「静悄悄什么都没有」。
#
# 用法： nohup bash scripts/finish_and_mail.sh mn-uparipannasa 166 132 194 &
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PROJ="$1"; shift
# 只上传：workspace/UPLOAD_ONLY 在时不导出不发信（收尾已另做过），退出码 4 交给调用方识别
if [[ -f workspace/UPLOAD_ONLY ]]; then echo "UPLOAD_ONLY：$PROJ 只上传，不导出不发信"; exit 4; fi
BOOKS=("$@")
PJ="workspace/projects/$PROJ/project.json"
CH=$(python3 -c "import json;print(json.load(open('$PJ'))['channel'])")

state() { python3 -c "
import json;d=json.load(open('$PJ'))
# schema 3 的调度单位是 task（顶层 tasks），schema 2 是 pipelines
js = d.get('tasks') if d.get('schema') == 3 else d['pipelines']
# 字段是 status 不是 state；skipped / fixed（revise 已补齐的 translate 失败）与 done 同为终态
done=sum(1 for j in js if j.get('status') in ('done', 'skipped', 'fixed'))
print(d.get('state'), done, len(js))"; }

while :; do
    read -r ST DONE TOT <<<"$(state)"
    [[ "$DONE" == "$TOT" ]] && break
    [[ "$ST" == "done" ]] && break
    sleep 300
done
echo "[$(date '+%F %T')] $PROJ 跑完（$DONE/$TOT），开始收尾"

# 一项目一目录：产物全在 workspace/projects/<name>/ 里，打包就是打这一个目录。
# 不用再从公共 export 里挑属于本项目的书（挑错就把别的书一起寄出去）。
# 日志不进附件——收件人要的是成果，不是工作现场。
HOME_DIR="workspace/projects/$PROJ"
EXP="$HOME_DIR/export"
EPUB="$HOME_DIR/epub"
mkdir -p "$EXP" "$EPUB"

# 导出**只能**按本项目负责的段范围来。注释书一本含好几集（book 100 = an2+an3+an4），
# 不给 --from/--to 就是整本导出：同一个 channel 上别的集早翻译过，于是把别集的章
# 一起导进来、打进 zip、合进 epub、寄出去。范围从 project.json 的 layers 现算
# （每本书取 min(start)/max(end)），不另外问 API。
RANGES=$(python3 - "$PJ" <<'PYR'
import json, sys
p = json.load(open(sys.argv[1], encoding='utf-8'))
rng = {}
# schema 3：各层就在顶层 layers，每层一段连续范围
# schema 2：层片段挂在每条流水线下（layers = 本作业负责翻译的层，不含只读的 ref）
groups = ([p.get('layers') or []] if p.get('schema') == 3
          else [j.get('layers') or [] for j in p.get('pipelines', [])])
for g in groups:
    for L in g:
        b, lo, hi = str(L['book']), int(L['start']), int(L['end'])
        o = rng.get(b)
        rng[b] = (min(o[0], lo), max(o[1], hi)) if o else (lo, hi)
for b, (lo, hi) in sorted(rng.items(), key=lambda kv: int(kv[0])):
    print(b, lo, hi)
PYR
)
# translate 只差一两句时流水线不重试、记进 manual_fix.tsv 待人工补：没补完不发信
if ! python3 scripts/manual_fix.py check --project "$PROJ"; then
    echo "⚠ 有句子待人工补（python3 scripts/manual_fix.py list --project $PROJ），本次不导出不发信"
    exit 3
fi

# plan_solo 的项目（藏外单层，project.json 带 seq）：导出前把纯编号句照抄原文补进 channel
if python3 -c "import json,sys;sys.exit(0 if 'seq' in json.load(open('$PJ')) else 1)"; then
    python3 scripts/fill_numbering.py --project "$PROJ" || echo "⚠ 补编号失败"
fi

for B in "${BOOKS[@]}"; do
    R=$(printf '%s\n' "$RANGES" | awk -v b="$B" '$1==b {print $2, $3}')
    if [[ -z "$R" ]]; then
        echo "⚠ book $B 不在 $PROJ 的负责范围里，跳过导出（别集的章不进附件）"
        continue
    fi
    read -r FROM TO <<<"$R"
    echo "导出 book $B 段 $FROM-$TO"
    python3 scripts/export_markdown.py --book "$B" --channel "$CH" --out "$EXP" \
        --from "$FROM" --to "$TO" || echo "⚠ 导出 book $B 失败"
done

python3 scripts/build_epub.py --root "$EXP" --out "$EPUB" --merge "${MERGE_TITLE:-$PROJ 三层合集}" \
    || echo "⚠ epub 失败"

PKG="$HOME_DIR/$PROJ.zip"
rm -f "$PKG"
(cd "$HOME_DIR" && zip -qr "$PROJ.zip" . -x "logs/*" "*.zip" ".*" "*/.*") || echo "⚠ 打包失败"
ls -la "$PKG"

# 以 mail_file.py 的退出码为准：没收件人、认证失败、超体积都是非零退出，
# 不能照样记「已发信」（kn8/9/13 曾因此误报）
if python3 scripts/mail_file.py "$PKG" \
    --subject "$PROJ 翻译完成" \
    --body "$PROJ 全部 $TOT 条流水线已完成。附件含 markdown 导出、epub 与过程报告。"; then
    echo "[$(date '+%F %T')] 已发信"
else
    echo "[$(date '+%F %T')] ✗ 未发出（见上一行原因）；包在 $PKG，可用 scripts/mail_file.py 补寄"
    exit 5
fi
