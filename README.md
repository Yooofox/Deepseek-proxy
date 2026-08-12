# DeepSeek Proxy for Android Studio

一个轻量级的本地代理服务器，用于解决 Android Studio LLM 集成与 DeepSeek API 之间的兼容性问题。

---

## 🐛 问题背景

随着 OpenAI API 规范的最新更新，Android Studio（以及各种 LLM 插件）开始发送带有 `"role": "developer"` 的对话消息。

由于 DeepSeek API 目前无法识别 `developer` 这个角色变体，导致请求失败并返回 `400 Bad Request` 反序列化错误：

```text
Model query failed: 400: Failed to deserialize the JSON body into the target type: 
messages[0].role: unknown variant developer, expected one of system, user, assistant, tool...
```

---

## 💡 解决方案

本代理服务器会拦截 Android Studio 发出的请求，自动将 `"role": "developer"` 转换回 `"role": "system"`，然后将修正后的请求无缝转发给 `api.deepseek.com`。

---

## 🚀 快速上手

1. **运行代理**
   启动可执行程序或在本地运行脚本（默认监听 `127.0.0.1:2345`）。

2. **修改 Android Studio 设置**
   在 Android Studio 的 LLM / AI Assistant API 配置中，修改 API Base 地址：
   * **原地址（From）：** `https://api.deepseek.com`
   * **修改为（To）：** `http://127.0.0.1:2345`

3. **完成！**
   现在可以在 Android Studio 中流畅使用 DeepSeek AI 功能，不再引发 Schema 格式报错。

---



A lightweight local proxy server that resolves compatibility issues between Android Studio's LLM integration and the DeepSeek API.

---

## 🐛 The Problem

Following recent updates to the OpenAI API specification, Android Studio (and various LLM plugins) started sending chat messages with `"role": "developer"`. 

Because the DeepSeek API does not currently recognize the `developer` role variant, requests fail with a `400 Bad Request` deserialization error:

```text
Model query failed: 400: Failed to deserialize the JSON body into the target type: 
messages[0].role: unknown variant developer, expected one of system, user, assistant, tool...
```

---

## 💡 The Solution

This proxy intercepts outgoing requests from Android Studio, automatically maps `"role": "developer"` back to `"role": "system"`, and seamlessly forwards the sanitized payload to `api.deepseek.com`.

---

## 🚀 Quick Start

1. **Run the Proxy**
   Launch the executable or run the script on your machine (it will listen on `127.0.0.1:2345` by default).

2. **Update Android Studio Settings**
   In Android Studio's LLM / AI Assistant API configuration, change the API base endpoint:
   * **From:** `https://api.deepseek.com`
   * **To:** `http://127.0.0.1:2345`

3. **Done!**
   Your Android Studio AI features will now work smoothly with DeepSeek without schema errors.

---
