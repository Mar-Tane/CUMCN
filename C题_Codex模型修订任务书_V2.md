# C题 Codex 模型修订任务书 V2

> 适用仓库：`CUMCM/Codex`  
> 目标：在保留现有工程成果和旧结果的前提下，系统修复信息边界、结算口径、Q3 消融实验和 Q4 波动电价信息边界问题，形成可用于国赛论文的最终模型与审计报告。

---

## 0. 总目标与工作原则

请基于当前 `CUMCM/Codex` 工程继续修改，不要推倒现有代码重写。当前 Q1–Q4、Excel 导出、HiGHS LP、验证器等工程框架均应保留。

本轮目的不是“把总费用调高/调低到某个预期数字”，而是解决目前存在的**信息边界、结算口径、消融实验和波动电价信息边界**问题，建立可以在论文中自洽解释、可复现、可审计的最终模型。

### 必须遵守

1. **禁止为了接近 14M、15M 等参考数字人工调参数。**
2. 当前结果全部保留，先作为 `legacy/perfect-information benchmark`。
3. 新结果先放到独立 variants 目录，**不要覆盖现有 `outputs/q2`、`q3`、`q4-*` 和现有 result.xlsx**。
4. 每个实验只能改变一个明确因素，避免多个条件一起变导致无法归因。
5. 所有“严格在线/因果”模型必须满足：

   > 决策时刻以后才会发生的附件2真实负载、真实光伏和附件4未来真实价格，不允许作为优化输入。

6. 不预设新方案一定比旧方案贵，也不预设加入更多预报一定更便宜。只报告真实结果。
7. Q1 当前结果作为回归锚点，除参数化公共代码外不要改变 Q1 主结果。

---

# 1. P0：首先建立“信息集模式”，解决未来信息穿越

这是本轮最高优先级。

当前 Q2：

```python
plan = solve_dispatch(
    annual.load_kw[d],
    decision.forecast_kw,
    prices[d],
    ...
)
```

因此 PV 是预测值，但负载是当天真实完整曲线。

当前 Q3：

```python
baseline = solve_dispatch(
    annual.load_kw[d],
    base_pv,
    prices[d],
    ...
)
```

并且 6/12/18 时：

```python
load_horizon = _horizon(annual.load_kw, d, node, ...)
price_horizon = _horizon(prices, d, node, ...)
```

会直接获取未来负载；Q4 使用附件4后，还会取得未来真实电价。

这些旧结果不要删除，将其明确标记为：

```text
perfect_load / perfect_price benchmark
```

而不是再笼统写成“strict online”。

---

## 1.1 新增严格因果负载预测模块

### 建议新增文件

```text
Codex/solve/load_forecast.py
```

实现：

```python
class OnlineLoadForecaster:
    ...
```

基本要求：

- 第 `d` 天 0:00 做预测时，只能使用 `< d` 的附件2负载；
- 6/12/18 做未来预测时，可以使用当前时刻以前已经发生的观测，但不能使用未来真实负载；
- 预测长度支持 144 slots；
- 跨日未来 24h 时必须能预测到下一日；
- 不得直接 slice `annual.load_kw` 的未来部分。

第一版不需要复杂 ML，优先使用稳定、可解释方法：

```text
persistence
mean7
mean14
mean30
weighted14
weighted30
```

可以增加：

```text
weekday_mean
```

但不是强制。

预测器必须滚动在线选型，选型也只能利用历史误差。

负载预测选择指标建议使用：

\[
MAE=\frac1N\sum |\hat L-L|
\]

而不是 PV 当前的 4:1 非对称评分，因为负载预测本身先保持中性。

输出：

```text
load_forecast_log.csv
```

字段至少：

```text
date
decision_time
history_days_used
method
mae_kw
rmse_kw
daily_energy_error_kwh
```

---

## 1.2 修改 `q2.py`

将：

```python
run_q2(...)
```

扩展为至少支持：

```python
run_q2(
    ...,
    load_mode="causal",       # causal / perfect
    realtime_feedback=True,
    pv_risk_mode="asymmetric",
    terminal_policy="daily_cycle",
)
```

### `load_mode`

#### `perfect`

完全保持当前行为：

```python
load_plan = annual.load_kw[d]
```

用于旧结果回归和 perfect-information benchmark。

#### `causal`

调用新的 `OnlineLoadForecaster`：

```python
load_plan = load_forecaster.predict(...)
```

LP 使用：

```python
solve_dispatch(
    load_plan,
    pv_forecast,
    price_plan,
    ...
)
```

