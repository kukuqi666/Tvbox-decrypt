# Tvbox-decrypt

TVBox / 影视仓 配置接口解密工具，两种形态：

| 目录 | 形态 | 说明 |
|---|---|---|
| 根目录（Vue） | 在线解密页 | 原「视频源解密」前端，`https://kukuqi666.github.io/Tvbox-decrypt/` |
| `mirror/` | 自动解密镜像 | GitHub Actions 定时抓取并解密，产出**静态 JSON** 发布到 Pages |
| `selfhost/` | PHP 自托管版 | 独立 `box.php` 后端 + 前端，扔进任意 PHP 主机即可用 |

---

## mirror — 自动解密镜像（推荐）

原理：GitHub Pages 跑不了 PHP，于是用 **GitHub Actions（服务器端 curl + Python）** 定时解密，把结果当静态文件发布。

### 使用

Actions 每次运行（每日 03:20 UTC 自动 / push / 手动）会遍历 `mirror/lines.txt` 里的线路，逐个解密成 `<名称>.json`，发布到：

```
https://kukuqi666.github.io/Tvbox-decrypt/mirror/index.html   <- 索引页（状态一览）
https://kukuqi666.github.io/Tvbox-decrypt/mirror/饭太硬.json    <- 解密后的配置，直接给 TVBox 用
```

TVBox 里把上面任一 `.json` 地址填进「配置地址」即可，**原站挂了也不受影响**。

### 维护

- **加/改线路**：编辑 `mirror/lines.txt`（格式 `名称|URL`），push 即触发重新解密。
- **改解密逻辑**：编辑 `mirror/decrypt.py`（支持图片隐写 / base64 / 明文三种，自动探测）。
- 手动刷一次：GitHub 仓库 -> Actions -> Deploy -> Run workflow。

---

## selfhost — PHP 自托管版

给有 PHP 主机 / VPS 的人，纯自建解密服务（不依赖任何第三方 API）：

```
selfhost/box.php      # 解密后端（自动识别加密方式，去广告，带 CORS）
selfhost/index.html   # 前端（33 条预设线路 + 复制结果 + 下载 spider jar）
```

部署：两个文件扔进任意 nginx/apache 站点目录，访问 `index.html` 即可。
本地预览：`php -S 0.0.0.0:8023` 后开 `http://127.0.0.1:8023/`。

---

## 解密算法（饭太硬实测还原）

1. 用 `okhttp/3.12.0` UA 请求接口（浏览器 UA 会拿到 302/首页，okhttp UA 才给加密包）；
2. 服务器返回一张 **JPEG**（伪装 `image/x-ms-bmp`），图片 `FFD9` 结束标记后附加加密数据；
3. 加密数据 = 自定义前缀 + **base64**，剥前缀、base64 解码、去掉 `//` 注释，即得配置 JSON；
4. `spider` 字段自带 `;md5;<hash>`，与实际下载 jar 的 MD5 一致（解密正确性可自证）。
