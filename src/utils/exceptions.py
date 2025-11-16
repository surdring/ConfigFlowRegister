"""
自定义异常类模块

定义应用程序中使用的所有自定义异常。
"""


class RegistrationError(Exception):
    """注册流程错误基类"""
    pass


class BrowserError(RegistrationError):
    """浏览器操作相关错误"""
    pass


class ElementNotFoundError(BrowserError):
    """页面元素未找到"""
    pass


class PageLoadError(BrowserError):
    """页面加载失败"""
    pass


class VerificationFailedError(BrowserError):
    """验证码验证失败"""
    pass


class EmailError(RegistrationError):
    """邮箱服务相关错误"""
    pass


class ConnectionError(EmailError):
    """邮箱连接失败"""
    pass


class AuthenticationError(EmailError):
    """邮箱认证失败（授权码错误）"""
    pass


class VerificationCodeNotFoundError(EmailError):
    """验证码未找到"""
    pass


class DataError(RegistrationError):
    """数据管理相关错误"""
    pass


class EmailGeneratorError(DataError):
    """邮箱生成器执行失败"""
    pass


class FileCorruptedError(DataError):
    """数据文件损坏"""
    pass


class ValidationError(RegistrationError):
    """配置验证错误"""
    pass