**真实 `annual.load_kw[d]` 只能进入当天实际执行/结算，不得进入 0:00 优化。**

修改 metrics：

当前：

```text
information_set
```

必须拆成明确字段：

```json
{
  "load_information": "...",
  "pv_information": "...",
  "price_information": "...",
  "realtime_storage_feedback": true
}
```

不要再写含糊的：

```text
Attachment 2 prior/current observations
```

---

# 2. P0：为 Q2 做“为什么 13.28M 较低”的严格归因实验

不要先改变当前 PV 风险预测方法。当前：

\[
4(\hat P-P)^+ +(P-\hat P)^+
\]

以及 q80/q85/q90/q95 有理论依据，先保留。

但需要增加一个**无安全下修版本**作为对照。

修改：

```text
forecast.py
q2.py
```

新增：

```python
pv_risk_mode =
    "asymmetric"   # 当前方案
    "point"        # 无分位数安全 margin
```

`point` 模式使用历史预测方法，但：

```text
margin_kw = 0
```

且候选模型尽量依据对称 MAE/历史误差选取。

### 必跑四组 Q2

保持其余参数完全一致：

| 编号 | 负载 | PV风险 | 实时储能反馈 |
|---|---|---|---|
| Q2-A | perfect | asymmetric | ON |
| Q2-B | causal | asymmetric | ON |
| Q2-C | causal | point | ON |
| Q2-D | causal | asymmetric | OFF |

Q2-A 应能复现当前约 13.276966M 的旧结果。

这四组的目的不是选“费用最高”的，而是分解：

\[
\Delta C_{\rm load}
=C_B-C_A
\]

\[
\Delta C_{\rm PVrisk}
=C_C-C_B
\]

\[
\Delta C_{\rm feedback}
=C_D-C_B
\]

从而回答：

> 当前 13.28M 到底有多少来自完美负载信息、PV 风险安全边际、10min 实时储能调节。

---

# 3. P0：把实时储能反馈改成显式可开关模式

当前 `settle.py` 的：

```python
execute_with_realtime_storage_feedback(...)
```

在真实光伏低于计划时会：

```text
先取消充电
→ 再增加放电
→ 最后紧急购电
```

真实光伏过剩时则：

```text
先减少放电
→ 再增加充电
→ 最后弃光
```

这相当于给储能非常强的 10min 实时 recourse。

不要删除。

### 修改 `settle.py`

统一增加：

```python
execute_plan(
    ...,
    realtime_feedback: bool = True
)
```

或者保留旧函数，再新增：

```python
execute_fixed_storage_plan(...)
```

### OFF 模式定义

当：

```python
realtime_feedback=False
```

时：

- `charge = plan.charge`
- `discharge = plan.discharge`
- 不根据真实 PV 主动改变储能计划；
- 真实不足全部进入 emergency；
- 真实富余进入 curtail；
- 仍需满足 SOC 物理边界。

这只是**敏感性/口径实验**，不意味着最终一定采用 OFF。

---

# 4. P0：修正 Q3 的核心任务——真正回答“6/12/18 新预报是否值得使用”

原题明确要求：

> 分析是否需要引入其他时刻预报制定调整购电策略。

当前主要比较：

```text
raw step
calibrated step
calibrated linear
```

这只能回答“降尺度/校准方法哪个好”，不能直接回答：

> 6:00、12:00、18:00 这些新增预报值多少钱。

---

## 4.1 修改 `q3.py`

给：

```python
run_q3(...)
```

增加参数：

```python
update_nodes=(0,36,72,108)
```

合法示例：

```python
(0,)
(0,36)
(0,36,72)
(0,36,72,108)
```

不要把节点硬编码为：

```python
for node_index, node in enumerate((0,36,72,108)):
```

改成根据 `update_nodes` 控制是否允许更新。

### 必跑四组

保持：

- 同一个 load mode；
- 同一个 downscale；
- 同一个 calibrate；
- 同一个 settlement mode；
- 同一个 terminal policy；
- 同一个 realtime feedback；

只改变可使用的预报节点：

```text
S0 = 0:00 only
S1 = 0:00 + 6:00
S2 = 0:00 + 6:00 + 12:00
S3 = 0:00 + 6:00 + 12:00 + 18:00
```

计算：

\[
V_6=C_{S0}-C_{S1}
\]

\[
V_{12}=C_{S1}-C_{S2}
\]

\[
V_{18}=C_{S2}-C_{S3}
\]

