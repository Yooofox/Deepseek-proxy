import sys
import json
import re
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager

import tkinter as tk
from tkinter import scrolledtext, messagebox
import threading

from fastapi import FastAPI, Request
from fastapi.responses import Response, StreamingResponse
import httpx
import uvicorn

# --- Default Global Configurations / 默认全局参数 ---
TARGET_URL = "https://api.deepseek.com"
TARGET_CONTEXT_WINDOW = 65536  # 64k
PORT = 2345


# --- GUI Logger / GUI 日志管理器 ---
class GUILogger:
    def __init__(self, max_lines=1000):
        self.text_widget = None
        self.enabled_var = None
        self.max_lines = max_lines
        self.current_line_count = 0

    def setup_ui_refs(self, widget, enabled_var):
        self.text_widget = widget
        self.enabled_var = enabled_var

    def log(self, level: str, message: str):
        # Check if logging is enabled / 检查日志开关
        if self.enabled_var and not self.enabled_var.get():
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted = f"[{timestamp}] [{level:<5}] {message}\n"
        print(formatted, end="")  # Sync output to console / 控制台同步输出

        if self.text_widget:
            self.text_widget.after(0, self._append_text, formatted)

    def _append_text(self, text):
        try:
            # Prevent lag: limit max line count / 防卡顿：控制最大行数
            if self.current_line_count >= self.max_lines:
                self.text_widget.delete("1.0", "200.0")
                self.current_line_count -= 200

            self.text_widget.insert(tk.END, text)
            self.current_line_count += 1
            self.text_widget.see(tk.END)
        except Exception:
            pass

    def clear(self):
        if self.text_widget:
            self.text_widget.delete("1.0", tk.END)
            self.current_line_count = 0


gui_logger = GUILogger(max_lines=1000)

# --- Server Control & Client Connection Pool / 服务控制与连接池 ---
client = None
server_instance = None
server_thread = None


def get_client():
    global client
    if client is None or client.is_closed:
        client = httpx.AsyncClient(
            timeout=300.0,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
        )
    return client


@asynccontextmanager
async def lifespan(app: FastAPI):
    gui_logger.log("INFO", f"Proxy Service Started - Listening on http://127.0.0.1:{PORT}")
    yield
    global client
    if client and not client.is_closed:
        await client.aclose()
    gui_logger.log("INFO", "Proxy Service Stopped")


