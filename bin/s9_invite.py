"""프로젝트 초대 — 메일 본문·SMTP 발송·이력 기록 (REQ-20260913-010-62x6).

bin/s9.py 는 argparse·dispatch·API 라우트 배선만 갖고, 일은 전부 여기서 한다.
s9 의 헬퍼(프로젝트 문서 읽기·멤버 upsert·시크릿 읽기·문서 쓰기)는 bind() 로
받아 쓴다 — 문서를 쓰는 길과 시크릿을 읽는 길을 두 벌 만들지 않기 위해서다.

계약 B (화면 REQ-20260913-012 가 이 모양을 그대로 그린다 — 필드 이름을 바꾸지 마라):

  POST /api/project/invite {slug, email, role?, position?, send}
    → {ok, sent, said, command:{posix, windows}, mail:{subject, text, html}}
      · send:false  미리보기 — 본문과 명령만 돌려주고 기록하지 않는다
      · send:true   SMTP 발송 — 성공하면 sent:true 와 기록(History 한 줄 + 멤버)
      · SMTP 준비물이 없거나 발송이 실패하면 HTTP 200 {ok:false, error, sent:false,
        said, command, mail} — 본문을 복사해 직접 보낼 수 있게 mail 을 함께 준다
      · origin 이 없으면 said 로 알리고 command 두 줄은 빈 문자열, send 는 거부(ok:false)
      · 입력 거부(없는 slug·잘못된 이메일·모르는 role·manage 권한 없음)는 ValueError
        → 서버가 400 {ok:false, error} 로 낸다
  GET  /api/invite/state → {smtp:{ready, from, host}, repo:{origin, linked}}
      · 시크릿의 값(smtp_pass·smtp_user)은 나가지 않는다 — host 와 from 만

SMTP 준비물은 초대하는 사람의 시크릿(`s9 secret set …`) 다섯이다:
  smtp_host · smtp_port(기본 587) · smtp_user · smtp_pass · smtp_from
  587 → STARTTLS, 465 → SMTP_SSL, 그 밖의 포트(로컬 중계·시험 스텁) → 평문.
  user/pass 가 둘 다 있을 때만 login 한다. ready 판정은 host 와 from 이 있는가다.

기록 규칙: 초대가 이 프로그램의 손을 떠났을 때만 기록한다 — SMTP 발송 성공, 또는
CLI `--print`(본문을 받아 직접 보내는 길). 미리보기(API send:false)는 기록하지 않는다.
멤버 키는 그 이메일을 프로필 emails 에 가진 등록 사용자가 있으면 그 이름, 없으면
이메일 그대로다 — 합류(`s9 code --join`, REQ-20260913-013)가 같은 값으로 찾는다.
이미 멤버면 role 을 바꾸지 않는다(재초대가 owner 를 강등하면 안 된다).

발송은 **재시도하지 않는다** — 메일 발송은 멱등이 아니라서, 실패로 보였는데 실제로는
나간 메일이 두 번 가는 것이 한 번 실패보다 나쁘다. 연결·전송에는 timeout 을 건다.
"""
import base64
import html as _html
import os
import re
import smtplib
import subprocess
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

RELEASE_URL = "https://github.com/nicehugepark/section9/releases/latest"
GUIDE_URL = "https://github.com/nicehugepark/section9/blob/main/docs/guide.md"
TEMPLATE_DIR = ("harness", "common", "email")
LOGO_CANDIDATES = ("web/assets/logo.svg", "web/assets/mark.svg")
LOGO_MAX_BYTES = 64 * 1024            # 메일에 싣는 그림 — 이보다 크면 글자 마크로
PLACEHOLDERS = ("project", "inviter", "repo_url", "join_cmd_posix", "join_cmd_windows",
                "release_url", "guide_url", "logo")