以及：

\[
V_{\rm total}=C_{S0}-C_{S3}.
\]

**不要要求这些值一定为正。**

若后续预测误差使某个更新时刻反而增加费用，也必须真实报告。

---

## 4.2 输出 Q3 消融报告

新增：

```text
outputs/variants/q3_update_ablation/summary.csv
outputs/variants/q3_update_ablation/summary.json
outputs/variants/q3_update_ablation/by_season.csv
```

`summary.csv` 至少包括：

```text
case
update_nodes
total_cost_yuan
baseline_purchase_cost_yuan
adjustment_settlement_cost_yuan
emergency_cost_yuan
emergency_energy_kwh
days_with_emergency
curtailment_energy_kwh
up_adjustment_energy_kwh
down_adjustment_energy_kwh
forecast_mae_kw
storage_throughput_kwh
cost_saving_vs_S0_yuan
incremental_value_yuan
```

季节至少划分：

```text
spring: 3-5
summer: 6-8
autumn: 9-11
winter: 12,1,2
```

目的：论文能回答“夏季光伏波动更强时后续预报是否更有价值”等问题。

---

# 5. P0：Q3 两种结算解释必须分别重新优化

当前 Q3 已计算两种费用：

```python
settlement
additive
```

但 LP 只按照当前 replacement settlement 优化，然后对同一个调度方案事后计算 additive cost。

这不够。

因为：

> 目标函数变了，最优调整策略本身也可能变。

---

## 5.1 修改 `lp_core.py`

把：

```python
solve_adjustment_dispatch(...)
```

扩展为：

```python
solve_adjustment_dispatch(
    ...,
    settlement_mode="replacement"
)
```

支持：

```text
replacement
additive
```

### replacement 模式

保持当前：

\[
C_t
=
p_t[
\min(G_t^p,G_t^a)
+0.5(G_t^p-G_t^a)^+
+1.5(G_t^a-G_t^p)^+
].
\]

当前线性化可以保留。

### additive 模式

严格按照：

\[
C_t
=
p_tG_t^p
+0.5p_t(G_t^p-G_t^a)^+
+1.5p_t(G_t^a-G_t^p)^+.
\]

建议增加：

\[
u_t=(G_t^a-G_t^p)^+
\]

\[
d_t=(G_t^p-G_t^a)^+
\]

满足：

\[
G_t^a-G_t^p=u_t-d_t,
\qquad u_t,d_t\ge0.
\]

目标中：

\[
p_tG_t^p
+
1.5p_tu_t
+
0.5p_td_t.
\]

其中 \(p_tG_t^p\) 对调整阶段是常数，但最终报告必须加入。

---

## 5.2 必跑

在相同：

```text
load mode
forecast
update nodes
feedback
terminal policy
price
```

条件下分别完整重优化：

```text
Q3-replacement
Q3-additive
```

不得再只做“同方案换公式计费”。

---

# 6. P0：Q4 增加价格信息边界，不再只有“未来真实价格完全可知”

当前 `q4.py`：

```python
prices = read_attachment4().price
run_q2(price_matrix=prices)
run_q3(price_matrix=prices)
```

这使 Q2 在每天 0:00、Q3 在 6/12/18 优化时都可能获得未来真实价格。

旧结果不要删除，将其明确命名：

```text
perfect_price benchmark
```

---

## 6.1 新增价格预测模块

建议新建：

```text
Codex/solve/price_forecast.py
```

实现：

```python
class OnlinePriceForecaster:
```

第一版仍然采用简单稳定预测：

```text
persistence
mean7
mean14
mean30
weighted14
weighted30
```

可选增加 weekday profile。

选择模型只能使用历史已发生价格。

必须支持：

```python
predict_horizon(day, start_slot, horizon=144)
```

在 6/12/18：

- 当前节点以前价格可以作为已知；
- 未来价格不可读取附件4真实未来值；
- 跨日部分也必须预测。

---

## 6.2 修改 Q2/Q3 接口

增加：

```python
price_mode="perfect"   # perfect / causal
```

或者传入明确的 `price_provider`。

### perfect

保持旧附件4真实全日价格输入。

### causal

只使用截至决策时刻已经可获得的附件4历史价格预测未来。

---

## 6.3 Q4 必跑四组

```text
Q4-2-perfect-price
Q4-2-causal-price
Q4-3-perfect-price
Q4-3-causal-price
```

定义价格信息价值：

