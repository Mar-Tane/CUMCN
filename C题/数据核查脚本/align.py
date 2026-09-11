# -*- coding: utf-8 -*-
import openpyxl, os, datetime, math

BASE = os.path.join("E:\\", "数模", "26国赛", "26 N AI assist'", "C题", "附件")

def rows(path, sheet=0):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    name = sheet if isinstance(sheet, str) else wb.sheetnames[sheet]
    ws = wb[name]
    out = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    return out

r = rows(os.path.join(BASE, "附件2.xlsx"), "光伏发电实际功率")
pv = {}
for row in r[1:]:
    pv[str(row[0])[:10]] = [float(v) for v in row[1:]]

def norm(d):
    y, m, dd = [int(x) for x in d.split("-")]
    return datetime.date(y, m, dd)

def hourly(v):
    return [sum(v[6*h:6*h+6])/6.0 for h in range(24)]

r3 = rows(os.path.join(BASE, "附件3.xlsx"))
fc = {}
cur = None
for row in r3[1:]:
    d = str(row[0]).strip()
    if d: cur = d
    fc[(cur, str(row[1]))] = [float(x) for x in row[2:]]

dates = sorted(pv, key=norm)
dmap = {norm(d): d for d in pv}

for off, fcm in [(0, "0:00"), (6, "6:00"), (12, "12:00"), (18, "18:00")]:
    for shift in (-1, 0, 1):
        s = 0.0; n = 0
        for (d, m), v in fc.items():
            if m != fcm: continue
            dn = norm(d)
            if dn not in dmap: continue
            a = hourly(pv[dmap[dn]])
            for k in range(24):
                j = k + shift
                if 0 <= j < 24:
                    s += (v[k]-a[j])**2; n += 1
        print("发布%s  shift=%+d  n=%d  RMSE=%.1f kW" % (fcm, shift, n, math.sqrt(s/n)))
    print()

# 光伏>0 的持续小时数 / 弃光风险
over = 0; tot = 0
maxnet = 0
rl = rows(os.path.join(BASE, "附件2.xlsx"), "小区负载")
ld = {str(row[0])[:10]: [float(v) for v in row[1:]] for row in rl[1:]}
for d in dates:
    for i in range(144):
        net = pv[d][i] - ld[d][i]
        if net > 5000: over += 1
        maxnet = max(maxnet, net)
        tot += 1
print("光伏-负载 > 5000kW(储能最大充电功率) 的时段数: %d / %d (%.2f%%)" % (over, tot, 100.0*over/tot))
print("全年 光伏-负载 最大净值: %.1f kW" % maxnet)

# 日净负荷(负载-光伏) 峰值
mx = 0
for d in dates:
    for i in range(144):
        mx = max(mx, ld[d][i]-pv[d][i])
print("全年 负载-光伏 最大净需求: %.1f kW" % mx)

# 电价波动性(附件4)：日内极差
r4 = rows(os.path.join(BASE, "附件4.xlsx"))
pr = {str(row[0])[:10]: [float(v) for v in row[1:]] for row in r4[1:]}
rng = [(max(pr[d])-min(pr[d])) for d in pr]
print("附件4 日内电价极差: 均值 %.4f, 最大 %.4f 元/kWh" % (sum(rng)/len(rng), max(rng)))
# 附件1 日内极差
r1 = rows(os.path.join(BASE, "附件1.xlsx"))
p1 = [float(x[1]) for x in r1[1:]]
print("附件1 日内电价极差: %.4f 元/kWh" % (max(p1)-min(p1)))
