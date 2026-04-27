#!/usr/bin/env python3
"""
验证：通过 WindsurfAPI 的登录 API 获取 token，写入 state.vscdb，看 Windsurf 是否识别。
用法: python3 verify_api_login.py <email>
密码默认等于邮箱（账号池规则）
"""
import sys, json, sqlite3, os, time, random, string, urllib.request, urllib.error
from pathlib import Path

HOME = Path.home()
STATE_VSCDB = HOME / ".config/Windsurf/User/globalStorage/state.vscdb"

FIREBASE_API_KEY = 'AIzaSyDsOl-1XpT5err0Tcnx8FFod1H8gVGIycY'
FIREBASE_AUTH_URL = f'https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}'
CODEIUM_REGISTER_URL = 'https://api.codeium.com/register_user/'
AUTH1_CONNECTIONS_URL = 'https://windsurf.com/_devin-auth/connections'
AUTH1_PASSWORD_LOGIN_URL = 'https://windsurf.com/_devin-auth/password/login'
WINDSURF_SEAT_BASE = 'https://server.self-serve.windsurf.com/exa.seat_management_pb.SeatManagementService'
WINDSURF_POST_AUTH_URL = f'{WINDSURF_SEAT_BASE}/WindsurfPostAuth'
WINDSURF_ONE_TIME_TOKEN_URL = f'{WINDSURF_SEAT_BASE}/GetOneTimeAuthToken'

OS_VERSIONS = ['X11; Linux x86_64', 'X11; Ubuntu; Linux x86_64',
               'Windows NT 10.0; Win64; x64', 'Macintosh; Intel Mac OS X 14_2_1']
CHROME_VERSIONS = [f'{v}.0.0.0' for v in range(125, 135)]

def pick(arr): return random.choice(arr)

def make_ua():
    os_v = pick(OS_VERSIONS)
    cv = pick(CHROME_VERSIONS)
    return f'Mozilla/5.0 ({os_v}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{cv} Safari/537.36'

def https_post(url, body_dict, extra_headers=None):
    data = json.dumps(body_dict).encode()
    headers = {'Content-Type': 'application/json', 'User-Agent': make_ua(),
               'Accept': 'application/json', 'Origin': 'https://windsurf.com',
               'Referer': 'https://windsurf.com/'}
    if extra_headers: headers.update(extra_headers)
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

def login_firebase(email, password):
    print(f'[Firebase] 尝试登录 {email}...')
    status, data = https_post(FIREBASE_AUTH_URL,
        {'email': email, 'password': password, 'returnSecureToken': True})
    if data.get('error'):
        msg = data['error'].get('message', '')
        print(f'[Firebase] 失败: {msg}')
        return None
    id_token = data.get('idToken')
    print(f'[Firebase] 成功, UID={data.get("localId","?")}')
    return id_token

def login_auth1(email, password):
    print(f'[Auth1] 尝试登录 {email}...')
    # Step 1: check connections
    status, conn_data = https_post(AUTH1_CONNECTIONS_URL, {'product': 'windsurf', 'email': email})
    method = conn_data.get('auth_method', {}).get('method', '')
    has_pwd = conn_data.get('auth_method', {}).get('has_password', True)
    print(f'[Auth1] method={method}, has_password={has_pwd}')
    if not has_pwd:
        print('[Auth1] 该账号未设置密码，跳过')
        return None

    # Step 2: password login
    status, login_data = https_post(AUTH1_PASSWORD_LOGIN_URL, {'email': email, 'password': password})
    if login_data.get('detail'):
        print(f'[Auth1] 登录失败: {login_data["detail"]}')
        return None
    auth1_token = login_data.get('token')
    if not auth1_token:
        print(f'[Auth1] 无 token: {json.dumps(login_data)[:200]}')
        return None
    print(f'[Auth1] 登录成功')

    # Step 3: PostAuth bridge
    status, bridge_data = https_post(WINDSURF_POST_AUTH_URL,
        {'auth1Token': auth1_token, 'orgId': ''},
        {'Connect-Protocol-Version': '1'})
    session_token = bridge_data.get('sessionToken')
    if not session_token:
        print(f'[Auth1] PostAuth 失败: {json.dumps(bridge_data)[:200]}')
        return None
    print(f'[Auth1] PostAuth 成功, account={bridge_data.get("accountId","?")}')

    # Step 4: One-time token
    status, ott_data = https_post(WINDSURF_ONE_TIME_TOKEN_URL,
        {'authToken': session_token},
        {'Connect-Protocol-Version': '1'})
    ott = ott_data.get('authToken')
    if not ott:
        print(f'[Auth1] OTT 失败: {json.dumps(ott_data)[:200]}')
        return None
    print(f'[Auth1] OTT 成功')
    return ott