app = FastAPI(lifespan=lifespan)


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy(request: Request, path: str):
    global TARGET_URL, TARGET_CONTEXT_WINDOW

    # Auto-fix route prefix / 路径格式标准化
    if not path.startswith("v1/") and path != "v1":
        real_path = f"v1/{path}"
    else:
        real_path = path

    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)

    body = await request.body()

    if request.method == "POST" and "application/json" in headers.get("content-type", "").lower():
        try:
            body_str = body.decode("utf-8")

            # Replace 'developer' role with 'system' / 兼容性修复：developer -> system
            if '"developer"' in body_str:
                body_str = re.sub(r'("role"\s*:\s*)"developer"', r'\1"system"', body_str)
                gui_logger.log("DEBUG", "  [FIX] Replaced 'developer' role with 'system'")

            body_json = json.loads(body_str)

            # --- 1. Reroute /responses to /v1/chat/completions / 重定向 /responses 接口 ---
            if real_path.endswith("responses"):
                real_path = "v1/chat/completions"
                gui_logger.log("DEBUG", "  [REROUTE] Mapped /responses -> /v1/chat/completions")

                messages = []
                if "instructions" in body_json and body_json["instructions"]:
                    messages.append({"role": "system", "content": body_json.pop("instructions")})

                inp = body_json.pop("input", None)
                if isinstance(inp, str) and inp:
                    messages.append({"role": "user", "content": inp})
                elif isinstance(inp, list):
                    messages.extend(inp)

                if "messages" not in body_json or not body_json["messages"]:
                    body_json["messages"] = messages

            # --- 2. Clean unsupported OpenAI parameters / 清洗 DeepSeek 不支持的参数 ---
            unsupported_keys = [
                "reasoning_effort",
                "stream_options",
                "parallel_tool_calls",
                "store",
                "metadata",
                "modalities",
                "audio"
            ]
            cleaned_keys = []
            for key in unsupported_keys:
                if key in body_json:
                    del body_json[key]
                    cleaned_keys.append(key)

            if cleaned_keys:
                gui_logger.log("DEBUG", f"  [CLEAN] Removed unsupported keys: {cleaned_keys}")

            if "max_tokens" in body_json and body_json["max_tokens"] < 8192:
                body_json["max_tokens"] = 8192

            gui_logger.log("DEBUG", f"  [Payload] Cleaned Keys: {list(body_json.keys())}")
            body = json.dumps(body_json).encode("utf-8")
        except Exception as e:
            gui_logger.log("ERROR", f"  [WARN] Request body parse/adapt failed: {e}")

    url = f"{TARGET_URL}/{real_path}"
    gui_logger.log("INFO", f"--> {request.method} /{path} -> /{real_path}")

    cli = get_client()
    req = cli.build_request(
        method=request.method,
        url=url,
        headers=headers,
        content=body
    )

    try:
        res = await cli.send(req, stream=True)
    except Exception as e:
        gui_logger.log("ERROR", f"  [ERROR] Network request failed: {e}")
        return Response(
            content=json.dumps({"error": str(e)}),
            status_code=502,
            headers={"content-type": "application/json"}
        )

    gui_logger.log("INFO", f"<-- Status {res.status_code} for /{path}")

    # Inject context window for models endpoint / 特殊处理 models 接口注入上下文上限
    if real_path.endswith("models") and res.status_code == 200:
        await res.aread()
        try:
            models_data = res.json()
            if "data" in models_data:
                for model in models_data["data"]:
                    model["context_window"] = TARGET_CONTEXT_WINDOW
                    model["max_input_tokens"] = TARGET_CONTEXT_WINDOW
                gui_logger.log("DEBUG", f"  [MOD] Injected {TARGET_CONTEXT_WINDOW} context window into models response")
            return Response(
                content=json.dumps(models_data),
                status_code=res.status_code,
                headers={"content-type": "application/json"}
            )
        except Exception as e:
            gui_logger.log("ERROR", f"  [WARN] Model injection failed: {e}")

    response_headers = dict(res.headers)
    response_headers.pop("content-length", None)
    response_headers.pop("content-encoding", None)

    async def stream_generator():
        try:
            async for chunk in res.aiter_raw():
                yield chunk
        finally:
            await res.aclose()

    return StreamingResponse(
        stream_generator(),
        status_code=res.status_code,
        headers=response_headers
    )


def start_server_thread():
    global server_instance, server_thread, PORT

    def run():
        global server_instance
        try:
            config = uvicorn.Config(
                app,
                host="127.0.0.1",
                port=PORT,
                log_level="error",
                log_config=None
            )
            server_instance = uvicorn.Server(config)
            server_instance.run()
        except Exception as e:
            gui_logger.log("ERROR", f"Failed to start server on port {PORT}: {e}")

    server_thread = threading.Thread(target=run, daemon=True)
    server_thread.start()


def restart_server():
    global server_instance, client
    gui_logger.log("INFO", "Restarting Proxy Server...")

    if client and not client.is_closed:
        asyncio.run(client.aclose())
        client = None

    if server_instance:
        server_instance.should_exit = True
        server_instance = None

    threading.Thread(target=_do_restart, daemon=True).start()


def _do_restart():
    import time
    time.sleep(1.0)
    start_server_thread()


