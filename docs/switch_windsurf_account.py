#!/usr/bin/env python3
"""
Windsurf 一键切换账号工具
通过 API 获取 token，然后通过 windsurf:// URI 让 Windsurf 自己完成认证存储。

用法: python3 switch_windsurf_account.py <email> [--method auth1|firebase|auto] [--open]

流程:
1. 用 email/password 调用 Windsurf 认证 API 获取 token
2. 构造 windsurf://codeium.windsurf/#access_token=TOKEN URI
3. 通过 xdg-open 打开 URI，Windsurf 自动处理认证
"""
import sys, json, os, time, argparse, urllib.request, urllib.error, subprocess
from pathlib import Path
from urllib.parse import quote

# ─── API URLs ─────────────────────────────────────────────
FIREBASE_API_KEY = 'AIzaSyDsOl-1XpT5err0Tcnx8FFod1H8gVGIycY'
FIREBASE_AUTH_URL = f'https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}'
AUTH1_PASSWORD_LOGIN_URL = 'https://windsurf.com/_devin-auth/password/login'
AUTH1_CONNECTIONS_URL = 'https://windsurf.com/_devin-auth/connections'
WINDSURF_SEAT_BASE = 'https://server.self-serve.windsurf.com/exa.seat_management_pb.SeatManagementService'
WINDSURF_POST_AUTH_URL = f'{WINDSURF_SEAT_BASE}/WindsurfPostAuth'
WINDSURF_ONE_TIME_TOKEN_URL = f'{WINDSURF_SEAT_BASE}/GetOneTimeAuthToken'
CODEIUM_REGISTER_URL = 'https://api.codeium.com/register_user/'

# ─── HTTP helper ──────────────────────────────────────────
def https_post(url, body_dict, extra_headers=None, timeout=20):
    data = json.dumps(body_dict).encode()
    headers = {
        'Content-Type': 'application/json',
        'Content-Length': str(len(data)),
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Origin': 'https://windsurf.com',
        'Referer': 'https://windsurf.com/',
    }
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        try:
            return e.code, json.loads(body)
        except:
            return e.code, {'raw': body[:200]}
    except Exception as e:
        return 0, {'error': str(e)}

# ─── Login methods ────────────────────────────────────────
def login_firebase(email, password):
    """Firebase 登录，返回 idToken"""
    print(f'[Firebase] 登录 {email}...')
    status, data = https_post(FIREBASE_AUTH_URL, {
        'email': email, 'password': password, 'returnSecureToken': True
    })
    if data.get('error'):
        msg = data['error'].get('message', 'Unknown')
        print(f'[Firebase] 失败: {msg}')
        return None
    id_token = data.get('idToken')
    if not id_token:
        print(f'[Firebase] 无 idToken')
        return None
    print(f'[Firebase] 成功')
    return id_token

def login_auth1(email, password):
    """Auth1 登录，返回 {sessionToken, oneTimeAuthToken}"""
    print(f'[Auth1] 登录 {email}...')
    
    # Step 1: password login
    status, data = https_post(AUTH1_PASSWORD_LOGIN_URL, {
        'email': email, 'password': password
    })
    if data.get('detail'):
        print(f'[Auth1] 失败: {data["detail"]}')
        return None
    auth1_token = data.get('token')
    if not auth1_token:
        print(f'[Auth1] 无 token')
        return None
    print(f'[Auth1] 登录成功')

    # Step 2: PostAuth bridge
    status, data = https_post(WINDSURF_POST_AUTH_URL, {
        'auth1Token': auth1_token, 'orgId': ''
    }, {'Connect-Protocol-Version': '1'})
    session_token = data.get('sessionToken')
    if not session_token:
        print(f'[Auth1] PostAuth 失败: {json.dumps(data)[:200]}')
        return None
    print(f'[Auth1] PostAuth 成功')

    # Step 3: One-time token
    status, data = https_post(WINDSURF_ONE_TIME_TOKEN_URL, {
        'authToken': session_token
    }, {'Connect-Protocol-Version': '1'})
    ott = data.get('authToken')
    if not ott:
        print(f'[Auth1] OTT 失败: {json.dumps(data)[:200]}')
        return None
    print(f'[Auth1] OTT 成功')

    return {
        'sessionToken': session_token,
        'oneTimeAuthToken': ott,
    }