\[
V_{\rm price,Q2}
=
C_{\rm causal,Q2}-C_{\rm perfect,Q2}
\]

\[
V_{\rm price,Q3}
=
C_{\rm causal,Q3}-C_{\rm perfect,Q3}.
\]

同时输出：

```text
price_mae
price_rmse
daily_price_energy_weighted_error
```

不要预设 causal 一定更贵，但理论上 perfect information 是非常重要的参考下界。

---

# 7. P1：日末 SOC 约束参数化，但暂时不要推翻现有主方案

当前 Q2：

```python
soc_terminal=initial
```

Q3 各 24h 滚动优化也是：

```python
soc_terminal=node_state
```

原题只有 Q1 明确要求：

\[
S_{0:00}=S_{24:00}.
\]

Q2/Q3 没有明确写这个要求。

但是直接去掉终端约束也可能引入有限时域“把储能在结尾放空”的问题，因此本轮不要武断替换，只做敏感性。

### 修改

增加：

```python
terminal_policy =
    "daily_cycle"
    "free"
```

其中：

#### daily_cycle

保持当前做法。

#### free

不设置：

```python
soc_terminal
```

最后比较：

```text
总费用
紧急购电
弃光
全年末 SOC
日边界 SOC 分布
```

论文最终是否采用 daily_cycle，结合经济合理性决定。

当前主结果可以继续以 daily-cycle 作为“保持储能长期可持续运行”的假设，但必须在论文明确写出来。

---

# 8. P1：储能效率口径敏感性

当前：

```python
ETA_CH=0.9
ETA_DIS=0.9
```

意味着往返效率：

\[
0.9^2=81\%.
\]

题面只写“充放电效率为 90%”，存在两种解释。

不要立即改主模型。

建议将储能参数从硬编码改成：

```python
@dataclass
class StorageParams:
    eta_ch: float
    eta_dis: float
    soc_min: float
    soc_max: float
    power_limit_kw: float
```

至少跑：

### E1 当前解释

\[
\eta_c=\eta_d=0.9
\]

### E2 往返总效率 90%

\[
\eta_c=\eta_d=\sqrt{0.9}.
\]

输出总费用和储能吞吐量差异。

---

# 9. 必须增加“未来信息泄漏”自动测试

这是非常重要的一项，不要只靠人工看代码。

建议新增：

```text
Codex/tests/test_causality.py
```

至少实现以下测试。

### Test 1：Q2 负载因果性

在某天 `d`：

1. 生成当天 0:00 的 causal load forecast；
2. 把附件2第 `d` 天真实负载人为乘 10 或随机替换；
3. 在不修改 `<d` 历史数据的条件下重新做 0:00 预测；
4. 两次计划输入必须完全一致。

验收：

```text
max_abs_diff < 1e-10
```

---

### Test 2：Q2 PV 因果性

同理修改当天未来实际 PV。

0:00 的预测与计划不得改变。

---

### Test 3：Q3 节点因果性

例如 6:00：

人为修改：

```text
当天 6:00 以后真实 load
当天 6:00 以后真实 PV
```

在 causal 模式下，6:00 的优化输入不得变化。

---

### Test 4：Q4 价格因果性

在 6:00：

人为修改附件4当天 6:00 以后真实价格。

`price_mode="causal"` 时：

```text
6:00 forecast / decision
```

不得变化。

`price_mode="perfect"` 则允许变化。

---

# 10. 增加 Q3 结算单元测试

新增：

```text
Codex/tests/test_settlement.py
```

至少验证 \(p=1\)。

### replacement

若：

```text
Gp=900
Ga=700
```

应为：

\[
700+0.5\times200=800.
\]

若：

```text
Gp=700
Ga=900
```

应为：

\[
700+1.5\times200=1000.
\]

### additive

若：

```text
Gp=900
Ga=700
```

应为：

\[
900+0.5\times200=1000.
\]

若：

```text
Gp=700
Ga=900
```

应为：

\[
700+1.5\times200=1000.
\]

同时对随机数组验证：

```text
LP 线性化目标
```

和直接 numpy 重算之间：

```text
abs(gap) < 1e-7
```

---

# 11. 旧结果必须能无损复现：回归测试

这是防止“修一个地方坏三个地方”。

新增 regression test 或审计脚本。

旧参数：

```text
load_mode=perfect
price_mode=perfect
realtime_feedback=True
pv_risk_mode=asymmetric
settlement_mode=replacement
terminal_policy=daily_cycle
```

必须基本复现当前已有：

