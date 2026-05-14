# Kernel1 MVP

Socionics 单次判型 prototype。

## 图形界面

在项目根目录运行：

```powershell
cd D:\guCodex\shiroProject
python -m uvicorn kernel1.app:app --host 127.0.0.1 --port 8787
```

然后浏览器打开：

```text
http://127.0.0.1:8787/
```

页面可以填写：

- 是否使用本地 LLM
- OpenAI-compatible 监听地址，例如 `http://127.0.0.1:8000/v1/chat/completions`
- 模型名，例如 `qwen3.6-27b`
- API Key，vLLM 本地服务一般可填 `EMPTY`
- 待分析文章 / 自述文本

如果不勾选“使用本地 LLM”，系统会使用内置启发式 fallback 跑通流程。

## 启动脚本

也可以直接运行根目录脚本：

```powershell
cd D:\guCodex\shiroProject
.\start_kernel1_api.ps1
```

如果 `8787` 被占用：

```powershell
.\start_kernel1_api.ps1 -Port 8789
```

## 命令行运行

```powershell
cd D:\guCodex\shiroProject
python -m kernel1.cli --text-file .\kernel1\samples\sample_input.txt --case-id sample-001 --report-only
```

## API 调用

```powershell
$body = @{
  case_id = "api-test-001"
  text = Get-Content -Raw .\kernel1\samples\sample_input.txt
  llm_enabled = $false
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/kernel1/analyze -ContentType "application/json; charset=utf-8" -Body $body
```

使用本地 LLM：

```powershell
$body = @{
  case_id = "qwen-test-001"
  text = Get-Content -Raw .\kernel1\samples\sample_input.txt
  llm_enabled = $true
  llm_base_url = "http://127.0.0.1:8000/v1/chat/completions"
  llm_model = "qwen3.6-27b"
  llm_api_key = "EMPTY"
  llm_timeout = 90
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/kernel1/analyze -ContentType "application/json; charset=utf-8" -Body $body
```

## 输出位置

- `kernel1/outputs/*.json`
- `kernel1/logs/kernel1.log`
