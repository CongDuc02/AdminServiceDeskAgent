"""Thăm dò: python làm PID 1 chạy convert_to_pdf (bình thường và bị giết giữa chừng) — có zombie/mồ côi không?"""
import io, os, sys, threading, time
sys.path.insert(0, "/repo/backend/src")
from docx import Document
from bo19.tool_layer.rendering import convert


def table():
    rows = []
    for pid in sorted((p for p in os.listdir("/proc") if p.isdigit()), key=int):
        try:
            st = open(f"/proc/{pid}/stat").read()
            comm = st[st.index("(") + 1: st.rindex(")")]
            rest = st[st.rindex(")") + 2:].split()
            rows.append((int(pid), comm, rest[0], int(rest[1])))
        except OSError:
            pass
    return rows


def show(label):
    print(f"--- {label} (pid của tôi = {os.getpid()})")
    for pid, comm, state, ppid in table():
        print(f"  {pid:>5} ppid={ppid:<5} {state} {comm}")


d = Document(); d.add_paragraph("thử nghiệm"); b = io.BytesIO(); d.save(b)
t0 = time.time()
convert.convert_to_pdf(b.getvalue(), timeout_s=300)
print(f"chuyển đổi bình thường: {time.time()-t0:.1f}s")
time.sleep(1)
show("sau chuyển đổi bình thường")

# bị giết giữa chừng: timeout rất ngắn
try:
    convert.convert_to_pdf(b.getvalue(), timeout_s=0.5)
except Exception as e:
    print("kết quả:", type(e).__name__)
time.sleep(1)
show("sau chuyển đổi bị giết bởi timeout 0,5 s")