def main():
    global TARGET_URL, PORT, TARGET_CONTEXT_WINDOW

    root = tk.Tk()
    root.title("API Local Proxy Control Panel")
    root.geometry("860x600")
    root.configure(bg="#f5f5f5")

    # 1. Header Bar / 顶部标题栏
    title_frame = tk.Frame(root, bg="#2b2b2b", pady=6)
    title_frame.pack(fill=tk.X)
    title_label = tk.Label(
        title_frame,
        text=f"API Local Proxy | Endpoint: http://127.0.0.1:{PORT}/v1",
        font=("Segoe UI", 10, "bold"),
        bg="#2b2b2b",
        fg="#ffffff"
    )
    title_label.pack()

    # 2. Config Panel / 参数配置区
    config_frame = tk.LabelFrame(
        root,
        text=" Configuration / 参数设置 ",
        bg="#f5f5f5",
        font=("Segoe UI", 9, "bold"),
        padx=10,
        pady=8
    )
    config_frame.pack(fill=tk.X, padx=8, pady=6)

    # Line 1: Target URL Entry / 目标网址
    f_url = tk.Frame(config_frame, bg="#f5f5f5")
    f_url.pack(fill=tk.X, pady=2)
    lbl_url = tk.Label(f_url, text="Target API URL / 目标网址:", width=22, anchor="w", bg="#f5f5f5",
                       font=("Segoe UI", 9))
    lbl_url.pack(side=tk.LEFT)
    url_var = tk.StringVar(value=TARGET_URL)
    ent_url = tk.Entry(f_url, textvariable=url_var, font=("Consolas", 9))
    ent_url.pack(side=tk.LEFT, fill=tk.X, expand=True)

    # Line 2: Port & Context Window / 端口与上下文大小
    f_num = tk.Frame(config_frame, bg="#f5f5f5")
    f_num.pack(fill=tk.X, pady=2)

    lbl_port = tk.Label(f_num, text="Port / 端口:", width=22, anchor="w", bg="#f5f5f5", font=("Segoe UI", 9))
    lbl_port.pack(side=tk.LEFT)
    port_var = tk.StringVar(value=str(PORT))
    ent_port = tk.Entry(f_num, textvariable=port_var, width=10, font=("Consolas", 9))
    ent_port.pack(side=tk.LEFT, padx=(0, 20))

    lbl_ctx = tk.Label(f_num, text="Context Window / 上下文:", bg="#f5f5f5", font=("Segoe UI", 9))
    lbl_ctx.pack(side=tk.LEFT, padx=(0, 5))
    ctx_var = tk.StringVar(value=str(TARGET_CONTEXT_WINDOW))
    ent_ctx = tk.Entry(f_num, textvariable=ctx_var, width=12, font=("Consolas", 9))
    ent_ctx.pack(side=tk.LEFT)

    # 3. Control Panel & Buttons / 控制按钮栏
    control_frame = tk.Frame(root, bg="#f5f5f5", padx=8, pady=4)
    control_frame.pack(fill=tk.X)

    log_enabled_var = tk.BooleanVar(value=True)
    chk_enable = tk.Checkbutton(
        control_frame,
        text="Enable Log / 启用日志",
        variable=log_enabled_var,
        bg="#f5f5f5",
        font=("Segoe UI", 9)
    )
    chk_enable.pack(side=tk.LEFT)

    # Save & Restart Callback / 保存参数并重启逻辑
    def apply_config_and_restart():
        global TARGET_URL, PORT, TARGET_CONTEXT_WINDOW

        new_url = url_var.get().strip().rstrip("/")
        new_port_str = port_var.get().strip()
        new_ctx_str = ctx_var.get().strip()

        if not new_url.startswith(("http://", "https://")):
            messagebox.showerror("Error / 错误",
                                 "Target URL must start with http:// or https://\n目标 URL 必须以 http:// 或 https:// 开头")
            return

        try:
            new_port = int(new_port_str)
            new_ctx = int(new_ctx_str)
        except ValueError:
            messagebox.showerror("Error / 错误",
                                 "Port and Context Window must be valid numbers!\n端口和上下文必须为有效数字！")
            return

        # Update Globals / 更新全局变量
        TARGET_URL = new_url
        PORT = new_port
        TARGET_CONTEXT_WINDOW = new_ctx

        # Update Header Display / 更新标题栏展示
        title_label.config(text=f"API Local Proxy | Endpoint: http://127.0.0.1:{PORT}/v1")
        gui_logger.log("INFO", f"Saved Config -> URL: {TARGET_URL} | Port: {PORT} | Context: {TARGET_CONTEXT_WINDOW}")

        # Restart Proxy / 重启服务
        restart_server()

    btn_apply = tk.Button(
        control_frame,
        text="Save & Restart / 保存并重启",
        command=apply_config_and_restart,
        font=("Segoe UI", 9, "bold"),
        bg="#e1f5fe",
        relief="groove",
        padx=10
    )
    btn_apply.pack(side=tk.RIGHT, padx=(5, 0))

    btn_clear = tk.Button(
        control_frame,
        text="Clear / 清空日志",
        command=lambda: gui_logger.clear(),
        font=("Segoe UI", 9),
        bg="#ffffff",
        relief="groove",
        padx=10
    )
    btn_clear.pack(side=tk.RIGHT)

    # 4. Log Text Area / 日志展示区
    log_area = scrolledtext.ScrolledText(
        root,
        font=("Consolas", 10),
        bg="#ffffff",
        fg="#000000",
        insertbackground="black",
        selectbackground="#0078d7",
        selectforeground="white",
        wrap=tk.WORD
    )
    log_area.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

    gui_logger.setup_ui_refs(log_area, log_enabled_var)
    gui_logger.log("INFO", "Initializing Local Proxy Server...")

    start_server_thread()

    root.mainloop()


if __name__ == "__main__":
    main()