SMTP_KEYS = ("smtp_host", "smtp_port", "smtp_user", "smtp_pass", "smtp_from")
SMTP_DEFAULT_PORT = 587
SMTP_TIMEOUT = 20.0                   # 바깥 서비스 호출 — timeout 없는 호출은 없다
GIT_TIMEOUT = 10.0
SMTP_MISSING = "SMTP 준비물 없음 — Settings › 외부 서비스"
NOT_LINKED = "아직 GitHub 과 이어지지 않음 — Settings › 저장소"

_PH = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")
_S9 = {}


def bind(ns):
    """s9.py 의 이름공간(dict 또는 module)을 받는다. s9 의 invite_module() 이 부른다."""
    global _S9
    _S9 = ns if isinstance(ns, dict) else vars(ns)
    return _S9


def _h(name):
    try:
        return _S9[name]
    except KeyError:
        raise RuntimeError(f"s9_invite: bind(s9 이름공간) 가 먼저다 — {name} 이 없다")


# ── 임시 본문 (REQ-20260913-011 의 템플릿이 harness/common/email/ 에 서면 그것을 읽는다) ──

FALLBACK_TEXT = """{{inviter}} 님이 section9 의 「{{project}}」 프로젝트에 초대했습니다.

■ 프로젝트 저장소 (GitHub)
{{repo_url}}

■ 설치 — 릴리스 파일을 받아 풉니다
{{release_url}}
· 리눅스 / macOS / WSL: section9-<버전>-linux-macos.tar.gz 를 받아
    tar xzf section9-<버전>-linux-macos.tar.gz
    cd section9
· Windows (Claude Code Windows 판): section9-<버전>-windows-claude.zip 을 받아
    압축을 풀고 PowerShell 또는 cmd 로 그 폴더(section9)에 들어갑니다

■ 합류 — 아래 한 줄이 저장소를 잇고 이 프로젝트에 넣어 줍니다
· 리눅스 / macOS / WSL:
    {{join_cmd_posix}}
· Windows:
    {{join_cmd_windows}}

처음 실행하면 대시보드가 열리고 Claude Code 로그인을 안내합니다.
OS 별 자세한 절차: {{guide_url}}
"""

FALLBACK_HTML = """<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:600px;max-width:600px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;font-size:15px;line-height:1.6;color:#1a1a1a;">
<tr><td style="padding:24px 0 8px 0;">{{logo}}</td></tr>
<tr><td style="padding:8px 0 16px 0;font-size:20px;font-weight:600;">{{inviter}} 님이 「{{project}}」 프로젝트에 초대했습니다</td></tr>
<tr><td style="padding:12px 0 4px 0;font-weight:600;color:#2b5fd9;">프로젝트 저장소 (GitHub)</td></tr>
<tr><td style="padding:0 0 12px 0;"><a href="{{repo_url}}" style="color:#2b5fd9;">{{repo_url}}</a></td></tr>
<tr><td style="padding:12px 0 4px 0;font-weight:600;color:#2b5fd9;">설치 — 릴리스 파일을 받아 풉니다</td></tr>
<tr><td style="padding:0 0 4px 0;"><a href="{{release_url}}" style="color:#2b5fd9;">{{release_url}}</a></td></tr>
<tr><td style="padding:0 0 4px 0;">리눅스 / macOS / WSL: <code>section9-&lt;버전&gt;-linux-macos.tar.gz</code> 를 받아 <code>tar xzf</code> 로 풀고 <code>cd section9</code></td></tr>
<tr><td style="padding:0 0 12px 0;">Windows (Claude Code Windows 판): <code>section9-&lt;버전&gt;-windows-claude.zip</code> 을 받아 압축을 풀고 PowerShell 또는 cmd 로 그 폴더(section9)에 들어갑니다</td></tr>
<tr><td style="padding:12px 0 4px 0;font-weight:600;color:#2b5fd9;">합류 — 아래 한 줄이 저장소를 잇고 이 프로젝트에 넣어 줍니다</td></tr>
<tr><td style="padding:0 0 4px 0;">리눅스 / macOS / WSL</td></tr>
<tr><td style="padding:0 0 8px 0;"><code style="display:block;padding:8px 10px;border:1px solid #d9d9d9;font-size:13px;white-space:pre-wrap;word-break:break-all;">{{join_cmd_posix}}</code></td></tr>
<tr><td style="padding:0 0 4px 0;">Windows</td></tr>
<tr><td style="padding:0 0 12px 0;"><code style="display:block;padding:8px 10px;border:1px solid #d9d9d9;font-size:13px;white-space:pre-wrap;word-break:break-all;">{{join_cmd_windows}}</code></td></tr>
<tr><td style="padding:12px 0 24px 0;color:#555555;">처음 실행하면 대시보드가 열리고 Claude Code 로그인을 안내합니다. OS 별 자세한 절차: <a href="{{guide_url}}" style="color:#2b5fd9;">{{guide_url}}</a></td></tr>
</table>
"""


