# 512890 红利低波信号系统 PWA

一个面向 **512890红利低波ETF** 的 Streamlit PWA 项目。策略严格按“**T日收盘后出信号，T+1开盘执行**”的口径实现，只允许在 **512890 与现金** 之间切换。

本版本已经升级为 **每日自动更新版**：GitHub Actions 会在每个A股交易日 **北京时间18:15** 运行，自动拉取 512890 与 588000 日线行情，更新策略信号、自动组合状态和历史信号文件，并提交到仓库。

## 项目定位

本项目不是最小可行版，而是一个可继续产品化的研究型仓库：包含策略引擎、状态机、T+1执行模块、每日自动更新脚本、自动组合状态、回测模块、PWA静态资源、iOS淡色系UI、示例数据、测试、Docker和部署配置。

系统使用四个量化信号：

1. **科技/红利相对强弱**：`R = 588000 / 512890`。
2. **512890趋势结构**：MA5、MA10、MA20。
3. **512890承接强度**：CLV，判断是否“利空不跌”。
4. **科技拥挤/钝化**：588000日内CLV、MA5、市场宽度。

输出五档状态：S0空仓、S1观察仓、S2初步确认、S3主仓持有、S4满仓持有。

## 自动更新逻辑

自动更新由 `.github/workflows/daily-signal.yml` 执行：

```yaml
schedule:
  - cron: "15 10 * * 1-5"
```

该时间对应 **北京时间18:15，周一至周五**。运行流程：

1. 安装依赖。
2. 执行 `python scripts/update_daily_snapshot.py`。
3. 拉取最近约120天的 512890 与 588000 ETF日线行情。
4. 合并并去重写入 `data/live_prices.csv`。
5. 如果上一交易日存在待执行信号，用当天开盘价进行T+1模拟执行。
6. 用当天收盘数据生成新信号。
7. 写入：
   - `data/latest_signal.json`
   - `data/auto_portfolio.json`
   - `data/signal_history.csv`
   - `data/update_log.json`
8. 运行 `pytest -q`。
9. 如果数据或信号有变化，自动commit并push。

> 注意：PWA不会自动向券商下单。它只在18:15后生成“下一交易日开盘应执行”的信号。`auto_portfolio.json` 是研究用自动组合跟踪，方便状态可视化和复盘。

## 目录结构

```text
.
├── app.py                         # Streamlit主应用
├── scripts/update_daily_snapshot.py# 每日自动更新入口
├── strategy/                      # 策略核心：指标、评分、状态机、执行、回测、自动组合
├── ui/                            # iOS淡色系UI组件和CSS注入
├── data/sample_prices.csv         # 示例行情数据
├── data/live_prices.csv           # 自动更新行情数据
├── data/latest_signal.json        # 最新策略信号快照
├── data/auto_portfolio.json       # 自动组合状态
├── data/signal_history.csv        # 历史信号记录
├── static/                        # manifest与图标
├── pwa/                           # service worker与注册片段
├── deploy/nginx.conf              # 生产PWA部署示例
├── config/strategy.json           # 策略参数
├── docs/STRATEGY_SPEC.md          # 策略规格说明
└── tests/                         # pytest测试
```

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

打开：

```text
http://localhost:8501
```

## 手动触发一次自动更新

使用真实行情：

```bash
python scripts/update_daily_snapshot.py
```

使用内置示例数据，不访问网络：

```bash
python scripts/update_daily_snapshot.py --offline-sample
```

指定日期，主要用于复现和测试：

```bash
python scripts/update_daily_snapshot.py --end-date 2026-06-19
```

## Docker运行

```bash
docker compose up --build
```

## 数据格式

上传CSV或自动行情CSV需要以下字段：

```text
date,
open_512890, high_512890, low_512890, close_512890, volume_512890, amount_512890,
open_588000, high_588000, low_588000, close_588000, volume_588000, amount_588000,
advancers, decliners
```

`advancers`、`decliners`用于市场宽度；如果没有，可以留空，科技拥挤评分会降级为价格结构判断。

## PWA说明

Streamlit静态文件机制可以通过 `.streamlit/config.toml` 的 `enableStaticServing = true` 开启，并将 `./static/` 文件映射到 `app/static/...`。本项目已经注入manifest和iOS Home Screen meta标签。

完整PWA的service worker需要以 `application/javascript` 的MIME类型从根路径 `/sw.js` 提供。由于Streamlit静态文件服务对非白名单文件会按 `text/plain` 处理并设置 `nosniff`，生产部署时建议使用 `deploy/nginx.conf` 将 `pwa/sw.js` 映射到 `/sw.js`。

纯Streamlit模式：可显示PWA图标、manifest和iOS添加到主屏幕基础能力。

生产模式：通过Nginx或同源静态服务器提供 `/sw.js`，获得更完整的PWA缓存能力。

## 测试

```bash
pytest -q
```

当前检查结果：

```text
9 passed
```

## 重要声明

本项目用于策略研究、信号可视化和回测，不构成投资建议。ETF价格、指数行情、份额和成交数据需要以正式行情源为准。
