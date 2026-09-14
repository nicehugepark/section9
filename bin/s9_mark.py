# -*- coding: utf-8 -*-
"""마크의 버전 — 이름을 붙여 두고 한 줄로 갈아 끼운다 (REQ-20260914-002-62x6).

주인(2026-09-14 11:02): 「다시 롤백할 수 있도록 준비하고, 지금부터는 버전을
명시해서 시도해 보자. 그래야 롤백을 하거나 지정할 수 있지.」

마크는 파일 일곱 벌이다 — svg 셋 · ico 하나 · png 셋. 거기에 머리글에 인라인으로
박히는 조각(header.svg)까지 여덟이라, 「이전 것으로 되돌려 봐」 한마디가 여덟 자리를
손으로 맞추는 일이 된다. 그래서 **한 버전은 제 디렉토리에 통째로** 둔다:

    web/assets/mark/<버전>/  mark.svg favicon.svg logo.svg favicon.ico
                            icon-192.png icon-512.png apple-touch-icon.png
                            header.svg   ← 머리글에 박히는 조각
                            NOTE.md      ← 첫 줄이 그 버전의 이름과 한 줄 설명
                            build.py     ← 다시 구울 생성기

`web/assets/` 최상위와 `web/index.html` 의 인라인 조각은 **지금 실린 버전의 복사본**
이고, 실린 이름은 `web/assets/MARK_VERSION` 한 줄에 적힌다. 최상위를 원본으로 두지
않는 까닭은 화면·시험·서버가 전부 그 자리를 이름으로 부르기 때문이다 — 자리는 그대로
두고 내용만 갈아 끼운다.

    s9 mark ls            있는 버전과 지금 실린 것
    s9 mark use v1        v1 을 싣는다(되돌리기)
    s9 mark show v2       그 버전의 파일 목록
"""
import os
import re
import shutil

# 마크의 얼굴 일곱 — 화면·탭·앱 아이콘이 이름으로 부르는 자리다
FACES = ("mark.svg", "favicon.svg", "logo.svg", "favicon.ico",
         "icon-192.png", "icon-512.png", "apple-touch-icon.png")
# 얼굴 말고 버전이 함께 지녀야 하는 것 — 머리 조각 · 설명 · 생성기
EXTRA = ("header.svg", "NOTE.md", "build.py")
VERSION_FILE = "MARK_VERSION"
# 껍데기 안의 마크 조각 — 한 덩어리다(하나뿐이어야 한다)
INLINE_RE = re.compile(r'<svg class="mark".*?</svg>', re.S)


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def paths(root=None):
    root = root or repo_root()
    web = os.path.join(root, "web")
    return web, os.path.join(web, "assets"), os.path.join(web, "assets", "mark")


def versions(root=None):
    """있는 버전 — 이름순. 얼굴 일곱이 다 있는 디렉토리만 버전으로 센다."""
    _, _, store = paths(root)
    if not os.path.isdir(store):
        return []
    out = []
    for name in sorted(os.listdir(store)):
        d = os.path.join(store, name)
        if os.path.isdir(d) and all(os.path.isfile(os.path.join(d, f)) for f in FACES):
            out.append(name)
    return out


def installed(root=None):
    """지금 실린 버전 이름 — 적힌 것이 없으면 None."""
    _, assets, _ = paths(root)
    p = os.path.join(assets, VERSION_FILE)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        name = f.read().strip().splitlines()
        return name[0].strip() if name else None


def note(name, root=None):
    """그 버전의 한 줄 설명 — NOTE.md 의 첫 줄(머리 기호는 뗀다)."""
    _, _, store = paths(root)
    p = os.path.join(store, name, "NOTE.md")
    if not os.path.isfile(p):
        return ""
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip().lstrip("#").strip()
            if line:
                return line
    return ""


def use(name, root=None):
    """그 버전을 싣는다 — 최상위 일곱을 덮고, 껍데기의 인라인 조각을 갈아 끼우고,
    실린 이름을 적는다. 무엇이 바뀌었는지를 돌려준다."""
    web, assets, store = paths(root)
    src = os.path.join(store, name)
    if not os.path.isdir(src):
        raise ValueError("그런 버전이 없다: %s (있는 것: %s)"
                         % (name, ", ".join(versions(root)) or "없음"))
    missing = [f for f in FACES + EXTRA if not os.path.isfile(os.path.join(src, f))]
    if missing:
        raise ValueError("%s 에 없는 파일: %s" % (name, ", ".join(missing)))

    copied = []
    for f in FACES:
        shutil.copyfile(os.path.join(src, f), os.path.join(assets, f))
        copied.append(f)

    shell = os.path.join(web, "index.html")
    with open(os.path.join(src, "header.svg"), encoding="utf-8") as f:
        snippet = f.read().strip()
    with open(shell, encoding="utf-8") as f:
        html = f.read()
    found = INLINE_RE.findall(html)
    if len(found) != 1:
        raise ValueError("index.html 의 마크 조각이 %d 개다 — 하나여야 한다" % len(found))
    changed = found[0] != snippet
    if changed:
        # 조각 안에 백슬래시가 있어도 그대로 들어가야 한다 — 치환 함수로 넘긴다
        html = INLINE_RE.sub(lambda m: snippet, html, count=1)
        with open(shell, "w", encoding="utf-8") as f:
            f.write(html)

    with open(os.path.join(assets, VERSION_FILE), "w", encoding="utf-8") as f:
        f.write(name + "\n")
    return {"version": name, "faces": copied, "shell_changed": changed,
            "note": note(name, root)}


def save(name, summary, root=None, build_src=None, header=None):
    """지금 최상위에 실린 것을 그 이름의 버전으로 보존한다 — 첫 버전을 세울 때 쓴다."""
    web, assets, store = paths(root)
    dst = os.path.join(store, name)
    os.makedirs(dst, exist_ok=True)
    for f in FACES:
        shutil.copyfile(os.path.join(assets, f), os.path.join(dst, f))
    if header is None:
        with open(os.path.join(web, "index.html"), encoding="utf-8") as f:
            found = INLINE_RE.findall(f.read())
        if len(found) != 1:
            raise ValueError("index.html 의 마크 조각이 %d 개다" % len(found))
        header = found[0]
    with open(os.path.join(dst, "header.svg"), "w", encoding="utf-8") as f:
        f.write(header.strip() + "\n")
    with open(os.path.join(dst, "NOTE.md"), "w", encoding="utf-8") as f:
        f.write(summary.strip() + "\n")
    if build_src and os.path.isfile(build_src):
        shutil.copyfile(build_src, os.path.join(dst, "build.py"))
    with open(os.path.join(assets, VERSION_FILE), "w", encoding="utf-8") as f:
        f.write(name + "\n")
    return dst


def table(root=None):
    """`s9 mark ls` 가 내는 줄들 — 실린 것 앞에 ●."""
    now = installed(root)
    lines = []
    for name in versions(root):
        lines.append("%s %-8s %s" % ("●" if name == now else " ", name, note(name, root)))
    if not lines:
        lines.append("  (버전이 없다 — web/assets/mark/<이름>/ 에 만든다)")
    return lines
