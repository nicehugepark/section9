"""REQ-20260910-023: 같은 자를 둘이 동시에 쓰면 서로의 값을 망치는가.

`_probe_marks.measure()` 는 프로파일·픽스처 자리를 `/tmp/s9probe-marks` 로 고정한다
(픽스처 파일 `/tmp/s9probe-marks.html` 까지 같은 이름이다). 전체 테스트는 파일을
병렬로 돌리고, 사람이나 에이전트가 그 옆에서 같은 자를 직접 돌리기도 한다.
둘이 겹치면 한쪽이 다른 쪽의 프로파일을 `rmtree` 하고 같은 `DevToolsActivePort`
파일을 읽는다 — 그러면 자기가 안 띄운 브라우저를 잰다.

배율 1.0 과 1.5 를 동시에 돌려, 각자가 제 배율의 값을 내는지 본다.
혼자 돌 때의 값과 다르면 그것이 증거다.
"""
import multiprocessing
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tests"))


def run(scale, q):
    import _probe_marks as P
    try:
        rows = P.measure(scale, ["ledger"], "par%g" % scale)
        for r in rows:
            if r["face"] != "on":
                continue
            c, n = r["parts"]["clock"], r["parts"]["num"]
            q.put((scale, "%.3f..%.3f" % (c["y0"], c["y1"]),
                   "%.3f..%.3f" % (n["y0"], n["y1"]),
                   (c["y0"] + c["y1"]) / 2 - (n["y0"] + n["y1"]) / 2))
            return
        q.put((scale, "얼굴 없음", "-", 0))
    except BaseException as e:
        q.put((scale, "터짐: %s: %s" % (type(e).__name__, e), "-", 0))


if __name__ == "__main__":
    print("혼자 돌 때 (기준):")
    for sc in (1.0, 1.5):
        q = multiprocessing.Queue()
        p = multiprocessing.Process(target=run, args=(sc, q))
        p.start()
        p.join(300)
        print("   x%-4g 시계 %-16s 숫자 %-16s dy=%+.3f" % q.get())

    print()
    print("둘이 동시에 돌 때:")
    q = multiprocessing.Queue()
    ps = [multiprocessing.Process(target=run, args=(sc, q))
          for sc in (1.0, 1.5)]
    for p in ps:
        p.start()
    for p in ps:
        p.join(300)
    out = sorted([q.get() for _ in ps])
    for row in out:
        print("   x%-4g 시계 %-16s 숫자 %-16s dy=%+.3f" % row)