# ── 읽기 ────────────────────────────────────────────────────────────────────

def repo_origin(root):
    """`git remote get-url origin` — 없거나 못 물으면 빈 문자열."""
    try:
        r = subprocess.run(["git", "-C", root, "remote", "get-url", "origin"],
                           capture_output=True, encoding="utf-8", errors="replace",
                           timeout=GIT_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def join_commands(origin, slug):
    """합류 명령 두 줄 — origin 이 없으면 둘 다 빈 문자열(반쪽 명령을 내보내지 않는다)."""
    if not origin:
        return "", ""
    return (f"bin/s9 code --join {origin} --project {slug}",
            f"bin\\s9 code --join {origin} --project {slug}")


def _template(root, name):
    p = os.path.join(root, *TEMPLATE_DIR, name)
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _logo_html(root):
    """로고는 바깥 주소를 부르지 않고 data URI 로 싣는다 (REQ-20260913-011 판정).
    아직 파일이 없으면(REQ-20260913-014 가 짓는 중) 글자 마크."""
    for rel in LOGO_CANDIDATES:
        p = os.path.join(root, *rel.split("/"))
        try:
            if 0 < os.path.getsize(p) <= LOGO_MAX_BYTES:
                with open(p, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
                return (f'<img src="data:image/svg+xml;base64,{b64}" alt="section9" '
                        f'height="28" style="height:28px;border:0;">')
        except OSError:
            continue
    return '<strong style="font-size:16px;letter-spacing:0.02em;">section9</strong>'


def render(template, values):
    """{{name}} 치환 — 모르는 자리는 그대로 둔다(템플릿의 결함이 눈에 보이게)."""
    return _PH.sub(lambda m: values.get(m.group(1), m.group(0)), template)


def member_key(email):
    """그 이메일을 가진 등록 사용자의 이름, 없으면 이메일 그대로."""
    want = email.strip().lower()
    for u in _h("registered_users")():
        prof = _h("user_profile")(u) or {}
        got = prof.get("emails") or []
        got = list(got) if isinstance(got, list) else [got]
        if prof.get("email"):
            got.append(prof["email"])
        if want in [str(e).strip().lower() for e in got if e]:
            return u
    return email.strip()


def compose_invite(root, slug, email, role, position, inviter):
    """초대 메일 본문 — {subject, text, html, command_posix, command_windows, said, …}.
    origin 이 없어도 본문은 짓는다(미리보기용). said 가 그 사실을 말하고 명령은 빈다."""
    pr = _h("load_project")(slug)
    if not pr:
        raise ValueError(f"not found: {slug}")
    meta = pr[0]
    slug = meta.get("slug") or slug
    title = str(meta.get("title") or slug)
    inviter_name = str((_h("user_profile")(inviter) or {}).get("display") or inviter or "")
    origin = repo_origin(root)
    posix, windows = join_commands(origin, slug)
    raw = {"project": title, "inviter": inviter_name, "repo_url": origin,
           "join_cmd_posix": posix, "join_cmd_windows": windows,
           "release_url": RELEASE_URL, "guide_url": GUIDE_URL}
    text_vals = {**raw, "logo": "section9"}
    if not origin:
        text_vals["repo_url"] = f"({NOT_LINKED})"
    html_vals = {k: _html.escape(v, quote=True) for k, v in text_vals.items()}
    html_vals["logo"] = _logo_html(root)
    text = render(_template(root, "invite.txt") or FALLBACK_TEXT, text_vals)
    body = render(_template(root, "invite.html") or FALLBACK_HTML, html_vals)
    return {
        "subject": f"[section9] {inviter_name} 님이 「{title}」 프로젝트에 초대합니다",
        "text": text, "html": body,
        "command_posix": posix, "command_windows": windows,
        "repo_url": origin, "said": "" if origin else NOT_LINKED,
        "project": title, "slug": slug, "to": email.strip(),
        "role": role, "position": position or "", "inviter": inviter,
    }


# ── SMTP ────────────────────────────────────────────────────────────────────

def smtp_config(root, user):
    """초대하는 사람의 시크릿에서 SMTP 준비물을 읽는다. 값은 이 함수 밖으로 흘리지 마라
    — 화면·API 에는 smtp_public() 만 준다."""
    val = _h("secret_value")
    cfg = {k: (val(user, k, root) or "") for k in SMTP_KEYS} if user else \
        {k: "" for k in SMTP_KEYS}
    try:
        port = int(cfg["smtp_port"] or SMTP_DEFAULT_PORT)
    except ValueError:
        port = 0
    cfg["port"] = port
    cfg["ready"] = bool(cfg["smtp_host"] and cfg["smtp_from"] and port > 0)
    return cfg


def smtp_public(cfg):
    return {"ready": bool(cfg.get("ready")), "from": cfg.get("smtp_from", ""),
            "host": cfg.get("smtp_host", "")}


def invite_state(root, user):
    """GET /api/invite/state 의 본문."""
    origin = repo_origin(root)
    return {"smtp": smtp_public(smtp_config(root, user)),
            "repo": {"origin": origin, "linked": bool(origin)}}


def build_message(mail, to, sender):
    msg = EmailMessage()
    msg["Subject"] = mail["subject"]
    msg["From"] = sender
    msg["To"] = to
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="section9.invite")
    msg.set_content(mail["text"])
    msg.add_alternative(mail["html"], subtype="html")
    return msg


def send_invite(root, mail, to, user=None):
    """SMTP 로 보낸다 — 한 번만. {ok, sent, error?, mail}.
    준비물이 없으면 보내지 않고 ok:false 와 mail 을 함께 돌려준다."""
    user = user or mail.get("inviter") or ""
    cfg = smtp_config(root, user)
    if not cfg["ready"]:
        return {"ok": False, "sent": False, "error": SMTP_MISSING, "mail": mail}
    msg = build_message(mail, to, cfg["smtp_from"])
    host, port = cfg["smtp_host"], cfg["port"]
    try:
        if port == 465:
            conn = smtplib.SMTP_SSL(host, port, timeout=SMTP_TIMEOUT)
        else:
            conn = smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT)
        try:
            conn.ehlo()
            if port == 587:
                conn.starttls()
                conn.ehlo()
            if cfg["smtp_user"] and cfg["smtp_pass"]:
                conn.login(cfg["smtp_user"], cfg["smtp_pass"])
            conn.send_message(msg, from_addr=cfg["smtp_from"], to_addrs=[to])
        finally:
            try:
                conn.quit()
            except (smtplib.SMTPException, OSError):
                pass
    except (smtplib.SMTPException, OSError) as e:
        return {"ok": False, "sent": False,
                "error": f"SMTP 발송 실패 ({host}:{port}): {e}", "mail": mail}
    return {"ok": True, "sent": True, "mail": mail}