def register_codeium(token):
    print(f'[Codeium] 注册...')
    status, data = https_post(CODEIUM_REGISTER_URL, {'firebase_id_token': token})
    api_key = data.get('api_key')
    if not api_key:
        print(f'[Codeium] 失败: {json.dumps(data)[:200]}')
        return None
    print(f'[Codeium] 成功, apiKey={api_key[:30]}...')
    return data

def write_auth_to_state(api_key, email, api_server_url=''):
    """将 apiKey 写入 state.vscdb 的 windsurfAuthStatus"""
    if not STATE_VSCDB.exists():
        print(f'[写入] state.vscdb 不存在: {STATE_VSCDB}')
        return False

    conn = sqlite3.connect(str(STATE_VSCDB))
    c = conn.cursor()

    # 读取当前 windsurfAuthStatus
    c.execute("SELECT value FROM ItemTable WHERE key = 'windsurfAuthStatus'")
    row = c.fetchone()
    if row:
        try:
            current = json.loads(row[0] if isinstance(row[0], str) else row[0].decode('utf-8','surrogatepass'))
        except:
            current = {}
    else:
        current = {}

    # 更新 apiKey
    current['apiKey'] = api_key
    new_value = json.dumps(current, ensure_ascii=False)

    c.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)",
              ('windsurfAuthStatus', new_value))

    # 更新 codeium.windsurf 中的 lastLoginEmail
    c.execute("SELECT value FROM ItemTable WHERE key = 'codeium.windsurf'")
    row2 = c.fetchone()
    if row2:
        try:
            cw = json.loads(row2[0] if isinstance(row2[0], str) else row2[0].decode('utf-8','surrogatepass'))
        except:
            cw = {}
    else:
        cw = {}
    cw['lastLoginEmail'] = email
    if api_server_url:
        cw['apiServerUrl'] = api_server_url
    c.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)",
              ('codeium.windsurf', json.dumps(cw, ensure_ascii=False)))

    conn.commit()
    conn.close()
    print(f'[写入] 已更新 windsurfAuthStatus 和 codeium.windsurf')
    return True

def main():
    if len(sys.argv) < 2:
        print(f'用法: python3 {sys.argv[0]} <email>')
        print('密码默认等于邮箱')
        return

    email = sys.argv[1]
    password = email  # 密码=邮箱

    # 先尝试 Auth1，再 Firebase
    token = None
    auth_method = None

    # Auth1
    try:
        ott = login_auth1(email, password)
        if ott:
            token = ott
            auth_method = 'auth1'
    except Exception as e:
        print(f'[Auth1] 异常: {e}')

    # Firebase
    if not token:
        try:
            id_token = login_firebase(email, password)
            if id_token:
                token = id_token
                auth_method = 'firebase'
        except Exception as e:
            print(f'[Firebase] 异常: {e}')

    if not token:
        print('[失败] 所有登录方式均失败')
        return

    # Codeium 注册
    reg = register_codeium(token)
    if not reg:
        print('[失败] Codeium 注册失败')
        return

    api_key = reg['api_key']
    api_server_url = reg.get('api_server_url', '')

    # 写入 state.vscdb
    ok = write_auth_to_state(api_key, email, api_server_url)
    if ok:
        print(f'\n[完成] 已将 {email} 的认证写入 state.vscdb')
        print('请打开 Windsurf 查看是否切换到该账号')
    else:
        print('[失败] 写入 state.vscdb 失败')

if __name__ == '__main__':
    main()
