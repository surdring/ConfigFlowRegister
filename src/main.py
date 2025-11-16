#!/usr/bin/env python3
"""
WindSurf账号批量注册工具 - 主程序入口

简化MVP版本 - 展示核心架构和基础设施已就绪
"""

import tkinter as tk
from pathlib import Path
import sys

# 确保导入路径正确（支持打包和开发环境）
try:
    # 开发环境 - 使用相对导入
    from utils.logger import setup_logger
    from utils import config as app_config
    from data.data_manager import Configuration, DataManager
    from utils.exceptions import ValidationError
except (ImportError, ValueError):
    # PyInstaller打包环境 - 使用绝对导入
    try:
        from src.utils.logger import setup_logger
        from src.utils import config as app_config
        from src.data.data_manager import Configuration, DataManager
        from src.utils.exceptions import ValidationError
    except ImportError:
        # 最后尝试添加路径
        import sys
        import os
        # 添加src目录到Python路径
        src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
        if src_path not in sys.path:
            sys.path.insert(0, src_path)
        
        from src.utils.logger import setup_logger
        from src.utils import config as app_config
        from src.data.data_manager import Configuration, DataManager
        from src.utils.exceptions import ValidationError


def main():
    """主程序入口"""
    # 设置日志
    logger = setup_logger()
    logger.info("="*50)
    logger.info("WindSurf账号批量注册工具启动")
    logger.info("="*50)
    
    try:
        # 加载配置
        logger.info("正在加载配置...")
        config_dict = app_config.load_config()
        config = Configuration.from_json(config_dict)
        
        # 验证配置
        errors = config.validate()
        if errors:
            logger.error("配置验证失败:")
            for error in errors:
                logger.error(f"  - {error}")
            return 1
        
        logger.info("配置加载成功")
        
        # 初始化DataManager
        # 处理打包后的资源路径
        if getattr(sys, 'frozen', False):
            # 打包后的环境
            base_path = Path(sys._MEIPASS)
            email_generator = base_path / "scripts" / "email_generator.py"
        else:
            # 开发环境
            email_generator = Path("scripts/email_generator.py")
        
        data_manager = DataManager(email_generator, config)
        
        # 检查未完成的任务
        existing_task = None
        
        # 创建Tkinter根窗口
        root = tk.Tk()
        root.title("WindSurf账号批量注册工具")
        root.geometry("900x700")
        
        # 创建完整的GUI界面
        try:
            from gui.main_window import MainWindow
        except ImportError:
            from src.gui.main_window import MainWindow
        app = MainWindow(root, config, data_manager, existing_task)
        
        logger.info("GUI窗口已创建")
        
        # 启动事件循环
        root.mainloop()
        
        logger.info("程序正常退出")
        return 0
        
    except ValidationError as e:
        logger.error(f"配置错误: {e}")
        print("\n" + "="*60)
        print("程序启动失败，请检查上述错误信息")
        print("="*60)
        input("\n按回车键退出...")
        return 1
    except KeyboardInterrupt:
        logger.info("用户中断程序")
        return 0
    except Exception as e:
        logger.error(f"程序异常退出: {e}", exc_info=True)
        print("\n" + "="*60)
        print("程序异常退出，请检查上述错误信息")
        print("="*60)
        input("\n按回车键退出...")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
