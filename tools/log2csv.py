# Convert the Pico's drive log (log.bin from drive.Recorder) to CSV.
#   mpremote cp :log.bin log.bin
#   py tools/log2csv.py log.bin log.csv
import array
import sys

FIELDS = ("raw_yaw", "p", "r", "y", "lim", "FL", "FR", "RL", "RR")
LOG_MS = 50

src, dst = sys.argv[1], sys.argv[2]
buf = array.array("h")
with open(src, "rb") as f:
    buf.frombytes(f.read())
nf = len(FIELDS)
with open(dst, "w") as f:
    f.write("t_ms," + ",".join(FIELDS) + "\n")
    for k in range(len(buf) // nf):
        row = buf[k * nf:(k + 1) * nf]
        f.write("%d,%s\n" % (k * LOG_MS, ",".join("%.3f" % (v / 1000) for v in row)))
print(len(buf) // nf, "samples ->", dst)
