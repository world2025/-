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

## 行为说明

- 每页会生成 `# 第 N 页` 标题
- 全大写且较短的行会转成二级标题
- 连续空行会归并为一个空段
