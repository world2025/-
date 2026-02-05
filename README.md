# PDF -> Markdown Web

一个最小可用的 Web 服务：上传 PDF，返回可下载的 Markdown 文件。

## 启动

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

打开 <http://127.0.0.1:8000>。

## 并发设计

- `/convert` 接口内部使用 `asyncio.to_thread` 执行 PDF 解析，避免阻塞事件循环。
- 使用 `MAX_CONCURRENT_CONVERSIONS`（默认 `8`）控制转换并发，防止高并发时资源被打满。

示例：

```bash
MAX_CONCURRENT_CONVERSIONS=16 uvicorn main:app --host 0.0.0.0 --port 8000
```

## 测试

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
```

## 行为说明

- 每页会生成 `# 第 N 页` 标题
- 全大写且较短的行会转成二级标题
- 连续空行会归并为一个空段
