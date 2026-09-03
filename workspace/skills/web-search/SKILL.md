---
name: web-search
description: 用户要网上搜索、查资料、look up / search the web 时使用；调用 web.search，用返回链接回答。
---

# 网上搜索

当用户说「网上查一下」「搜索一下」「帮我查」「search online」等：

1. 调用工具 `web.search`，`query` 用用户要查的关键词（可略作整理，不要丢关键实体名）
2. 只根据工具返回的 `results` / `reply_text` 回答
3. 回复必须带上标题和可点击链接；不要编造 URL
4. 用中文简短总结 2～4 条即可，除非用户要求更多
