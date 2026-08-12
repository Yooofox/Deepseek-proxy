# Deepseek-proxy

Android Studio 的大语言模型代理，解决 OpenAI 规范更新与 DeepSeek API 角色定义不兼容

使用 Android Studio 调用 Deepseek API 的时候遇到了“Model query failed: 400: Failed to deserialize the JSON body into the target type: messages[0].role: unknown variant developer, expected one of system, user, assistant, tool, latest_reminder at line 1 column 35744”，网上查不到解决方案，使用 AI 查询后得知是 OpenAI 规范更新与 DeepSeek API 角色定义不兼容，顺手让 AI 写了一个代理，将就着用吧。



An LLM Proxy for Android Studio: Resolving Role Mismatches Between Updated OpenAI Specs and DeepSeek API

I ran into the following error:
Model query failed: 400: Failed to deserialize the JSON body into the target type: messages[0].role: unknown variant developer, expected one of system, user, assistant, tool, latest_reminder at line 1 column 35744
Couldn't find any solutions online, but after asking AI, I learned it stems from a role-definition incompatibility between recent OpenAI specification updates and the DeepSeek API. So, I had AI quickly draft a proxy as a workaround—feel free to use it as a quick fix for now!