def register_codeium(token):
    """用 Codeium 注册获取 apiKey"""
    print(f'[Codeium] 注册...')
    status, data = https_post(CODEIUM_REGISTER_URL, {
        'firebase_id_token': token
    })
    api_key = data.get('api_key')
    if not api_key:
        print(f'[Codeium] 失败: {json.dumps(data)[:200]}')
        return None
    print(f'[Codeium] 成功, apiKey={api_key[:30]}...')
    return data

# ─── Main logic ───────────────────────────────────────────
def switch_account(email, password=None, method='auto', open_uri=False):
    if password is None:
        password = email  # 默认密码=邮箱

    tokens = {}

    if method in ('auto', 'auth1'):
        try:
            result = login_auth1(email, password)
            if result:
                tokens['sessionToken'] = result['sessionToken']
                tokens['oneTimeAuthToken'] = result['oneTimeAuthToken']
        except Exception as e:
            print(f'[Auth1] 异常: {e}')

    if method in ('auto', 'firebase') and not tokens.get('firebase_id_token'):
        try:
            id_token = login_firebase(email, password)
            if id_token:
                tokens['firebase_id_token'] = id_token
        except Exception as e:
            print(f'[Firebase] 异常: {e}')

    if not tokens:
        print('[失败] 所有登录方式均失败')
        return False

    # 尝试 Codeium 注册获取 apiKey（用于直接写入 state.vscdb 的备选方案）
    reg_token = tokens.get('firebase_id_token') or tokens.get('oneTimeAuthToken')
    if reg_token:
        try:
            reg = register_codeium(reg_token)
            if reg:
                tokens['apiKey'] = reg.get('api_key', '')
                tokens['apiServerUrl'] = reg.get('api_server_url', '')
        except Exception as e:
            print(f'[Codeium] 注册异常: {e}')

    # 构造 windsurf:// URI
    # Windsurf 扩展期望 access_token 是 Firebase ID token
    # 优先使用 firebase_id_token，其次 sessionToken，最后 ott
    access_token = tokens.get('firebase_id_token') or tokens.get('sessionToken') or tokens.get('oneTimeAuthToken')
    
    if not access_token:
        print('[失败] 无可用 token')
        return False

    uri = f'windsurf://codeium.windsurf/#access_token={quote(access_token, safe="")}'
    
    print(f'\n=== 获取到的 tokens ===')
    for k, v in tokens.items():
        print(f'  {k}: {v[:40]}...' if len(v) > 40 else f'  {k}: {v}')
    
    print(f'\n=== windsurf URI ===')
    print(f'  {uri[:80]}...')
    
    # 保存 URI 到文件
    uri_file = Path('/tmp/windsurf_switch_uri.txt')
    uri_file.write_text(uri)
    print(f'\nURI 已保存到 {uri_file}')

    # 保存所有 tokens
    tokens_file = Path(f'/tmp/windsurf_tokens_{email.split("@")[0]}.json')
    tokens_file.write_text(json.dumps(tokens, indent=2, ensure_ascii=False))
    print(f'Tokens 已保存到 {tokens_file}')

    if open_uri:
        print(f'\n正在打开 windsurf URI...')
        try:
            subprocess.run(['xdg-open', uri], check=True, timeout=10)
            print('URI 已发送，请观察 Windsurf 是否切换账号')
        except Exception as e:
            print(f'打开失败: {e}')
            print(f'请手动执行: xdg-open \'{uri}\'')
    else:
        print(f'\n手动切换命令:')
        print(f'  xdg-open \'{uri}\'')
    
    return True

def main():
    parser = argparse.ArgumentParser(description='Windsurf 一键切换账号')
    parser.add_argument('email', help='账号邮箱')
    parser.add_argument('--password', help='密码（默认等于邮箱）')
    parser.add_argument('--method', choices=['auto', 'auth1', 'firebase'], default='auto',
                        help='登录方式（默认 auto）')
    parser.add_argument('--open', action='store_true', help='自动打开 windsurf URI')
    parser.add_argument('--retry', type=int, default=1, help='重试次数（默认1）')
    
    args = parser.parse_args()
    password = args.password or args.email

    for attempt in range(args.retry):
        if attempt > 0:
            print(f'\n--- 重试 {attempt + 1}/{args.retry} ---')
            time.sleep(3)
        
        if switch_account(args.email, password, args.method, args.open):
            return
    
    print(f'\n[失败] {args.retry} 次尝试均失败')

if __name__ == '__main__':
    main()
