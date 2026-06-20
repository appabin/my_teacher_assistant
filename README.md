# 小学数学互动课件生成器

这个本地应用把课本截图转成可投屏的互动 H5。当前工作流已从小米 MiMo 切换为：

- Qwen 图像理解：识别课本截图、题目、图形、知识点和适合的教学场景
- DeepSeek 页面生成：基于小学数学模板和矢量素材生成互动 HTML
- DeepSeek 引导文案：生成老师可参考的课堂口语引导稿
- TTS：暂不生成音频，`audio_url` 固定为空

## 使用

1. 复制环境变量样例：

```bash
cp .env.example .env
```

2. 编辑 `.env`，填入至少以下配置：

```ini
QWEN_API_KEY=你的 Qwen 或 DashScope Key
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_VISION_MODEL=qwen3.5-omni-plus

DEEPSEEK_API_KEY=你的 DeepSeek Key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-v4-pro
```

3. 启动本地服务：

```bash
./start_teach_assistant.sh
```

4. 打开 http://127.0.0.1:8000

脚本会自动检测 8000 端口上是否已经有教学助手服务在运行；如需临时换端口：

```bash
./start_teach_assistant.sh --port 8001
```

没有配置 API Key 时，网页会默认勾选“模拟运行”，可以先验证上传、模板匹配、预览和保存流程。

## 工作流

1. 浏览器把本地截图压缩为最长边 768px 的 JPEG data URL，API Key 不会传给浏览器。
2. 后端调用 `QWEN_VISION_MODEL` 读取截图并输出自然语言识别摘要；omni 模型会自动使用 `modalities=["text"]` 和流式响应。
3. 后端调用 `DEEPSEEK_MODEL` 把 Qwen 摘要整理为结构化识别 JSON。
4. 后端根据识别结果选择 `templates/math/` 中的 HTML 基底和 `static/assets/math/` 中的 SVG 素材。
5. 后端调用 `DEEPSEEK_MODEL` 生成互动 H5。
6. 后端对生成 HTML 做本地质量检查；如果发现严重问题且 `ENABLE_HTML_REPAIR=true`，会再调用 DeepSeek 修复一次。
   默认 `ALLOW_EXTERNAL_ASSETS=true` 时允许生成页补充使用稳定的 https 图片素材；本地 SVG 仍会优先提供给模型。
7. 后端调用 DeepSeek 生成课堂引导文案。
8. 所有产物保存到 `outputs/{job_id}/`，包括：
   - `analysis.json`
   - `template_context.json`
   - `html_quality.json`
   - `index.html`
   - `guide_script.txt`

一次真实验证已使用历史“租船问题”截图跑通，产物位于 `outputs/20260607-160624-a23de69e/`。该次生成使用旧版 `qwen3.7-plus` 识图，DeepSeek 生成并修复 HTML，`html_quality.json` 检查通过；当前默认识图模型已切换为 `qwen3.5-omni-plus`。

## 模板和素材

当前内置模板：

- `application_reasoning.html`：鸡兔同笼、行程、工程、倍数、等量关系
- `number_operations.html`：数的组成、加减乘除、进位退位、位值、数轴
- `fractions.html`：分数意义、等分、分数比较、同分母加减
- `geometry_2d.html`：周长、面积、方格、平移旋转、平面图形
- `solid_geometry_3d.html`：长方体、正方体、圆柱圆锥、体积表面积、三视图
- `time_money.html`：钟表、经过时间、人民币、购物、找零
- `measurement_units.html`：长度、质量、角、单位换算、估测
- `data_statistics.html`：数据整理、条形统计图、象形统计图、折线统计图

当前内置 SVG 素材在 `static/assets/math/`，包括鸡、兔、个位块、十根、百板、分数圆、分数条、天平、数轴、方格纸、立体图形、钟面、人民币、购物篮、直尺、卷尺、秤、量角器、统计图、小木棍、小朋友、大小船、船桨、救生圈、座位、公交车、苹果、铅笔、书本和积木。

## 配置优先级

程序优先读取系统环境变量，其次读取项目根目录 `.env`，最后读取 `config.ini`。推荐使用 `.env`。

可用别名：

- Qwen Key：`QWEN_API_KEY`、`QWEN3_7_PLUS_API_KEY`、`DASHSCOPE_API_KEY`、`VISION_API_KEY`
- Qwen Key：也兼容 `QWEN_ANSWER_API_KEY`
- Qwen 模型：`QWEN_VISION_MODEL`、`QWEN_ANSWER_MODEL`、`QWEN_MODEL`、`VISION_MODEL`
- DeepSeek Key：`DEEPSEEK_API_KEY`、`DEEPSEEK_V4_API_KEY`、`PAGE_API_KEY`、`ANSWER_API_KEY`、`ROUTER_API_KEY`
- DeepSeek 模型：`DEEPSEEK_MODEL`、`DEEPSEEK_V4_MODEL`、`PAGE_MODEL`、`ANSWER_MODEL`、`ROUTER_MODEL`
- HTML 修复开关：`ENABLE_HTML_REPAIR=true|false`
- 外网图片素材开关：`ALLOW_EXTERNAL_ASSETS=true|false`

## 注意

生成的 HTML 由模型输出，服务只适合在本机或可信内网运行，不要直接暴露到公网。预览 iframe 使用 `sandbox="allow-scripts"`，仍建议人工检查后再用于正式课堂。
