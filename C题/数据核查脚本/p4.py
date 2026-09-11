# -*- coding: utf-8 -*-
import openpyxl, os

BASE = os.path.join("E:\\", "数模", "26国赛", "26 N AI assist'", "C题", "附件")

def rows(path, sheet=0):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    name = sheet if isinstance(sheet, str) else wb.sheetnames[sheet]
    ws = wb[name]
    out = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    return out

r1 = rows(os.path.join(BASE, "附件1.xlsx"))
p1 = [float(x[1]) for x in r1[1:]]
m1 = sum(p1)/len(p1)

r4 = rows(os.path.join(BASE, "附件4.xlsx"))
pr = {str(row[0])[:10]: [float(v) for v in row[1:]] for row in r4[1:]}
means = [sum(v)/len(v) for v in pr.values()]
print("附件1 日均电价: %.4f" % m1)
print("附件4 各日日均电价: min=%.4f max=%.4f 全年均值=%.4f" % (min(means), max(means), sum(means)/len(means)))
print("附件4 日均值 与 附件1日均 的差: max|diff| = %.4f" % max(abs(m-m1) for m in means))

# 与附件1曲线的相关性（同日同刻）
import math
diffs = []
for d, v in list(pr.items())[:10]:
    s = sum((a-b)**2 for a, b in zip(v, p1))/len(v)
    diffs.append(math.sqrt(s))
print("前10日 附件4电价 vs 附件1电价曲线 RMSE: min=%.4f max=%.4f" % (min(diffs), max(diffs)))

# 日内形态：上午/下午/夜间 均价对比
def seg(v, a, b):  # a,b in slots of 10min
    return sum(v[a:b])/(b-a)
print("附件1 0:00-6:00均价 %.4f, 6-12 %.4f, 12-18 %.4f, 18-24 %.4f" % (
    seg(p1,0,36), seg(p1,36,72), seg(p1,72,108), seg(p1,108,144)))
d0 = list(pr.values())[0]
print("附件4首日 0-6 %.4f, 6-12 %.4f, 12-18 %.4f, 18-24 %.4f" % (
    seg(d0,0,36), seg(d0,36,72), seg(d0,72,108), seg(d0,108,144)))
allp = [v for d in pr.values() for v in v]
print("附件4 分时均价 0-6 %.4f, 6-12 %.4f, 12-18 %.4f, 18-24 %.4f" % (
    sum(sum(v[0:36]) for v in pr.values())/(365*36),
    sum(sum(v[36:72]) for v in pr.values())/(365*36),
    sum(sum(v[72:108]) for v in pr.values())/(365*36),
    sum(sum(v[108:144]) for v in pr.values())/(365*36)))