```text
Q1
Q2
Q3
Q4-2
Q4-3
```

结果。

### 数值验收建议

总费用：

```text
abs(new-old) <= 1e-3 yuan
```

若 HiGHS/浮点导致轻微解的多重最优差异：

```text
relative cost diff < 1e-9
```

即可。

物理序列可允许多重最优导致的微小差异，但：

```text
费用
紧急购电总量
SOC约束
能量平衡
Excel总量
```

必须一致。

---

# 12. `validate_all.py` 必须增加的信息审计

当前 validator 主要验证物理可行性和 Excel 回读。

在此基础上增加：

```json
{
  "physical_validation": true,
  "excel_validation": true,
  "causality_validation": true,
  "settlement_validation": true,
  "regression_validation": true
}
```

最终：

```text
passed=True
```

必须要求五类全部通过。

---

# 13. 全部实验统一输出的核心指标

所有 Q2/Q3/Q4 variant 必须至少输出以下指标，字段名尽量统一：

```text
total_cost_yuan

plan_purchase_cost_yuan
adjustment_cost_yuan
emergency_cost_yuan

plan_purchase_energy_kwh
adjusted_purchase_energy_kwh
emergency_energy_kwh
curtailment_energy_kwh

days_with_emergency
emergency_interval_count

storage_charge_energy_kwh
storage_discharge_energy_kwh
storage_throughput_kwh

ending_soc_kwh
min_soc_kwh
max_soc_kwh

load_forecast_mae_kw
load_forecast_rmse_kw
pv_forecast_mae_kw
pv_forecast_rmse_kw
price_forecast_mae
price_forecast_rmse

max_balance_residual
max_soc_residual
max_simultaneous_charge_discharge

runtime_seconds
```

不适用字段填 `null`，不要用不同名称表达同一个量。

---

# 14. 输出目录规范

本轮所有实验先放：

```text
Codex/outputs/variants/model_audit_v2/
```

例如：

```text
q2/
    A_perfectload_risk_feedback/
    B_causalload_risk_feedback/
    C_causalload_point_feedback/
    D_causalload_risk_nofeedback/

q3/
    S0_0/
    S1_0_6/
    S2_0_6_12/
    S3_0_6_12_18/
    settlement_replacement/
    settlement_additive/

q4/
    q42_perfect_price/
    q42_causal_price/
    q43_perfect_price/
    q43_causal_price/

sensitivity/
    terminal/
    efficiency/
```

在确认最终主模型以前：

**禁止覆盖**

```text
Codex/outputs/q2
Codex/outputs/q3
Codex/outputs/q4-2
Codex/outputs/q4-3
```

以及现有官方 result Excel。

---

# 15. 自动生成总审计报告

新增：

```text
Codex/reports/MODEL_AUDIT_V2.md
```

程序自动或半自动生成。

必须包含以下表格。

## 表 A：Q2 原因拆解

```text
方案
负载信息
PV预测模式
实时反馈
总费用
计划费用
紧急费用
紧急电量
弃光
与当前13.28M差值
```

必须明确回答：

> 当前 Q2 费用较低主要是完美负载、PV 风险预测还是实时储能反馈造成的？

---

## 表 B：Q3 新预报价值

```text
0 only
0+6
0+6+12
0+6+12+18
```

报告：

```text
总费用
增量价值
累计价值
紧急购电
调整电量
季节分解
```

最终给出一句基于数值的结论：

```text
是否值得使用6/12/18时新增预报，以及哪些时刻价值最大。
```

不能只做定性描述。

---

## 表 C：Q3 结算口径

```text
replacement重新优化
additive重新优化
```

比较：

```text
总费用
计划购电
调整幅度
紧急购电
储能策略差异
```

---

## 表 D：Q4 价格信息价值

```text
Q4-2 perfect price
Q4-2 causal price
Q4-3 perfect price
Q4-3 causal price
```

给出：

```text
未来价格完美可知带来的理想化收益
```

以及：

```text
滚动光伏预报在动态价格条件下的价值是否改变
```

---

# 16. 验收标准

本轮任务只有同时满足以下条件才能认为完成。

### A. 工程正确

```bash
python -m unittest discover -s Codex/tests -v
```

全部通过。

```bash
python -m Codex.solve.validate_all
```

全部通过。

---

### B. 旧结果不被破坏

legacy 参数能够复现当前 Q1/Q2/Q3/Q4 数值。

---

### C. 无未来信息泄漏

causal 模式的自动 mutation tests 全部通过。

任何未来真实：

