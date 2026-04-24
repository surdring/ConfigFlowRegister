#!/usr/bin/env python3
"""测试 IMAP 连接，诊断问题"""
import os
import sys
import imaplib
import ssl

# 解密配置
os.environ['CONFIGFLOW_EMAIL_SECRET_KEY'] = 'windsurf'
sys.path.insert(0, 'src')
from utils.email_crypto import decrypt_email_secret

email = decrypt_email_secret('enc:aj0zhBLE0hGZPw8dRdmj')
password = decrypt_email_secret('enc:Mmp_3EWVh0qvNBVJRdSv2A==')

print(f"邮箱: {email}")
print(f"授权码长度: {len(password)}")
print(f"授权码前4位: {password[:4]}")
print("=" * 50)

# 测试 IMAP 连接
try:
    print("连接 imap.qq.com:993...")
    imap = imaplib.IMAP4_SSL("imap.qq.com", 993)
    print("✓ SSL 连接成功")
    
    print("登录中...")
    imap.login(email, password)
    print("✓ 登录成功")
    
    print("选择 INBOX...")
    imap.select("INBOX")
    print("✓ INBOX 选择成功")
    
    # 搜索未读邮件
    typ, data = imap.search(None, "UNSEEN")
    print(f"未读邮件数量: {len(data[0].split()) if data[0] else 0}")
    
    imap.logout()
    print("✓ 测试完成，IMAP 连接正常")
    
except imaplib.IMAP4.error as e:
    print(f"✗ IMAP 错误: {e}")
    if "authentication failed" in str(e).lower():
        print("  → 授权码错误，请重新生成")
    elif "b'[AUTHENTICATIONFAILED]" in str(e):
        print("  → QQ 邮箱授权码已过期或错误")
except Exception as e:
    print(f"✗ 其他错误: {type(e).__name__}: {e}")
