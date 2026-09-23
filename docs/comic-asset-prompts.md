# Web 阶段 8 漫画资产生成记录

生成模式：Codex 内置图像生成工具。以下为这一版 MVP 候选资产的最终提示词集。

## 四格主页

> Create a cohesive 2x2 four-panel family comic page with no text, speech bubbles, captions, logos, or watermarks. Warm editorial children's-book illustration, textured gouache and colored pencil, sophisticated but playful. The same three Chinese family characters must remain unmistakably consistent in every panel: father in a deep teal sweater, young child in a coral hoodie, grandmother in a mustard cardigan. Cozy cream-and-wood dining room at night. Story sequence: family chatting over dinner; father accidentally drops a tomato into soup; everyone reacts and laughs; warm quiet closing moment around the table. Clear panel boundaries, varied cinematic framing, expressive faces, coral/teal/mustard palette, suitable for adding UI text overlays later.

## 第 2 格重画备选

> Redraw only panel 2 of the referenced four-panel family dinner comic as one standalone landscape illustration. Preserve the exact same three characters and visual bible: Chinese father with same face/hair and deep teal sweater, same young child in coral hoodie, same grandmother in mustard cardigan; same warm editorial gouache-and-colored-pencil style and cream/wood dining room. Capture the comic turning point: father has just accidentally dropped a tomato into the soup, with a small playful splash and surprised amused reactions. No text, captions, speech bubbles, logos, or watermark. Leave clear negative space near the upper-left/upper-center for an app-rendered dialogue bubble.

## 工作区产物

- `web/public/assets/comics/family-dinner-four-panel-v1.png`
- `web/public/assets/comics/family-dinner-panel-2-v2.png`

这两张图是 MVP 演示资产。当前后端通过本地资产适配器选用，尚未对每个家庭故事实时调用生图服务。