# ── 기록 ────────────────────────────────────────────────────────────────────

def record_invite(slug, email, role, position, inviter, via=""):
    """프로젝트 문서에 「초대: <email> (role, by inviter)」 한 줄, 멤버가 아니면 추가.
    멤버 추가는 do_member_set 한 경로다(인가·마지막 owner 보호가 그 안에 있다)."""
    load, key = _h("load_project"), member_key(email)
    pr = load(slug)
    if not pr:
        raise ValueError(f"not found: {slug}")
    meta = pr[0]
    if not any(m.get("user") == key for m in meta.get("members", [])):
        _h("do_member_set")(meta["slug"], key, role=role, position=position or None,
                            actor=inviter, via=via)
    meta, body, path = load(meta["slug"])
    now = _h("now_iso")()
    meta["updated"] = now
    body = body.rstrip("\n") + f"\n- {now} 초대: {email} ({role}, by {inviter}{via})\n"
    _h("acquire_lock")()
    try:
        _h("write_doc")(path, meta, body)
        _h("rebuild_index")(quiet=True)
    finally:
        _h("release_lock")()
    return {"member": key, "role": role}


# ── 한 경로: CLI 와 POST /api/project/invite 가 함께 지난다 ──────────────────

def do_project_invite(root, slug, email, role=None, position=None, actor=None,
                      send=False, record=None, via=""):
    """거부는 ValueError(→ 400). 상태 문제(origin 없음·SMTP 준비물 없음·발송 실패)는
    ok:false 로 돌려준다 — 화면이 본문과 사유를 함께 그릴 수 있게.
    record: None = 발송 성공 때만 기록 · True = 발송과 무관하게 기록(CLI --print)."""
    email = (email or "").strip()
    role = (role or "contributor").strip()
    if not re.fullmatch(_h("EMAIL_RE"), email):
        raise ValueError(f"invalid email: {email!r}")
    if role not in _h("PROJECT_ROLES"):
        raise ValueError(f"invalid role: {role} (valid: {', '.join(_h('PROJECT_ROLES'))})")
    pr = _h("load_project")(slug)
    if not pr:
        raise ValueError(f"not found: {slug}")
    slug = pr[0].get("slug") or slug
    can = _h("project_can")
    if not can(slug, actor, "manage"):
        raise ValueError(f"권한 없음: '{actor}' 는 {slug} 에 초대할 수 없다 (maintainer 이상 필요)")
    if role == "owner" and not can(slug, actor, "own"):
        raise ValueError("권한 없음: owner 로 초대하는 것은 owner 만 할 수 있다")
    mail = compose_invite(root, slug, email, role, position, actor)
    public = {"subject": mail["subject"], "text": mail["text"], "html": mail["html"]}
    out = {"ok": True, "sent": False, "said": mail["said"],
           "command": {"posix": mail["command_posix"], "windows": mail["command_windows"]},
           "mail": public, "recorded": False}
    if send:
        if not mail["repo_url"]:
            return {**out, "ok": False, "error": NOT_LINKED}
        r = send_invite(root, mail, email, user=actor)
        if not r["ok"]:
            return {**out, "ok": False, "error": r["error"], "said": r["error"]}
        out["sent"] = True
        out["said"] = f"초대 메일을 {email} 로 보냈습니다"
    if record is True or (record is None and out["sent"]):
        record_invite(slug, email, role, position, actor, via=via)
        out["recorded"] = True
    return out


def cli_report(res, print_body=False):
    """`s9 project invite` 의 stdout — --print 는 본문 그대로, 아니면 요약 몇 줄."""
    m = res["mail"]
    if print_body:
        return f"Subject: {m['subject']}\n\n{m['text']}"
    lines = [f"제목: {m['subject']}"]
    if res["command"]["posix"]:
        lines.append(f"합류 명령 (리눅스·macOS·WSL): {res['command']['posix']}")
        lines.append(f"합류 명령 (Windows):        {res['command']['windows']}")
    if res.get("said"):
        lines.append(res["said"])
    if not res.get("sent"):
        lines.append("보내려면 --send, 본문을 받아 직접 보내려면 --print")
    return "\n".join(lines)
