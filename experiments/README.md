# 实验与验证材料

本目录集中保存竞赛报告的验证依据。日常使用请从项目根目录的 `START.bat` 启动，实验可选依赖无需随日常启动安装。

## 目录

| 路径 | 内容 |
|---|---|
| `scripts/` | 系统自检、视觉评测、数据生成、挑战诊断、绘图和上游竞态审计脚本 |
| `tests/` | 入口、网络、证书与 Windows 启动脚本的回归检查 |
| `data/` | 源照片、开发集与固定测试集各 80 张图、标注清单和数据来源说明 |
| `results/` | 与报告对应的指标、逐图预测、十项自检、二维码往返和原实验环境记录 |
| `audit/` | 上游来源、许可核查、运行记录和竞态实验记录 |

`data/manifest.json`、`results/predictions.json` 和 `results/stress.json` 中的图像路径以本目录为基准，例如 `data/test/000.png`。目录迁移不改变图像、模型、选参记录或已归档的实验指标。原实验平台见 `results/setup.json` 和 `audit/environment.txt`，不能将原平台的耗时视为当前电脑的测试结果。

## 自检与复现

以下命令均在**项目根目录**执行，假定已按根目录 README 创建并激活 Python 3.12 虚拟环境。也可在每条 `python` 命令前加 `uv run --locked`。

```powershell
# 十项签到与协议检查
python .\experiments\scripts\check.py

# 双入口、网络、证书与 Windows 脚本回归检查
python -m unittest discover -s experiments/tests

# 固定开发集选参并评估固定测试集
python .\experiments\scripts\evaluate.py

# 旋转、遮挡诊断与原始凭证二维码图片往返检查
python .\experiments\scripts\stress.py
```

**先归档再复跑**：`check.py` 会覆盖 `results/system_checks.json`，`evaluate.py` 会覆盖逐图预测、视觉汇总以及根目录的 `models/policy.json`，`stress.py` 会覆盖诊断与二维码往返结果。请先将这些文件复制到独立备份位置，给新结果标注环境和代码版本，不要把新旧实验记录混用。

重建合成数据或绘图前，安装可选依赖：

```powershell
pip install -e ".[experiments]" -i https://pypi.tuna.tsinghua.edu.cn/simple
# 使用 uv 时改为：uv sync --locked --extra experiments

python .\experiments\scripts\make_data.py
python .\experiments\scripts\plot_results.py --font "C:\Windows\Fonts\msyh.ttc"
```

`make_data.py` 会重建数据清单、合成图片和根目录的体验样例。`stress.py` 按种子 999 重建 40 张挑战图至 `data/stress/`；`plot_results.py` 从已有 JSON 生成四张图至 `results/figures/`。挑战图片、生成图表和重复的评测终端日志已从交付材料中精简，相关生成目录和日志由 `.gitignore` 排除；原指标与失败结果仍保留。

上游竞态审计需要另行取得合法访问权限的参考仓库副本，本项目不分发未获再分发授权的上游代码。只在具备该副本时运行：

```powershell
python .\experiments\scripts\upstream_race.py --upstream-src "D:\参考仓库副本"
```

默认输出为本目录的 `audit/upstream_race_rerun.json`，不会覆盖原 `audit/upstream_race.json`。

## 数据边界与交付

所有视觉合成图共用同一张源照片，只验证受控条件下的工程流程，不代表跨人群、真实活动的准确率。挑战诊断的失败记录同样保留，不用于反向选参。完整来源与许可说明见 [数据说明](data/README.md) 和根目录 [THIRD_PARTY.md](../THIRD_PARTY.md)。

竞赛成果包建议保留本目录，以便核验报告。图表和挑战图片需要时可重新生成。应用会尝试展示 `results/vision_summary.json` 和 `results/system_checks.json`，缺少实验记录时显示提示，不阻止业务页面运行。