```text
load
PV
price
```

被人工修改后，当前决策都不得受到影响。

---

### D. 物理约束通过

所有方案：

\[
1200\le SOC\le10800
\]

充放电功率合法。

能量平衡最大残差：

```text
< 1e-7 kWh
```

SOC递推残差：

```text
< 1e-7 kWh
```

---

### E. Q3 真正回答题目

必须获得 S0/S1/S2/S3 四组结果。

不接受仅以：

```text
Q3 cost - Q2 cost
```

来声称“后续预报的价值”。

---

### F. Q3 两种费用解释都是真正重新优化

不接受：

```text
同一个dispatch + 两种事后计费
```

代替两种优化。

---

### G. Q4 有 perfect 与 causal 两套价格信息结果

旧的附件4完整未来价格结果保留作 benchmark，但不得再把它描述成唯一的“实时价格模型”。

---

### H. 不允许结果导向调参

如果 causal Q2 最终仍然是：

```text
13M左右
```

只要因果测试、物理约束、结算和数据口径全部通过，就接受。

如果变成：

```text
14M或15M
```

也不能因为“看起来更合理”直接接受，必须通过同一套验收。

---

# 17. 执行顺序

请严格按以下顺序做，不要同时大改全部文件：

```text
Step 1
建立回归测试，冻结当前legacy结果。

Step 2
实现load_forecast.py和load_mode。
先只重跑Q2-A/Q2-B。

Step 3
实现realtime_feedback开关和pv_risk_mode。
完成Q2 A/B/C/D原因拆解。

Step 4
修改Q3 update_nodes。
完成S0/S1/S2/S3消融。

Step 5
实现settlement_mode两套LP并分别重优化。

Step 6
实现price_forecast.py和price_mode。
完成Q4 perfect/causal比较。

Step 7
做terminal policy、效率等P1敏感性。

Step 8
统一validator、paper tables、plots、MODEL_AUDIT_V2.md。

Step 9
根据审计结果决定最终论文采用哪一套结果。

Step 10
只有我确认后，才允许更新正式result1/2/3/4 Excel和主reports。
```

---

# 18. 完成后只向我汇报这些内容，不要先写长篇解释

任务完成后第一条回复请给我：

```text
1. 修改了哪些文件
2. 新增了哪些文件
3. 所有测试是否通过
4. Q2 A/B/C/D四组核心结果
5. Q3 S0/S1/S2/S3四组结果
6. Q3 replacement/additive重新优化结果
7. Q4 perfect-price/causal-price四组结果
8. 哪几个因素解释了原Q2的13.28M
9. 是否发现新的bug或题意歧义
10. 你建议最终论文采用哪套口径，以及理由
```

并同时给出：

```text
Codex/reports/MODEL_AUDIT_V2.md
```

的路径。

不要在没有跑完整实验之前猜测最终结论。

---

# 19. 本轮建模策略说明

本轮**暂不优先升级到复杂的两阶段随机规划、SAA 或鲁棒优化**。

原因是当前最重要的工作不是增加模型复杂度，而是先完成以下审计：

1. 负载是否存在未来信息穿越；
2. Q3 新预报时刻是否真正产生增量价值；
3. Q3 两种结算口径是否分别重新优化；
4. Q4 是否使用了未来真实价格；
5. 实时储能反馈到底对 Q2 的 13.28M 贡献了多少。

在以上问题没有完全锁定之前，直接引入更复杂优化模型只会进一步增加结果解释难度。

当本轮 `MODEL_AUDIT_V2.md` 完成后，再根据结果决定是否有必要将：

- Q2 升级为两阶段随机规划；
- Q3 升级为更严格的多阶段随机/滚动优化；
- Q4 升级为电价预测 + 情景优化或鲁棒优化。

---

# 20. 最终核心原则

本轮所有修改都围绕一个原则：

> **先证明模型没有偷看未来、没有混淆结算口径、没有用不同条件做错误对比，再讨论哪一种策略费用最低。**

不要以“结果接近某个参考答案”为正确性依据。

最终模型必须同时满足：

\[
\boxed{\text{题意一致}}
\]

\[
\boxed{\text{信息因果}}
\]

\[
\boxed{\text{物理可行}}
\]

\[
\boxed{\text{经济目标明确}}
\]

\[
\boxed{\text{代码可复现}}
\]

\[
\boxed{\text{结果可解释}}
\]

只有在上述条件全部满足后，才确定论文正文采用的最终 Q2、Q3、Q4 结果。
