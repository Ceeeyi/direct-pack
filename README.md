# DIRECT-PACK 1.0

根据矩形包装的尺寸、重量和允许朝向，在箱体底面上生成不堆叠的摆放方案，再用独立检查器复算。搜索范围有限：未找到方案不代表无解，找到方案也不等于证明全局最优。

## 运行虚构示例

需要 Python 3.10 或更高版本，无须安装第三方库。在本目录运行：

```sh
python -B runner.py demo.json demo-state.json
python -B check_result.py demo.json demo-state.json
```

示例箱底为 2000 × 1000 mm。两个 1000 × 1000 mm、各重 100 kg 的虚构包装恰好铺满一箱。预期检查结果：`valid: true`、`boxes: 1`、`overall_mean: "1"`。示例数值仅用于演示，不是实际装箱标准。

## 输入与结果

- `parameters`：`L/W/H` 为箱内长宽高（mm），`payload` 为载重上限（kg），`fb` 为前后半箱重量差上限（kg），`lr` 为横向重心偏离中线的上限（mm），`util` 为底面积利用率门槛。`height_check` 决定是否检查箱内高度。
- `items`：每件包装有唯一 `id`、长宽高 `l/w/h`（mm）、重量 `m`（kg）及允许的水平朝向 `allowed`（0 或 90 度）。配平计算假设单件包装质量均匀分布。
- `runner.py` 调用 `solver.py` 和 `allocation.py` 搜索并保存运行状态；`check_result.py` 调用 `audit.py` 独立复核布局。普通模式允许最后一箱仅面积不足，此时 `waiting_human_tail` 表示等待人工决定，不表示可以发运。
- 每个新输入请使用新的状态文件名。同一输入、配置和程序可沿用原状态文件续算。状态文件包含输入明细和布局，实际业务状态文件请勿上传。
