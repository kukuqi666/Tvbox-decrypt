<?php
/**
 * box.php — 自研 TVBox 配置接口解密服务（等价 fongmi 版，去掉广告、加 CORS、支持多加密方式自动探测）
 *
 * 用法：
 *   GET /box.php?url=<加密接口地址>
 *   GET /box.php?url=<加密接口地址>&raw=1         返回纯净 JSON（无外层包装）
 *   GET /box.php?url=<加密接口地址>&json=1         强制按 JSON 返回
 *
 * 支持的加密方式（自动探测）：
 *   1. 图片隐写（JPEG/BMP 尾部 FFD9 之后附加 base64）          —— 饭太硬 等
 *   2. 纯 base64 整段                                         —— 部分线路
 *   3. 图片隐写 + 自定义前缀 + base64
 *   4. 明文 JSON 直出                                          —— 无需解密
 *
 * 依赖：PHP 8.x + curl 扩展
 * 部署：扔进任意 nginx/apache 站点目录即可，前台用 index.html 调它。
 */

header('Content-Type: application/json; charset=utf-8');
// 允许跨域（静态前端页直接 fetch 本服务）
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { http_response_code(204); exit; }

$url = $_GET['url'] ?? '';
$raw = isset($_GET['raw']);
if ($url === '' || !preg_match('#^https?://#i', $url)) {
    http_response_code(400);
    echo json_encode(['error' => '缺少合法 url 参数，示例: /box.php?url=http://xxx/tv'], JSON_UNESCAPED_UNICODE);
    exit;
}

// ---- 抓取：关键是用 okhttp UA 触发服务端吐加密数据 ----
[$body, $ctype] = fetch_url($url);
if ($body === false) {
    http_response_code(502);
    echo json_encode(['error' => '抓取目标失败（上游不可达/超时）'], JSON_UNESCAPED_UNICODE);
    exit;
}

// ---- 解密 ----
$plain = decrypt($body, $ctype);

// ---- 输出：去掉 // 和 /* */ 注释，给干净 JSON ----
$clean = strip_json_comments($plain);

if ($raw) {
    // 原样输出解密结果（给 TVBox 直接当配置用）
    header('Content-Type: text/json; charset=utf-8');
    echo $clean;
    exit;
}

// 默认包一层，附上解密索引便于前端弹提示
echo json_encode([
    'ok'    => true,
    'url'   => $url,
    'type'  => detected_type($body, $ctype),
    'size'  => strlen($clean),
    'data'  => $clean,          // 解密后的完整配置文本
], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);

/* ------------------------------------------------------------------ */

function fetch_url(string $url): array {
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_FOLLOWLOCATION => true,
        CURLOPT_MAXREDIRS      => 5,
        CURLOPT_TIMEOUT        => 40,
        CURLOPT_CONNECTTIMEOUT => 15,
        CURLOPT_USERAGENT      => 'okhttp/3.12.0',   // 触发服务端派发加密包的 UA
        CURLOPT_SSL_VERIFYPEER => false,
        CURLOPT_SSL_VERIFYHOST => false,
        CURLOPT_HTTPHEADER     => ['Accept: */*'],
    ]);
    $body  = curl_exec($ch);
    $ctype = (string)curl_getinfo($ch, CURLINFO_CONTENT_TYPE);
    $err   = curl_error($ch);
    curl_close($ch);
    if ($body === false) return [false, $ctype];
    return [$body, $ctype];
}

function detected_type(string $body, string $ctype): string {
    if (strpos($ctype, 'image') !== false || substr($body, 0, 2) === "\xff\xd8" || substr($body, 0, 2) === 'BM') {
        return 'image-stego';
    }
    $t = ltrim($body);
    if ($t === '') return 'empty';
    return 'plain';
}

function decrypt(string $body, string $ctype): string {
    $candidates = [];

    // 图片隐写：优先取 JPEG EOI(FFD9) / BMP 数据后的尾随段
    if (substr($body, 0, 2) === "\xff\xd8") {
        $pos = strrpos($body, "\xff\xd9");
        if ($pos !== false && $pos + 2 < strlen($body)) {
            $candidates[] = substr($body, $pos + 2);
        }
    } elseif (substr($body, 0, 2) === 'BM') {
        // BMP: 文件头里 data-offset(0x0A) 之后是像素；加密数据在像素尾，这里也整段尝试
        $candidates[] = $body;
    }

    // 原样也试（纯 base64 / 明文 JSON）
    $candidates[] = $body;

    foreach ($candidates as $blob) {
        $blob = trim($blob);
        if ($blob === '') continue;

        // 方式A：整段 base64（先剔除非 base64 字符，兼容任意自定义前缀）
        $clean = preg_replace('/[^A-Za-z0-9+\/=]/', '', $blob);
        if ($clean !== '' && strlen($clean) >= 4) {
            $dec = @base64_decode($clean);   // 非 strict，容忍尾部杂项
            if ($dec !== false && ($p = json_start($dec)) !== false) {
                return substr($dec, $p);
            }
        }

        // 方式B：blob 本身已含 JSON（明文直出/嵌在注释里）
        if (($p = json_start($blob)) !== false) {
            return substr($blob, $p);
        }
    }

    // 全失败：原样返回（交给上层看）
    return $body;
}

// 找 JSON 起始符 { 或 [
function json_start(string $s): int|false {
    $a = strpos($s, '{');
    $b = strpos($s, '[');
    if ($a === false) return $b;
    if ($b === false) return $a;
    return min($a, $b);
}

// 去 // 行注释与 /* */ 块注释（TVBox 配置常带注释）
function strip_json_comments(string $s): string {
    $s = preg_replace('#^\s*//[^\r\n]*$#m', '', $s);       // 行注释
    $s = preg_replace('#/\*.*?\*/#s', '', $s);              // 块注释
    return trim($s);
}